#!/bin/bash
# RT tuning for LinuxCNC + Mesa hm2_eth on enp1s0.
# Run once manually: sudo bash set-cpu-performance.sh
# Or install the systemd service: sudo systemctl enable --now cpu-performance.service

# 1. CPU governor: lock at max frequency to eliminate SMI latency spikes
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
echo "CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

# 1b. Pin clock to a fixed frequency below the thermal-throttle point.
# Unpinned, the N150 turbos to 3.6 GHz, hits ~83C, and thermal-throttles
# constantly (1700+ events in 2 min) -> clock swings -> servo-thread jitter.
# A fixed 2.4 GHz is plenty for LinuxCNC and keeps the clock steady.
# Revert: echo 700000 > .../scaling_min_freq; echo 3600000 > .../scaling_max_freq
CPU_FREQ_KHZ=2400000
for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
    echo $CPU_FREQ_KHZ > $c/scaling_max_freq
    echo $CPU_FREQ_KHZ > $c/scaling_min_freq
done
echo "CPU freq pinned: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq)-$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq) kHz"

# 1c. Idle states, per core. Requires kernel cmdline intel_idle.max_cstate=2
# (max_cstate=1 on this N150 exposes only POLL). Housekeeping cores 0-1 may
# use C1 (~1 us exit) to shed heat; isolated RT cores 2-3 always POLL.
# Anything deeper than C1 is disabled everywhere.
HOUSEKEEPING_CPUS="0 1"
for s in /sys/devices/system/cpu/cpu[0-9]*/cpuidle/state[0-9]*; do
    cpu=$(echo "$s" | sed -E 's|.*/cpu([0-9]+)/cpuidle/.*|\1|')
    idx=${s##*state}
    want=1
    [ "$idx" -eq 0 ] && want=0                       # POLL: always allowed
    if [ "$idx" -eq 1 ] && [[ " $HOUSEKEEPING_CPUS " == *" $cpu "* ]]; then
        want=0                                       # C1 on housekeeping cores
    fi
    echo $want > "$s/disable"
done
for c in /sys/devices/system/cpu/cpu[0-9]*; do
    en=""
    for s in $c/cpuidle/state[0-9]*; do
        [ "$(cat $s/disable)" = 0 ] && en="$en $(cat $s/name)"
    done
    echo "idle states $(basename $c):$en"
done

# 2. qdisc: replace fq_codel (designed for internet) with pfifo_fast on Mesa NIC
/sbin/tc qdisc replace dev enp1s0 root pfifo_fast
echo "qdisc enp1s0: $(/sbin/tc qdisc show dev enp1s0 | head -1)"

# 3. Mesa NIC receive path priority (PREEMPT_RT).
# r8169 handles its IRQ in hard-IRQ context (no irq/NN-enp1s0 thread), so packet
# processing runs in ksoftirqd at normal (SCHED_OTHER) priority and can be
# delayed past the 2 ms servo period -> "hm2: error finishing read".
# Threaded NAPI moves receive processing into a napi/enp1s0-* kthread that we
# give SCHED_FIFO 70: above default IRQ threads (50), below LinuxCNC's RT threads.
# Revert: echo 0 > /sys/class/net/enp1s0/threaded
NIC=enp1s0
NAPI_PRIO=70
if [ -w /sys/class/net/$NIC/threaded ]; then
    echo 1 > /sys/class/net/$NIC/threaded
    pids=""
    for _ in $(seq 20); do
        pids=$(pgrep "^napi/$NIC")
        [ -n "$pids" ] && break
        sleep 0.5
    done
    # Also cover a threaded IRQ handler if a future driver/kernel provides one.
    # (comm is matched via ps: pgrep refuses patterns over 15 chars.)
    pids="$pids $(ps -eo pid=,comm= | awk -v n="$NIC" '$2 ~ "^irq/[0-9]+-" n "$" {print $1}')"
    for p in $pids; do
        chrt -f -p $NAPI_PRIO "$p" && echo "RT FIFO $NAPI_PRIO: $(cat /proc/$p/comm) (pid $p)"
    done
    if [ -z "${pids// /}" ]; then
        echo "WARNING: no napi/irq thread found for $NIC"
    fi
else
    echo "WARNING: /sys/class/net/$NIC/threaded not available"
fi

exit 0
