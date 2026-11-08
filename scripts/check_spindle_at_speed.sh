#!/bin/bash
# Standalone check of the spindle at-speed window (near, scale 2.0) — no Mesa.
# in1 = commanded rev/s (signed), in2 = measured rev/s (signed).
# LinuxCNC must NOT be running.
set -u
if pgrep -x milltask >/dev/null || pgrep -f linuxcncsvr >/dev/null; then
    echo "LinuxCNC is running — close it first." >&2; exit 2; fi
REALTIME=/usr/lib/linuxcnc/realtime
$REALTIME status >/dev/null 2>&1 && { echo "realtime already running (halrun -U)"; exit 2; }
$REALTIME start || exit 1
trap '$REALTIME stop >/dev/null 2>&1' EXIT
halcmd -f /dev/stdin <<'HAL' || { echo "HAL load FAILED"; exit 1; }
loadrt threads name1=servo-thread period1=2000000
loadrt near names=near-spindle
addf near-spindle servo-thread
setp near-spindle.scale 2.0
setp near-spindle.difference 0
start
HAL
fail=0
case_() { # desc cmd_rpm meas_rpm expected
  halcmd setp near-spindle.in1 "$(python3 -c "print($2/60)")"
  halcmd setp near-spindle.in2 "$(python3 -c "print($3/60)")"
  sleep 0.05
  got=$(halcmd -s getp near-spindle.out | tr -d '[:space:]')
  [ "$got" = "$4" ] && r=PASS || { r=FAIL; fail=1; }
  printf "  %-4s %-38s cmd %6s RPM  meas %6s RPM -> %s\n" "$r" "$1" "$2" "$3" "$got"
}
case_ "stopped, nothing commanded"      0     0   TRUE
case_ "M3 S64, gearbox 64 (meas 80.3)" 64   80.3  TRUE
case_ "M3 S64, exactly 2x"              64   128   TRUE
case_ "M3 S64, exactly 0.5x"            64    32   TRUE
case_ "M3 S64, spindle not started"     64     0   FALSE
case_ "M3 S64, too slow (0.4x)"         64  25.6   FALSE
case_ "M3 S64, wrong gear (3x)"         64   192   FALSE
case_ "M3 S64, running in REVERSE"      64 -80.3   FALSE
case_ "M3 S500, measured 480"          500   480   TRUE
case_ "spindle coasting, S0 commanded"   0    40   FALSE
halcmd stop; halcmd unload all
[ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"; exit $fail
