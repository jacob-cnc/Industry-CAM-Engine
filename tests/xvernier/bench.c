/* Offline bench for the X vernier (rtcomp/xvernier.comp). No realtime, no HAL.
 *
 * Simulates the X loop at the servo period: motion command -> pid.x (LinuxCNC pid
 * semantics: deadband, P, D, FF1, maxoutput) -> hm2 stepgen in velocity mode
 * (maxaccel, sub-step position-fb) -> integer motor steps -> closed-loop stepper
 * lag -> backlash play -> screw error -> carriage -> quantized linear scale with
 * noise and edge hysteresis.
 *
 * Three loops are compared on the same sequences:
 *   scale-db5   pid.x on the raw scale, DEADBAND .0005   (today)
 *   scale-db11  pid.x on the raw scale, DEADBAND .00011  (step 1)
 *   vernier     pid.x on xvernier.pos-est, DEADBAND .00001 (step 2)
 * The vernier also runs in SHADOW in the scale loops, as it would in shadow mode.
 *
 * Output: one RESULT line per loop/scenario/plant, errors in DIAMETER inches:
 *   RESULT <loop> <scenario> <plant> n=<holds> max=<..> rms=<..> est_max=<..> dither=<..> fault=<0|1>
 * usage: xv_bench [plant-name ...]   (default: all plants)
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xv_core.h"

#define DT 0.002
#define STEPS_PER_IN 54186.667
#define SCALE_CPI 5080.0

typedef struct {
    const char *name;
    double backlash_h;      /* half backlash, radius in */
    double motor_tau;       /* closed-loop stepper lag time constant, s */
    double screw_k;         /* linear step-scale error (fraction) */
    double screw_a;         /* periodic screw error amplitude, radius in */
    double screw_pitch;     /* periodic error period, in */
    double noise;           /* scale noise, counts rms */
    double hyst;            /* scale edge hysteresis, counts */
    double scale_sign;      /* +1 / -1 encoder scale sign */
    double drift;           /* thermal drift of the step/scale offset, in/s */
} plant_t;

static const plant_t PLANTS[] = {
    /* name        h        tau    k      a        pitch   noise hyst sign drift */
    {"ideal",      0.0,     0.0005, 0.0,   0.0,     0.059, 0.0,  0.0, -1, 0.0},
    {"nominal",    0.0001,  0.001, 2e-4,  0.00008, 0.059, 0.02, 0.0, -1, 0.0},
    {"loose",      0.0004,  0.002, 5e-4,  0.00015, 0.059, 0.05, 0.05,-1, 0.0},
    {"laggy",      0.0001,  0.004, 2e-4,  0.00008, 0.059, 0.02, 0.0, -1, 0.0},
    {"warming",    0.0001,  0.001, 2e-4,  0.00008, 0.059, 0.02, 0.0, -1, 2e-6},
    {"only-backlash",0.0001, 0.0005, 0.0,  0.0,     0.059, 0.0,  0.0, -1, 0.0},
    {"only-lag",   0.0,     0.001, 0.0,   0.0,     0.059, 0.0,  0.0, -1, 0.0},
    {"only-screwk",0.0,     0.0005, 2e-4,  0.0,     0.059, 0.0,  0.0, -1, 0.0},
    {"only-screwa",0.0,     0.0005, 0.0,   0.00008, 0.059, 0.0,  0.0, -1, 0.0},
    {"only-noise", 0.0,     0.0005, 0.0,   0.0,     0.059, 0.02, 0.0, -1, 0.0},
    {"pos-scale",  0.0001,  0.001, 2e-4,  0.00008, 0.059, 0.02, 0.0, +1, 0.0},
};
#define NPLANTS (sizeof PLANTS / sizeof PLANTS[0])

typedef struct { const char *name; int vernier_fb; double deadband; int cal; double alpha_h; } loop_t;
static const loop_t LOOPS[] = {
    {"scale-db5", 0, 0.0005, 0, 0},
    {"scale-db11", 0, 0.00011, 0, 0},
    {"vernier", 1, 0.00001, 0, 0.1},   /* no calibration at all, learns backlash online */
    {"vern-cal", 1, 0.00001, 1, 0},    /* sweep-calibrated (90%), backlash frozen: the shipped default */
    {"vern-cal-h", 1, 0.00001, 1, 0.1},/* calibrated + online backlash learning */
};

/* ---------------------------------------------------------------- RNG */
static unsigned long long rng = 88172645463325252ULL;
static double urand(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (rng >> 11) * (1.0 / 9007199254740992.0); }
static double grand(void) { double u = urand() + 1e-12, v = urand(); return sqrt(-2 * log(u)) * cos(2 * M_PI * v); }

/* ---------------------------------------------------------------- sim */
typedef struct {
    const plant_t *pl; const loop_t *lp;
    double t;
    /* motion */
    double cmd, cmd_v, cmd_prev;
    /* pid */
    double prev_err;
    /* stepgen */
    double sg_v, s;
    /* motor / carriage */
    double motor, carriage, x_true;
    /* scale */
    int counts;
    /* vernier */
    xv_param pa; xv_state st; xv_out o;
    double drift_off;
    FILE *cap;          /* sweep capture, same columns as capture.sh */
    /* hold stats */
    long dither; double last_step_dir; long last_steps;
} sim_t;

static double screw_err(const plant_t *pl, double x)
{
    return pl->screw_k * x + pl->screw_a * sin(2 * M_PI * x / pl->screw_pitch);
}

static void scale_read(sim_t *S)
{
    const plant_t *pl = S->pl;
    double q = S->x_true * SCALE_CPI + pl->noise * grand();
    int n = (int)(pl->scale_sign > 0 ? S->counts : -S->counts);    /* count in +x frame */
    double hy = 0.5 * pl->hyst;
    while (q > n + 0.5 + hy) n++;
    while (q < n - 0.5 - hy) n--;
    S->counts = pl->scale_sign > 0 ? n : -n;
}

static void sim_init(sim_t *S, const plant_t *pl, const loop_t *lp, double x0)
{
    memset(S, 0, sizeof *S);
    S->pl = pl; S->lp = lp;
    S->cmd = S->cmd_prev = x0;
    S->s = x0 + 0.0123;                 /* arbitrary step/scale frame offset */
    S->motor = round(S->s * STEPS_PER_IN) / STEPS_PER_IN;
    S->carriage = S->motor;
    S->x_true = S->carriage - 0.0123 - screw_err(pl, S->carriage);
    S->counts = (int)lround(pl->scale_sign * S->x_true * SCALE_CPI);
    S->pa.k_scale = pl->scale_sign * SCALE_CPI;
    S->pa.k_alpha = 0.3; S->pa.k_alpha_h = lp->alpha_h; S->pa.k_run_ticks = 6;
    S->pa.k_h_init = 0.0; S->pa.k_h_max = 0.002;
    S->pa.k_span_max = 0.0001; S->pa.k_margin = 0.1; S->pa.k_lag_cycles = 2.0;
    S->pa.k_lag_time = 0.0; S->pa.k_hyst = 0.0; S->pa.k_fault_limit = 0.0005;
    if (lp->cal) {
        S->pa.k_slope = pl->screw_k;
        S->pa.k_lead = pl->screw_pitch;
        S->pa.k_hs_init = 0.9 * pl->screw_a;   /* b = s - x = .0123 + screw_err(s) */
        S->pa.k_alpha_harm = 0.02;
        S->pa.k_h_init = 0.9 * pl->backlash_h;
        S->pa.k_lag_time = 0.9 * pl->motor_tau;
        /* XV_CAL="H_INIT LEAD HARM_COS HARM_SIN SLOPE LAG_TIME": use a real fit instead */
        const char *cal = getenv("XV_CAL");
        if (cal) {
            double h, ld, hc, hs, sl, lg;
            if (sscanf(cal, "%lf %lf %lf %lf %lf %lf", &h, &ld, &hc, &hs, &sl, &lg) == 6) {
                S->pa.k_h_init = h; S->pa.k_lead = ld; S->pa.k_hc_init = hc;
                S->pa.k_hs_init = hs; S->pa.k_slope = sl; S->pa.k_lag_time = lg;
            }
        }
    }
}

static void sim_cycle(sim_t *S)
{
    const plant_t *pl = S->pl;
    /* read: scale and step feedback */
    scale_read(S);
    xv_update(&S->st, &S->pa, S->s, S->counts, 1, DT, &S->o);
    if (S->cap)   /* columns: step_fb scale_counts motor_pos_cmd pos_est residual enable,
                     all as read together at the top of the servo cycle (like hm2 read) */
        fprintf(S->cap, "%.9f %d %.9f %.9f %.4f 1\n", S->s, S->counts, S->cmd, S->o.x, S->o.res);
    double fb = S->lp->vernier_fb ? S->o.x : S->counts / S->pa.k_scale;

    /* pid.x (LinuxCNC pid: deadband shrinks the error, FF1 on command velocity) */
    double err = S->cmd - fb;
    double db = S->lp->deadband;
    if (err > db) err -= db; else if (err < -db) err += db; else err = 0;
    double vcmd = (S->cmd - S->cmd_prev) / DT;
    double out = 125.0 * err + 0.002 * (err - S->prev_err) / DT + 1.0 * vcmd;
    S->prev_err = err;
    if (out > 2.5) out = 2.5; if (out < -2.5) out = -2.5;
    S->cmd_prev = S->cmd;

    /* stepgen velocity mode, maxaccel 12.5, maxvel 1.8 */
    double dv = out - S->sg_v, amax = 12.5 * DT;
    if (dv > amax) dv = amax; if (dv < -amax) dv = -amax;
    S->sg_v += dv;
    if (S->sg_v > 1.8) S->sg_v = 1.8; if (S->sg_v < -1.8) S->sg_v = -1.8;
    S->s += S->sg_v * DT;

    /* motor follows integer steps with lag; carriage through backlash play */
    long steps = lround(S->s * STEPS_PER_IN);
    if (steps != S->last_steps) {
        double d = steps > S->last_steps ? 1 : -1;
        if (S->last_step_dir != 0 && d != S->last_step_dir) S->dither++;
        S->last_step_dir = d; S->last_steps = steps;
    }
    double target = steps / STEPS_PER_IN;
    if (pl->motor_tau > 0) S->motor += (target - S->motor) * (1 - exp(-DT / pl->motor_tau));
    else S->motor = target;
    if (S->carriage < S->motor - pl->backlash_h) S->carriage = S->motor - pl->backlash_h;
    if (S->carriage > S->motor + pl->backlash_h) S->carriage = S->motor + pl->backlash_h;
    S->drift_off += pl->drift * DT;
    S->x_true = S->carriage - 0.0123 - screw_err(pl, S->carriage) - S->drift_off;
    S->t += DT;
}

/* motion planner: trapezoid to target at vmax, accel 10 */
static void move_to(sim_t *S, double target, double vmax)
{
    double v = 0, a = 10.0;
    for (int i = 0; i < 2000000; i++) {
        double dist = target - S->cmd;
        if (fabs(dist) < 1e-12 && fabs(v) < 1e-9) break;
        double dir = dist > 0 ? 1 : -1;
        double vstop = sqrt(2 * a * fabs(dist));
        double vdes = dir * (vstop < vmax ? vstop : vmax);
        double dv = vdes - v;
        if (dv > a * DT) dv = a * DT; if (dv < -a * DT) dv = -a * DT;
        v += dv;
        double step = v * DT;
        if ((dist > 0 && step >= dist) || (dist < 0 && step <= dist) || fabs(dist) < 1e-9) { S->cmd = target; v = 0; }
        else S->cmd += step;
        sim_cycle(S);
    }
    S->cmd = target;
}

static void dwell(sim_t *S, double sec) { for (int i = 0; i < (int)(sec / DT); i++) sim_cycle(S); }

typedef struct { int n; double max, sum2, est_max; long dither; } stats_t;
static void record(stats_t *s, sim_t *S)
{
    double e = 2 * (S->x_true - S->cmd);
    double ee = 2 * (S->o.x - S->x_true);
    if (fabs(e) > s->max) s->max = fabs(e);
    if (fabs(ee) > s->est_max) s->est_max = fabs(ee);
    s->sum2 += e * e; s->n++; s->dither += S->dither;
    if (getenv("XV_DEBUG"))
        fprintf(stderr, "hold cmd=%.6f err_dia=%+.6f est_dia=%+.6f h=%.6f u=%+.6f carr-mot=%+.6f rev=%ld n=%ld\n",
                S->cmd, e, ee, S->st.h, S->st.u, S->carriage - S->motor, S->st.n_rev, S->st.n_samples);
}

#define FEED 0.025      /* radius in/s, ~0.003 ipr at 1000 rpm on diameter */
#define RAPID 1.0

/* scenarios: every hold is preceded by roughing-like travel so the vernier has
 * to keep up across the axis, not just at one spot */
static void run(const plant_t *pl, const loop_t *lp, const char *scen, stats_t *st, int *fault)
{
    sim_t S;
    rng = 88172645463325252ULL;              /* same targets for every loop */
    sim_init(&S, pl, lp, 1.0);
    dwell(&S, 0.2);
    move_to(&S, 1.6, RAPID); move_to(&S, 0.9, FEED * 8);  /* warm-up roughing */
    for (int k = 0; k < 30; k++) {
        double T = 1.0 + 0.5 * urand();           /* random sub-count landing */
        if (!strcmp(scen, "face-up")) {           /* finish contour: feed up the face to the diameter */
            move_to(&S, T - 0.08, RAPID); dwell(&S, 0.1);
            move_to(&S, T, FEED); dwell(&S, 0.5); S.dither = 0; dwell(&S, 0.5); record(st, &S);
        } else if (!strcmp(scen, "face-down")) {   /* ID-style: feed down to the diameter */
            move_to(&S, T + 0.08, RAPID); dwell(&S, 0.1);
            move_to(&S, T, FEED); dwell(&S, 0.5); S.dither = 0; dwell(&S, 0.5); record(st, &S);
        } else if (!strcmp(scen, "rapid-in")) {   /* rapid straight to the diameter (no slow edges) */
            move_to(&S, T + 0.3 * (urand() < 0.5 ? 1 : -1), RAPID); dwell(&S, 0.1);
            move_to(&S, T, RAPID); dwell(&S, 0.5); S.dither = 0; dwell(&S, 0.5); record(st, &S);
        } else if (!strcmp(scen, "lost-steps")) { /* carriage slips .001 r at hold 10 (lost steps) */
            move_to(&S, T - 0.08, RAPID); move_to(&S, T, FEED); dwell(&S, 0.3);
            if (k == 10) { S.drift_off += 0.001; dwell(&S, 0.05); if (S.st.flt) *fault = 1; }
            dwell(&S, 0.7); S.dither = 0; dwell(&S, 0.5);
            if (k != 10) record(st, &S);
            continue;
        } else if (!strcmp(scen, "wear-steps")) { /* .0001 dia wear steps after a face-up approach */
            move_to(&S, T - 0.08, RAPID); move_to(&S, T, FEED); dwell(&S, 0.5);
            for (int j = 1; j <= 6; j++) {
                double TT = T + j * 0.00005;
                move_to(&S, TT, FEED); dwell(&S, 0.5); S.dither = 0; dwell(&S, 0.5); record(st, &S);
            }
        }
        if (S.st.flt) *fault = 1;
    }
}

/* the calibration sweep, mirroring scripts/xvernier/x_calibration_sweep.ngc
   (radius units; feeds converted from the program's ipm) */
static void sweep(const plant_t *pl, const char *path)
{
    sim_t S;
    sim_init(&S, pl, &LOOPS[0], 1.0);           /* calibration runs on today's loop */
    S.cap = fopen(path, "w");
    if (!S.cap) { perror(path); exit(1); }
    fprintf(S.cap, "# xv_bench sweep plant=%s h=%g tau=%g k=%g a=%g pitch=%g\n", pl->name,
            pl->backlash_h, pl->motor_tau, pl->screw_k, pl->screw_a, pl->screw_pitch);
    double feeds[] = {0.6, 1.5, 3.0};
    dwell(&S, 0.5);
    for (int i = 0; i < 3; i++) {
        double v = feeds[i] / 60.0;
        move_to(&S, 1.25, v); dwell(&S, 0.5);
        move_to(&S, 1.0, v); dwell(&S, 0.5);
    }
    for (int i = 0; i < 10; i++) {
        move_to(&S, 1.005 + 0.01 * i, 0.01); dwell(&S, 0.3);
        move_to(&S, 1.0 + 0.01 * i, 0.01); dwell(&S, 0.3);
    }
    fclose(S.cap);
}

/* x_positioning_test.ngc, radius units (xd = 2.0 dia), captured like capture.sh */
static void positioning(const plant_t *pl, const loop_t *lp, const char *path)
{
    sim_t S;
    sim_init(&S, pl, lp, 1.05);
    S.cap = fopen(path, "w");
    if (!S.cap) { perror(path); exit(1); }
    fprintf(S.cap, "# xv_bench positioning plant=%s loop=%s\n", pl->name, lp->name);
    for (int k = 0; k < 12; k++) {
        double t = 1.0 + 0.05 + 0.013765 * k;
        move_to(&S, t - 0.025, RAPID); move_to(&S, t, 2.0 / 60); dwell(&S, 3.0);
        move_to(&S, t + 0.025, RAPID); move_to(&S, t, 2.0 / 60); dwell(&S, 3.0);
        move_to(&S, t + 0.15, RAPID); move_to(&S, t, RAPID); dwell(&S, 3.0);
    }
    fclose(S.cap);
}

int main(int argc, char **argv)
{
    if (argc == 5 && !strcmp(argv[1], "--positioning")) {
        for (unsigned p = 0; p < NPLANTS; p++)
            for (unsigned l = 0; l < sizeof LOOPS / sizeof LOOPS[0]; l++)
                if (!strcmp(argv[2], PLANTS[p].name) && !strcmp(argv[3], LOOPS[l].name)) {
                    positioning(&PLANTS[p], &LOOPS[l], argv[4]); return 0;
                }
        fprintf(stderr, "unknown plant/loop\n"); return 2;
    }
    if (argc == 4 && !strcmp(argv[1], "--sweep")) {
        for (unsigned p = 0; p < NPLANTS; p++)
            if (!strcmp(argv[2], PLANTS[p].name)) { sweep(&PLANTS[p], argv[3]); return 0; }
        fprintf(stderr, "unknown plant %s\n", argv[2]); return 2;
    }
    const char *only_scen = getenv("XV_SCEN"), *only_loop = getenv("XV_LOOP");
    const char *scens[] = {"face-up", "face-down", "rapid-in", "wear-steps", "lost-steps"};
    for (unsigned p = 0; p < NPLANTS; p++) {
        int want = argc < 2;
        for (int a = 1; a < argc; a++) if (!strcmp(argv[a], PLANTS[p].name)) want = 1;
        if (!want) continue;
        for (unsigned l = 0; l < sizeof LOOPS / sizeof LOOPS[0]; l++)
            for (unsigned s = 0; s < 5; s++) {
                stats_t st = {0}; int fault = 0;
                if (only_scen && strcmp(only_scen, scens[s])) continue;
                if (only_loop && strcmp(only_loop, LOOPS[l].name)) continue;
                run(&PLANTS[p], &LOOPS[l], scens[s], &st, &fault);
                printf("RESULT %-10s %-10s %-9s n=%-3d max=%.5f rms=%.5f est_max=%.5f dither=%ld fault=%d\n",
                       LOOPS[l].name, scens[s], PLANTS[p].name, st.n, st.max,
                       sqrt(st.sum2 / (st.n ? st.n : 1)), st.est_max, st.dither, fault);
            }
    }
    return 0;
}
