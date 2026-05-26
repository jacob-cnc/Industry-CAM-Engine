#!/bin/bash
# Monitor X axis velocity ceiling test
# Logs key signals during a fast MPG jog
# Usage: ./monitor_x_vel.sh [duration_seconds]
# Results saved to /tmp/x_vel_test_HHMMSS.csv

DURATION=${1:-15}
LOGFILE="/tmp/x_vel_test_$(date +%H%M%S).csv"

echo "Logging to: $LOGFILE"
echo "Running for ${DURATION}s — do your fast MPG jog now!"
echo "Press Ctrl+C to stop early"
echo ""
printf "%-8s %-14s %-14s %-12s %-10s\n" "time" "pos_cmd" "pos_fb" "f_error" "vel_cmd"
echo "time,pos_cmd,pos_fb,f_error,vel_cmd" > "$LOGFILE"

END=$((SECONDS + DURATION))

while [ $SECONDS -lt $END ]; do
    SNAP=$(halcmd show pin joint.0.motor-pos-cmd joint.0.motor-pos-fb joint.0.f-error stepgen.01.velocity-cmd 2>/dev/null \
        | awk '/joint\.0\.motor-pos-cmd/ {cmd=$4}
               /joint\.0\.motor-pos-fb/  {fb=$4}
               /joint\.0\.f-error /      {fe=$4}
               /stepgen\.01\.velocity-cmd/ {vc=$4}
               END {print cmd","fb","fe","vc}')

    T=$SECONDS
    echo "$T,$SNAP" >> "$LOGFILE"
    printf "%-8s %s\n" "${T}s" "$SNAP"
    sleep 0.1
done

echo ""
echo "Done. Log: $LOGFILE"
echo ""
echo "=== RESULTS ==="
awk -F, 'NR>1 && $4!="" {
    v=$4; if(v<0)v=-v
    if(v>maxfe) maxfe=v
    vc=$5; if(vc<0)vc=-vc
    if(vc>maxvc) maxvc=vc
} END {
    printf "Peak f-error:  %.6f\" (%.2f thou)\n", maxfe, maxfe*1000
    printf "Max vel-cmd:   %.4f in/s\n", maxvc
}' "$LOGFILE"
