/* Offline replay of a capture.sh file through the shipped xvernier estimator.
 *
 * Build: scripts/xvernier/build_replay.sh [OUTDIR]   (extracts CORE-BEGIN..CORE-END
 *        from rtcomp/xvernier.comp, so this runs exactly the RT module's code)
 * Run:   xv_replay CAPTURE.txt
 *        H=0.0038958 HMAX=0.005 SLOPE=4.5597e-4 FLT=0.016 xv_replay CAPTURE.txt
 *
 * No HAL, no realtime, no machine. Reads the columns capture.sh writes:
 *   step_fb scale_counts motor_pos_cmd pos_est residual enable
 *
 * Metric: at every learned scale edge, the innovation r = estimate minus the
 * true edge position just before the edge updates the estimate. That is the
 * estimator's position error at that instant.
 *   "steady"     = all learned edges except the ones below
 *   "after-rest" = first 3 learned edges after the motor sat still >= 0.5 s
 *                  (what parking accuracy depends on)
 * Clamps = cycles where the scale forced the estimate back within half a count.
 * In closed mode each clamp shift becomes a step in the PID feedback.
 *
 * Parameters (environment, radius units) default to the [XVERNIER] defaults:
 *   ALPHA .3  H (H_INIT) 0  HMAX .002  SLOPE 0  SPAN (SPAN_MAX) .0001  FLT .0005
 *   SCALE -5080  DT .002
 *   BIG=1 also lists every clamp shift larger than .0005 dia, with its time.
 * All printed results are in DIAMETER.
 *
 * 2026-11-11 sweep result (fitted H/SLOPE, HMAX .005, FLT .016): steady rms
 * .00010, after-rest rms .00015 / max .0003, clamps .0005-.0009 at reversals.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "xv_core.h"

static double env(const char *k, double d) { const char *v = getenv(k); return v ? atof(v) : d; }

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: xv_replay CAPTURE.txt  (see header for env params)\n"); return 2; }
    FILE *f = fopen(argv[1], "r");
    if (!f) { perror(argv[1]); return 2; }

    xv_param pa; memset(&pa, 0, sizeof pa);
    pa.k_scale = env("SCALE", -5080);   pa.k_alpha = env("ALPHA", 0.3);  pa.k_alpha_h = 0;
    pa.k_h_init = env("H", 0.0);         pa.k_h_max = env("HMAX", 0.002); pa.k_run_ticks = 6;
    pa.k_lead = 0;                        pa.k_alpha_harm = 0.02;          pa.k_slope = env("SLOPE", 0.0);
    pa.k_span_max = env("SPAN", 0.0001); pa.k_margin = 0.1;              pa.k_lag_cycles = 2;
    pa.k_lag_time = 0;                    pa.k_hyst = 0;                   pa.k_fault_limit = env("FLT", 0.0005);
    double dt = env("DT", 0.002);
    int big = getenv("BIG") != NULL;
    printf("params: ALPHA %g H %g HMAX %g SLOPE %g SPAN %g FLT %g (radius)\n",
           pa.k_alpha, pa.k_h_init, pa.k_h_max, pa.k_slope, pa.k_span_max, pa.k_fault_limit);

    xv_state st; memset(&st, 0, sizeof st);
    xv_out o;
    char line[512];
    long n = 0, rest = 0, prev_ns = 0, ns = 0, na = 0;
    int post = 99, have = 0;
    double prev_s = 0, s2s = 0, s2a = 0, mxs = 0, mxa = 0;

    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == 'o') continue;          /* header, "overrun" */
        double s, cmd, est, res, en; int cnt;
        if (sscanf(line, "%lf %d %lf %lf %lf %lf", &s, &cnt, &cmd, &est, &res, &en) < 6) continue;
        double ds = have ? s - prev_s : 0; have = 1; prev_s = s;
        if (fabs(ds) < 1e-9) rest++; else { if (rest >= (long)(0.5 / dt)) post = 0; rest = 0; }

        long c0 = st.n_clamps; double b0 = st.b0;
        xv_update(&st, &pa, s, cnt, 1, dt, &o);
        if (big && st.n_clamps > c0 && fabs(st.b0 - b0) > 0.00025)
            printf("  t=%7.2f s  clamp shift %.5f dia\n", n * dt, 2 * fabs(st.b0 - b0));

        if (st.n_samples > prev_ns) {
            prev_ns = st.n_samples;
            if (st.n_samples > 20) {                               /* skip start-up mean */
                double r = fabs(st.last_r);
                if (post < 3) { s2a += r * r; na++; if (r > mxa) mxa = r; post++; }
                else          { s2s += r * r; ns++; if (r > mxs) mxs = r; }
            }
        }
        n++;
    }
    fclose(f);
    printf("samples %ld (%.1f s)  learned edges %ld  clamps %ld  max clamp %.5f  fault %d\n",
           n, n * dt, st.n_samples, st.n_clamps, 2 * st.mx_shift, st.flt);
    printf("edge error  steady:     rms %.5f  max %.5f  (n=%ld)\n", 2 * sqrt(s2s / (ns ? ns : 1)), 2 * mxs, ns);
    printf("edge error  after-rest: rms %.5f  max %.5f  (n=%ld)   [all dia]\n", 2 * sqrt(s2a / (na ? na : 1)), 2 * mxa, na);
    return 0;
}
