#!/bin/bash
# RT tuning for LinuxCNC + Mesa hm2_eth on enp1s0.
# Run once manually: sudo bash set-cpu-performance.sh
# Or install the systemd service: sudo systemctl enable --now cpu-performance.service

# 1. CPU governor: lock at max frequency to eliminate SMI latency spikes
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
echo "CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

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
    pids="$pids $(pgrep "^irq/[0-9]+-$NIC")"
    for p in $pids; do
        chrt -f -p $NAPI_PRIO "$p" && echo "RT FIFO $NAPI_PRIO: $(cat /proc/$p/comm) (pid $p)"
    done
    [ -z "${pids// /}" ] && echo "WARNING: no napi/irq thread found for $NIC"
else
    echo "WARNING: /sys/class/net/$NIC/threaded not available"
fi
