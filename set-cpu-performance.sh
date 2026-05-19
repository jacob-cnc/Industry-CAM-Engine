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
