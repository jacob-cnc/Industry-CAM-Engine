#!/bin/bash
# Monitor X axis PID tuning — f-error, cmd, fb, pid output
# Usage: ./monitor_x_pid.sh [duration_seconds]

DURATION=${1:-20}
LOGFILE="/tmp/x_pid_test_$(date +%H%M%S).csv"

echo "Logging to: $LOGFILE"
echo "Duration: ${DURATION}s — jog X now!"
echo ""
printf "%-6s %-10s %-10s %-12s %-10s\n" "t(s)" "pos_cmd" "pos_fb" "f_error(thou)" "pid_out"
echo "time,pos_cmd,pos_fb,f_error,pid_out" > "$LOGFILE"

END=$((SECONDS + DURATION))

while [ $SECONDS -lt $END ]; do
    CMD=$(halcmd getp joint.0.motor-pos-cmd 2>/dev/null)
    FB=$(halcmd getp joint.0.motor-pos-fb 2>/dev/null)
    FERR=$(halcmd getp joint.0.f-error 2>/dev/null)
    OUT=$(halcmd getp pid.x.output 2>/dev/null)
    T=$SECONDS

    echo "$T,$CMD,$FB,$FERR,$OUT" >> "$LOGFILE"

    # convert f-error to thou for display
    FE_THOU=$(awk "BEGIN{v=$FERR; if(v<0)v=-v; printf \"%.2f\", v*1000}")
    printf "%-6s %-10s %-10s %-12s %-10s\n" "${T}s" \
        "$(printf '%.5f' $CMD)" "$(printf '%.5f' $FB)" "$FE_THOU" "$(printf '%.4f' $OUT)"

    sleep 0.1
done

echo ""
echo "=== RESULTS ==="
awk -F, 'NR>1 && $4!="" {
    v=$4; if(v<0)v=-v
    if(v>maxfe) { maxfe=v; maxt=$1 }
    sum+=v; n++
} END {
    printf "Peak f-error: %.4f\" (%.2f thou) at t=%ss\n", maxfe, maxfe*1000, maxt
    printf "Mean f-error: %.4f\" (%.2f thou)\n", sum/n, (sum/n)*1000
}' "$LOGFILE"
