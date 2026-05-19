# Session Notes: 2026-05-18 — Commissioning ESTOP Debug

## Status at end of session

**UNRESOLVED — Machine stuck in ESTOP, could not complete test before session limit.**

LinuxCNC was loading (terminal showing hm2 init + task slow loops) when session ended.
The Python state diagnostic was run BEFORE this restart so the result (still state=1) is from the old session.

---

## What was fixed this session

### 1. CPU governor (SOLVED)
- `powersave` governor was causing RT latency spikes → changed to `performance`
- Added `set-cpu-performance.sh` and `cpu-performance.service` (systemd unit)
- **Still TODO:** `sudo systemctl enable --now cpu-performance.service` to persist across reboots

### 2. SERVO_PERIOD (SOLVED)
- 1ms was too tight for hm2_eth → changed to 2ms in `industry-cam.ini`
- `hm2/hm2_7i96s.0: error finishing read!` errors gone

### 3. E-stop bypass (SOLVED — hardware)
- Old approach `net estop-loop user-enable-out => emc-enable-in` is a deadlock in LinuxCNC 2.9
- Replaced with `and2.estop-bypass` component with both inputs hardwired to 1
- `iocontrol.0.emc-enable-in = TRUE` confirmed by halcmd

### 4. Jog guard (SOLVED)
- MPG jog commands were spamming NML in ESTOP state
- Added `_machine_is_on()` guard to `jog_continuous`, `jog_stop`, `jog_increment` in `hal/live_backend.py`

### 5. Button hover styles (COSMETIC FIX)
- Reset and ON buttons had no hover/pressed visual feedback
- Fixed in `gui/manual/sections.py`

### 6. postgui.hal simplified (HYPOTHESIS — not yet tested)
- Old postgui.hal loaded `mux_generic` and tried to connect `compound-slide.*` pins
- Conda's python3 has the WRONG `hal` module (not LinuxCNC's) — so `hal.component("compound-slide")` silently fails
- compound-slide pins never get created → postgui.hal fails at first `net ... compound-slide.*` command
- A postgui.hal failure in LinuxCNC 2.9 is FATAL — leaves machine in permanent ESTOP
- **FIX:** Rewrote postgui.hal to route MPG counts directly to joints (no compound-slide, no mux_generic)
- **TEST STILL NEEDED** — was restarting LinuxCNC when session ended

---

## Key diagnostic findings

- `iocontrol.0.emc-enable-in = TRUE` (confirmed multiple times)
- `iocontrol.0.user-enable-out` goes TRUE after clicking Reset (iocontrol processes command)
- `task_state` stays at 1 (ESTOP) regardless — never transitions to 2 (ESTOP_RESET) or 4 (ON)
- `c.state(linuxcnc.STATE_ESTOP_RESET)` accepted by NML but has no effect
- GUI running in "offline preview mode" for pin providers — wrong hal module in conda

---

## Next session: what to do first

1. **Start LinuxCNC from terminal:** `~/linuxcnc/configs/industry-cam/launch_gui.sh`
2. **Wait for GUI to appear** (task slow loops will print, then stop)
3. **Test ESTOP transition** from second terminal:
   ```bash
   /usr/bin/python3 -c "
   import linuxcnc, time
   c = linuxcnc.command()
   s = linuxcnc.stat()
   s.poll()
   print('State before:', s.task_state)
   c.state(linuxcnc.STATE_ESTOP_RESET)
   time.sleep(0.5)
   s.poll()
   print('After RESET:', s.task_state)
   c.state(linuxcnc.STATE_ON)
   time.sleep(0.5)
   s.poll()
   print('After ON:', s.task_state)
   "
   ```
4. **Expected if fix worked:** `2` then `4` instead of `1` all the way
5. **If still stuck at 1:** check `halcmd show pin iocontrol` for all pin values, and paste the full terminal output from launch_gui.sh

---

## If ESTOP is fixed: next commissioning steps

1. Home both axes (home-in-place, just zero the DROs)
2. Test MPG jogging — turn X handwheel slowly, verify axis moves
3. Check direction: clockwise = positive direction? Verify with encoder feedback
4. Tune PID if needed (P=500, FF1=1.0 initial — likely needs adjustment)
5. Enable cpu-performance.service for boot persistence

---

## Outstanding issues (not blocking commissioning)

- **Compound-slide / conda hal module:** `import hal` in conda gets wrong module.
  Fix: add `/usr/lib/python3/dist-packages` to PYTHONPATH in `display_gui.sh` before `exec python3`.
  Or better: restructure compound-slide to not need a persistent HAL component at all.
  Low priority — compound slide is for taper cutting, not needed for basic operation.

- **Hardware E-stop wiring:** gpio.004 is connected (NC button, TB3 P5).
  When ready to wire: replace `net estop-always-enabled and2.estop-bypass.out => iocontrol.0.emc-enable-in`
  with `net estop-ext hm2_7i96s.0.gpio.004.in => iocontrol.0.emc-enable-in`
  Note: use `.in` (not `.in_not`) — button NC means `.in` is HIGH when released = safe.

- **Home/limit switches:** not wired. Current HAL has HOME_SEARCH_VEL=0 (home in place).
  When wired: use `.in` (not `.in_not`), uncomment nets in industry-cam.hal sections 7.

- **Jog buttons / cycle start-stop:** not wired (TB3 P6-P11).

---

## File state summary (what changed this session)

| File | Change |
|------|--------|
| `industry-cam.hal` | and2.estop-bypass added, SERVO_PERIOD comments |
| `industry-cam.ini` | SERVO_PERIOD=2ms, JOINT_0/1 FERROR loosened, [EMCIO] added |
| `postgui.hal` | **SIMPLIFIED** — direct MPG routing, no compound-slide |
| `hal/live_backend.py` | machine_is_on guard, state logging, error drain |
| `gui/manual/sections.py` | Button hover/pressed styles fixed |
| `set-cpu-performance.sh` | New — RT tuning script |
| `cpu-performance.service` | New — systemd unit for RT tuning |
