#!/bin/bash
# Servo-rate capture for the X vernier (one line per 2 ms servo period):
#   step_fb scale_counts motor_pos_cmd pos_est residual enable
# Needs LinuxCNC running with x-vernier-observe.hal loaded. Loads the standard
# `sampler` component on first use (a few hundred bytes per cycle; cheap) and
# reads it with halsampler. Does not command the machine.
#
# usage: scripts/xvernier/capture.sh SECONDS OUT.txt
#   then run the program (sweep / positioning / staircase) while it records.
set -e
SECS=${1:?seconds}; OUT=${2:?output file}
PERIOD_S=0.002
N=$(python3 -c "print(int($SECS / $PERIOD_S))")

halcmd -s show pin xvernier.pos-est >/dev/null 2>&1 || {
    echo "xvernier not loaded: enable HALFILE = x-vernier-observe.hal and restart LinuxCNC"; exit 1; }

# signal on a pin, or create one
sig_of() {   # pin -> signal name ('' if none)
    halcmd -s show pin "$1" | awk '{for (i=1;i<=NF;i++) if ($i=="==>"||$i=="<==") print $(i+1)}' | head -1
}
attach() {   # pin samplerpin newsig
    local s; s=$(sig_of "$1")
    if [ -z "$s" ]; then s=$3; halcmd net "$s" "$1"; fi
    halcmd net "$s" "$2"
}

if ! halcmd -s show pin sampler.0.enable >/dev/null 2>&1 || [ -z "$(halcmd -s show pin sampler.0.enable)" ]; then
    halcmd loadrt sampler depth=20000 cfg=fsfffb
    halcmd addf sampler.0 servo-thread
    halcmd setp sampler.0.enable 0
    attach hm2_7i96s.0.stepgen.01.position-fb sampler.0.pin.0 x-step-fb
    attach hm2_7i96s.0.encoder.01.count       sampler.0.pin.1 x-scale-counts
    attach joint.0.motor-pos-cmd              sampler.0.pin.2 x-pos-cmd
    attach xvernier.pos-est                   sampler.0.pin.3 xv-cap-est
    attach xvernier.residual                  sampler.0.pin.4 xv-cap-resid
    attach joint.0.amp-enable-out             sampler.0.pin.5 x-enable
fi

halcmd setp sampler.0.enable 0
timeout 0.5 halsampler -c 0 >/dev/null 2>&1 || true        # drain anything stale
halcmd setp sampler.0.overruns 0
{
  echo "# xvernier capture $(date '+%F %T') period=$PERIOD_S"
  echo "# params: $(halcmd -s show param xvernier | awk '{printf "%s=%s ", $NF, $(NF-1)}')"
  echo "# columns: step_fb scale_counts motor_pos_cmd pos_est residual enable"
} > "$OUT"
echo "recording $SECS s ($N samples) -> $OUT ... start the program now"
halcmd setp sampler.0.enable 1
halsampler -c 0 -n "$N" >> "$OUT"
halcmd setp sampler.0.enable 0
OV=$(halcmd -s getp sampler.0.overruns)
echo "done: $(grep -vc '^#' "$OUT") samples, overruns=$OV"
[ "$OV" = "0" ] || echo "WARNING: $OV samples lost (FIFO overrun) - the data has gaps; re-run if this is large"
echo "vernier: samples=$(halcmd getp xvernier.samples) clamps=$(halcmd getp xvernier.clamps) \
max-shift=$(halcmd getp xvernier.max-shift) fault=$(halcmd getp xvernier.fault) h=$(halcmd getp xvernier.half-backlash)"
