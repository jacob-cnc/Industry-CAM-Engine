# 2026-11-09 — Lathe PC OS / real-time tuning

Machine-local OS changes on the lathe PC (Intel N150, 4 cores, Debian 12,
kernel `6.1.0-30-rt-amd64`, LinuxCNC 2.9.6, Mesa 7i96s on `enp1s0`).
None of these live in the repo; this note records them for troubleshooting.
All were applied by the owner with sudo; Claude only inspected read-only.

## Changes

| Change | Where | Why | Revert |
|---|---|---|---|
| Kernel cmdline: `isolcpus=2,3 irqaffinity=0,1 intel_idle.max_cstate=1 processor.max_cstate=1` | `/etc/default/grub` (`GRUB_CMDLINE_LINUX_DEFAULT`, was `"quiet"`), then `update-grub` | Keep RT threads (LinuxCNC uses CPU 3) away from desktop/IRQ load; N150 C10 exit latency is 660 µs, a large fraction of the 2 ms servo period | `sudo cp /etc/default/grub.bak /etc/default/grub && sudo update-grub`, reboot |
| Bluetooth service disabled | `systemctl disable --now bluetooth` | Not used; onboard Realtek BT (USB `0bda:b850`) can't be unplugged | `sudo systemctl enable --now bluetooth` |
| Bluetooth kernel modules blacklisted | `/etc/modprobe.d/disable-bluetooth.conf` (`blacklist btusb`, `blacklist bluetooth`) | Driver never loads. Modules aren't in the initramfs, so no initramfs rebuild needed | Delete file, reboot; radio was also rfkill soft-blocked: `sudo rfkill unblock bluetooth` |
| Background services disabled | `apt-daily.timer`, `apt-daily-upgrade.timer`, `cups`, `ModemManager`, `avahi-daemon` (+ its socket) | apt jobs could unpack packages mid-cycle; printing/modem/mDNS unused | `sudo systemctl enable --now <unit>`; run `sudo apt update && sudo apt upgrade` manually when the machine is idle |

Keyboard/mouse: Logitech keyboard and mouse use the Logi Bolt USB receiver
(`046d:c548`), paired with Solaar. No Bluetooth needed.

## Already in place before this session (unchanged)

- `cpu-performance.service` (enabled) runs `set-cpu-performance.sh`: performance
  governor, `pfifo_fast` qdisc on `enp1s0`, threaded NAPI for `enp1s0` at
  SCHED_FIFO 70. With `irqaffinity=0,1` / `isolcpus=2,3` the `napi/enp1s0-*`
  kthread runs on housekeeping CPUs 0–1.
- `irqbalance` not running; NIC interrupt coalescing `rx-usecs 0` on both NICs.
- Kernel package `linux-image-6.1.0-30-rt-amd64` is on apt **hold**. The
  `/lib/modules/6.1.0-40-*` directories are leftovers from removed kernels,
  not installed kernels.
- Mesa link: NetworkManager profile "MESA 7i96s", `enp1s0`, 192.168.1.1/24;
  board at 192.168.1.121. `industry-cam.ini` SERVO_PERIOD 2 ms, hm2 watchdog 5 ms.

## Verify after boot

```bash
cat /proc/cmdline                               # shows isolcpus/max_cstate args
cat /sys/devices/system/cpu/isolated            # 2-3
ls /sys/devices/system/cpu/cpu0/cpuidle/        # only shallow states listed / used
lsmod | grep -iE '^(btusb|bluetooth) '          # empty
systemctl is-enabled bluetooth cups ModemManager avahi-daemon apt-daily.timer
```

## Troubleshooting pointers

- If `hm2: error finishing read` or latency spikes appear after this, first
  confirm the cmdline actually applied (`/proc/cmdline`). If the PC runs hot
  or behaves oddly, the C-state limit is the first thing to revert.
- Measure jitter with `latency-histogram` **alone**: LinuxCNC closed, no
  pytest or other load. Running a latency test together with the test suite
  previously froze this PC.
- Optional further step not taken: disable onboard Bluetooth and C-states in BIOS.
