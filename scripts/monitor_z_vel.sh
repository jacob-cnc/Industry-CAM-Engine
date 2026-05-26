#!/bin/bash
# Monitor Z axis velocity ceiling test
# Usage: ./monitor_z_vel.sh [duration_seconds]

DURATION=${1:-15}
LOGFILE="/tmp/z_vel_test_$(date +%H%M%S).csv"

echo "Logging to: $LOGFILE"
echo "Duration: ${DURATION}s — do your fast MPG jog now!"
echo ""
printf "%-6s %-10s %-10s %-12s\n" "t(s)" "pos_cmd" "pos_fb" "f_error(thou)"
echo "time,pos_cmd,pos_fb,f_error" > "$LOGFILE"

END=$((SECONDS + DURATION))

while [ $SECONDS -lt $END ]; do
    CMD=$(halcmd getp joint.1.motor-pos-cmd 2>/dev/null)
    FB=$(halcmd getp joint.1.motor-pos-fb 2>/dev/null)
    FERR=$(halcmd getp joint.1.f-error 2>/dev/null)
    T=$SECONDS

    echo "$T,$CMD,$FB,$FERR" >> "$LOGFILE"

    FE_THOU=$(awk "BEGIN{v=$FERR; if(v<0)v=-v; printf \"%.2f\", v*1000}")
    printf "%-6s %-10s %-10s %-12s\n" "${T}s" \
        "$(printf '%.5f' $CMD)" "$(printf '%.5f' $FB)" "$FE_THOU"

    sleep 0.1
done

echo ""
echo "=== RESULTS ==="
awk -F, 'NR>1 && $4!="" {
    v=$4; if(v<0)v=-v
    if(v>maxfe) { maxfe=v; maxt=$1 }
    if(prev_cmd!="") {
        vel=($2-prev_cmd)/0.1; if(vel<0)vel=-vel
        if(vel>maxvel) maxvel=vel
    }
    prev_cmd=$2
} END {
    printf "Peak f-error: %.4f\" (%.2f thou) at t=%ss\n", maxfe, maxfe*1000, maxt
    printf "Peak vel est: %.3f in/s\n", maxvel
}' "$LOGFILE"
