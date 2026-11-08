#!/bin/bash
# Standalone check of the compound-slide jog routing HAL (no Mesa, no motion).
#
# Loads ONLY the routing components from industry-cam.hal into a private
# halrun session and verifies:
#   1. pin names/types load (mux_generic ss2, and2, not)
#   2. signals declared with readers only can later get a writer (GUI pattern)
#   3. mux selects direct MPG by default and compound input when enabled
#   4. jog-enable gate = machine-on AND NOT inhibit
#
# LinuxCNC must NOT be running (halrun uses its own realtime session).
set -u
if pgrep -x milltask >/dev/null || pgrep -f linuxcncsvr >/dev/null; then
    echo "LinuxCNC is running — close it first." >&2
    exit 2
fi

fail=0
check() {  # check <pin> <expected>
    local got
    got=$(halcmd -s getp "$1" 2>/dev/null | tr -d '[:space:]')
    if [ "$got" = "$2" ]; then echo "  PASS $1 = $got"
    else echo "  FAIL $1 = '$got' (expected $2)"; fail=1; fi
}

REALTIME=/usr/lib/linuxcnc/realtime
if $REALTIME status >/dev/null 2>&1; then
    echo "A realtime session is already running (halrun -U to clear it)." >&2
    exit 2
fi
$REALTIME start || exit 1
trap '$REALTIME stop >/dev/null 2>&1' EXIT
halcmd -f /dev/stdin <<'EOF' || { echo "HAL load FAILED"; exit 1; }
loadrt threads name1=servo-thread period1=2000000
loadrt mux_generic config="ss2,ss2"
loadrt and2 names=and2.mpg-jog-gate
loadrt not names=not.compound-jog-inhibit
addf mux-gen.00                 servo-thread
addf mux-gen.01                 servo-thread
addf not.compound-jog-inhibit   servo-thread
addf and2.mpg-jog-gate          servo-thread
net compound-x-jog    => mux-gen.00.in-s32-01
net compound-z-jog    => mux-gen.01.in-s32-01
net compound-enable   => mux-gen.00.sel-bit-00 mux-gen.01.sel-bit-00
net compound-jog-inhibit => not.compound-jog-inhibit.in
net jog-not-inhibited    not.compound-jog-inhibit.out => and2.mpg-jog-gate.in1
setp mux-gen.00.in-s32-00 1111
setp mux-gen.01.in-s32-00 2222
setp and2.mpg-jog-gate.in0 1
start
EOF
sleep 0.2
echo "Default (no GUI writer): direct MPG, jog enabled"
check mux-gen.00.out-s32 1111
check mux-gen.01.out-s32 2222
check and2.mpg-jog-gate.out TRUE

# Emulate the GUI driving the reader-only signals
halcmd sets compound-x-jog 77
halcmd sets compound-z-jog 88
halcmd sets compound-jog-inhibit TRUE
sleep 0.05
echo "Inhibit asserted: jog disabled"
check and2.mpg-jog-gate.out FALSE
halcmd sets compound-enable TRUE
sleep 0.05
echo "Compound enabled: mux selects compound outputs"
check mux-gen.00.out-s32 77
check mux-gen.01.out-s32 88
halcmd sets compound-jog-inhibit FALSE
sleep 0.05
check and2.mpg-jog-gate.out TRUE

halcmd stop; halcmd unload all
[ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $fail
