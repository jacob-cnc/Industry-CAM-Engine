# Industry CAM Engine — Machine Commissioning Guide

## What This Is

This folder contains the LinuxCNC configuration files for your CNC lathe. When you copy this folder to your LinuxCNC computer and launch LinuxCNC pointing at `industry-cam.ini`, it will control your machine.

**Your machine:**
- CQ6133 2-axis lathe (X cross-slide, Z carriage)
- Mesa 7i96s ethernet motion controller + 7i85s daughter card
- UIRobot UIM8696PM closed-loop integrated steppers (48V)
- Sino KA300/KA500 linear encoders (5µm resolution) on both axes
- Manual spindle with rotary encoder for threading
- 2 MPG handwheels, 4 jog buttons, home switches, E-stop

---

## File Inventory

| File | Purpose |
|------|---------|
| `industry-cam.ini` | Main machine configuration — axis limits, velocities, PID values, homing |
| `industry-cam.hal` | HAL wiring — connects Mesa hardware pins to LinuxCNC motion controller |
| `custom.hal` | Your custom additions (empty for now) |
| `postgui.hal` | Connections that need the GUI running first (compound slide routing) |
| `industry-cam.var` | Persistent parameters (G54 offsets, etc.) — auto-updated by LinuxCNC |
| `launch_gui.sh` | Script that starts the Industry CAM Engine GUI |

---

## First-Time Setup on the LinuxCNC Computer

### Step 1: Copy Files

Copy this entire `linuxcnc/` folder to your LinuxCNC computer. The standard location is:

```
/home/linuxcnc/linuxcnc/industry-cam/
```

So you'd have:
```
/home/linuxcnc/linuxcnc/industry-cam/industry-cam.ini
/home/linuxcnc/linuxcnc/industry-cam/industry-cam.hal
/home/linuxcnc/linuxcnc/industry-cam/custom.hal
/home/linuxcnc/linuxcnc/industry-cam/postgui.hal
/home/linuxcnc/linuxcnc/industry-cam/industry-cam.var
/home/linuxcnc/linuxcnc/industry-cam/launch_gui.sh
/home/linuxcnc/linuxcnc/industry-cam/gui/   (the GUI application)
```

### Step 2: Make the Launch Script Executable

```bash
chmod +x /home/linuxcnc/linuxcnc/industry-cam/launch_gui.sh
```

### Step 3: Verify Mesa Board Communication

Before launching LinuxCNC, confirm the Mesa 7i96s is reachable:

```bash
ping 192.168.1.121
```

You should get replies. If not:
- Check the ethernet cable between the PC and the 7i96s
- The PC's ethernet port must be configured with a static IP on the same subnet (e.g., 192.168.1.100, netmask 255.255.255.0)
- The 7i96s default IP is 192.168.1.121

### Step 4: Verify Mesa Firmware

```bash
mesaflash --device 7i96s --addr 192.168.1.121 --readhmid
```

This should show your firmware configuration including stepgens, encoders, and GPIO. You need the `7i96s_7i85sd.bin` firmware (or equivalent that provides 5 encoders + 2 stepgens + sserial).

### Step 5: Launch LinuxCNC

```bash
linuxcnc /home/linuxcnc/linuxcnc/industry-cam/industry-cam.ini
```

If everything is configured correctly, the GUI will appear. If it errors, read the error message carefully — it usually tells you exactly which HAL pin or signal has a problem.

---

## First Power-On Procedure

**IMPORTANT: Read this entire section before turning anything on.**

### Safety Checklist

- [ ] E-stop button is accessible and you know where it is
- [ ] Spindle is OFF (manual switch in off position)
- [ ] No tools in the tool post (or tool is clear of workpiece)
- [ ] Both axes have clearance to move without hitting anything
- [ ] 48V stepper power supply is OFF (turn on last)

### Power-On Sequence

1. **Turn on 5V power supply** — powers the Mesa boards and encoders
2. **Turn on 24V power supply** — powers the control logic, buttons, switches
3. **Wait 3 seconds** — let the Mesa boards boot and establish ethernet
4. **Launch LinuxCNC** (see Step 5 above)
5. **Verify the GUI loads without errors**
6. **Check E-stop** — press E-stop, confirm LinuxCNC shows ESTOP state. Release, reset in GUI.
7. **Turn on 48V power supply** — now the steppers have power
8. **Machine On** — click Machine On in the GUI (or press the physical button if wired)

### What "Machine On" Does

When you click Machine On:
- LinuxCNC enables the stepper drives (via the `amp-enable` signal)
- The PID loops activate
- The encoders start being read
- The machine is now ready to accept motion commands

**If the machine immediately faults with a "following error" message:**
- This means the encoder is reading a position that doesn't match what the stepgen commanded
- Most likely cause: encoder wired backwards (counting in wrong direction)
- See "Encoder Direction Verification" below

---

## Encoder Direction Verification

This is the FIRST thing to check after power-on. If the encoder counts in the opposite direction from the stepgen, the PID loop will have positive feedback and the axis will run away or immediately fault.

### How to Check

1. Launch LinuxCNC
2. Open the HAL Monitor tab (Setup → HAL Monitor)
3. Add these pins to the watch list (double-click each):
   - `pid.x.command`
   - `pid.x.feedback`
   - `pid.x.error`
   - `hm2_7i96s.0.encoder.00.position`
4. Machine On
5. Jog X+ very slowly (use the slowest jog speed, or 0.0001" MPG increment)
6. Watch the values:

**CORRECT behavior:**
- `pid.x.command` increases (you commanded positive motion)
- `encoder.00.position` increases (encoder agrees)
- `pid.x.error` stays small (< 0.001") and returns toward zero

**WRONG behavior (encoder backwards):**
- `pid.x.command` increases
- `encoder.00.position` DECREASES
- `pid.x.error` grows rapidly
- Machine faults with following error

### How to Fix Wrong Direction

If the encoder is counting backwards, you have two options:

**Option A: Negate the encoder scale in the INI file**

Open `industry-cam.ini` and change:
```ini
# In [JOINT_0] for X axis:
ENCODER_SCALE = -5080    # was 5080, now negative

# In [JOINT_1] for Z axis:
ENCODER_SCALE = -5080    # was 5080, now negative
```

**Option B: Swap the A and B encoder wires**

On the 7i85s TB1 connector, swap the A and B channel wires for the affected encoder. This physically reverses the count direction.

**Option A is easier and doesn't require rewiring.** Do one axis at a time.

### Repeat for Z Axis

Do the same check for Z:
- Watch `pid.z.command`, `pid.z.feedback`, `pid.z.error`, `encoder.01.position`
- Jog Z+ slowly
- Confirm error stays small and returns to zero

---

## PID Tuning

Once encoder direction is confirmed correct, you can tune the PID loop. The config ships with conservative values (P=500, FF1=1.0) that should work without oscillation but may be sluggish.

### What the PID Values Mean

| Parameter | What It Does | Starting Value | Notes |
|-----------|-------------|----------------|-------|
| **P** (Proportional) | Corrects position error. Higher = more responsive but can oscillate. | 500 | The main knob to turn |
| **I** (Integral) | Eliminates steady-state error over time. | 0 | Leave at 0 for steppers |
| **D** (Derivative) | Dampens oscillation. | 0 | Rarely needed for steppers |
| **FF0** | Position feedforward | 0 | Leave at 0 |
| **FF1** | Velocity feedforward | 1.0 | **CRITICAL — must be 1.0 for velocity-mode stepgen** |
| **FF2** | Acceleration feedforward | 0 | Leave at 0 |
| **Deadband** | Ignore errors smaller than this | 0.0001" | Prevents hunting on encoder noise |
| **Max Output** | Clamp PID output velocity | 2.5 in/sec | Prevents runaway |

### The Tuning Procedure

1. Open the **Setup → Tuning** tab in the GUI
2. Click **Load from INI** to populate fields with current values
3. Watch the **Following Error graph** — it shows real-time deviation between commanded and actual position
4. Jog an axis back and forth at moderate speed (0.5–1.0 in/sec)
5. Observe the following error:
   - **Error is large but stable (no oscillation):** Increase P gain
   - **Error oscillates (bounces back and forth):** Decrease P gain
   - **Error is small and settles quickly:** You're done

### Step-by-Step P Gain Tuning

1. Start at P = 500 (the shipped default)
2. Jog X back and forth. Watch the error graph.
3. If error is > 0.002" during motion and settles slowly:
   - Increase P to 750
   - Jog again, observe
4. If error is < 0.001" and settles quickly with no ringing:
   - Try P = 1000
   - If it starts to oscillate (error bounces ±), back off to 800
5. The sweet spot is usually where the error settles in 2-3 servo cycles without overshoot

### Applying Changes

- **Apply Live** button: Pushes PID gains to HAL immediately (no restart needed). Use this for rapid iteration.
- **Save to INI** button: Writes values to the INI file. Requires LinuxCNC restart to take effect. Do this once you're happy with the values.

### Deadband Tuning

After P gain is set:
1. Let the axis sit still (no motion commanded)
2. Watch `pid.x.error` — it should be very small (< 0.0001")
3. If the error constantly fluctuates and the stepgen is "hunting" (making tiny corrections):
   - Increase deadband from 0.0001" to 0.0002"
   - This tells the PID "ignore errors smaller than this"
4. The deadband should be larger than your encoder noise but smaller than your acceptable positioning error
5. For 5µm (0.000197") encoders, a deadband of 0.0001" to 0.0002" is typical

### What "Good" Looks Like

After tuning, you should see:
- Following error < 0.001" during motion at full speed (2 in/sec)
- Following error < 0.0002" at rest
- No oscillation or hunting
- Error returns to near-zero within 50-100ms after motion stops
- No FERROR faults during rapid moves

---

## Tightening Following Error Limits

The config ships with relaxed FERROR limits (0.050" / 0.010") so you don't fault during initial tuning. Once PID is tuned and stable:

1. Open `industry-cam.ini`
2. Change both JOINT_0 and JOINT_1:
```ini
# Production values (tighten after tuning is complete):
FERROR = 0.005
MIN_FERROR = 0.001
```
3. Restart LinuxCNC
4. Run at full speed — if it faults, your PID needs more tuning or your FERROR is too tight

**What FERROR and MIN_FERROR mean:**
- `FERROR` = maximum allowed following error at full speed (2 in/sec)
- `MIN_FERROR` = maximum allowed following error at zero speed (at rest)
- LinuxCNC interpolates between these based on current velocity
- If the actual following error exceeds the limit, the machine faults (emergency stop)

---

## Step Scale Verification

The step scale values in the INI (54186.667 for X, 27093.333 for Z) are calculated from motor specs and leadscrew pitch. Real machines have tolerances, so you should verify:

### How to Verify

1. Home the machine (or note the current DRO position)
2. Place a dial indicator against the cross-slide (for X) or carriage (for Z)
3. Zero the indicator
4. Command a 1.000" move via MDI: `G91 G0 X1.0` (for X) or `G91 G0 Z1.0` (for Z)
5. Read the dial indicator

**If the indicator reads exactly 1.000":** Your step scale is correct.

**If the indicator reads 0.998" (short):** Your step scale is too low. Increase it:
```
New scale = Old scale × (commanded / actual)
New scale = 54186.667 × (1.000 / 0.998) = 54295.0
```

**If the indicator reads 1.002" (long):** Your step scale is too high. Decrease it.

### Important Notes

- For X axis, remember that the DRO shows DIAMETER but the indicator measures RADIUS. If you command `X1.0` (1" diameter), the cross-slide moves 0.5" (radius). Set your indicator accordingly.
- Do this test over at least 1" of travel. Longer is better (less percentage error from indicator reading).
- Do it in both directions to check for backlash.

---

## Homing (When You're Ready)

The config ships with homing in "test mode" — it homes at the current position without searching for a switch. This lets you jog and tune without needing to home first.

When you're ready to enable real homing:

1. Confirm home switches work:
   - Open HAL Monitor
   - Watch `debounce.0.0.out` (Z home) and `debounce.0.3.out` (X home)
   - Manually trigger each switch — confirm the pin toggles TRUE/FALSE

2. Edit `industry-cam.ini`:
```ini
# In [JOINT_0] (X axis):
HOME_SEARCH_VEL = 0.5       # Search toward X+ at 0.5 in/sec
HOME_LATCH_VEL = -0.05      # Back off slowly for precision
HOME_FINAL_VEL = 0           # No final move after latch

# In [JOINT_1] (Z axis):
HOME_SEARCH_VEL = -0.5      # Search toward Z- at 0.5 in/sec
HOME_LATCH_VEL = 0.05       # Back off slowly for precision
HOME_FINAL_VEL = 0
```

3. Also change in `[TRAJ]`:
```ini
NO_FORCE_HOMING = 0    # Require homing before auto mode
```

4. Restart LinuxCNC and test homing one axis at a time

### Homing Direction

- **X axis:** Homes toward X+ (away from centerline, toward the home switch at max travel)
- **Z axis:** Homes toward Z- (toward the headstock, where the Z home switch is)

If your switches are at different locations, flip the sign of `HOME_SEARCH_VEL`.

---

## Jog Speed and Increment

### Button Jogging (TB3 P6–P9)

The four jog buttons on the panel jog at a fixed speed. The default is 1.0 in/sec (60 IPM). You can change this:

- **From the GUI:** The Manual tab has a jog speed control
- **From the INI:** Not directly — it's set in the HAL file via `setp halui.axis.x.jog-speed`
- **Future:** The 7i73 panel card with a 6-position rotary switch will give you hardware speed selection

### MPG Jogging (Handwheels)

The MPG handwheels jog in increment mode — each click moves a fixed distance. The default increment is 0.001" per click.

To change the increment:
- **From the GUI:** The Manual tab has an increment selector
- **Future:** The 6-position rotary switch on the 7i73 panel will select: 0.0001, 0.0005, 0.001, 0.005, 0.010, 0.050

---

## Troubleshooting

### "Following error on joint 0" (or joint 1)

**What it means:** The actual position (from encoder) is too far from the commanded position.

**Common causes:**
1. Encoder wired backwards (see Encoder Direction Verification above)
2. PID not tuned (P too low = sluggish response = large error during motion)
3. Mechanical binding (axis physically can't move freely)
4. Stepper stalling (48V supply voltage too low, or acceleration too high)
5. FERROR limit too tight for current tuning state

**Quick fix:** Widen FERROR in the INI to 0.050" / 0.010" and restart. Then tune PID.

### Machine won't jog

**Check in order:**
1. Is the machine in ESTOP? (Reset E-stop, then Machine On)
2. Is the machine ON? (Click Machine On in GUI)
3. Are you in Manual mode? (Must be in Manual to jog)
4. Is `NO_FORCE_HOMING = 1` in the INI? (If 0, you must home before jogging)
5. Check `halui.joint.0.jog-speed` in HAL Monitor — is it > 0?

### Steppers don't move but no error

**Check:**
1. Is 48V power supply on?
2. Are stepper enable wires connected? (Blue wire to 24V+, Brown to 24V-)
3. Check `hm2_7i96s.0.stepgen.01.enable` in HAL Monitor — should be TRUE when machine is on
4. Check `pid.x.output` — is it non-zero when you command motion?

### Encoder reads zero and never changes

**Check:**
1. Is 5V power reaching the encoder? (Check +5V wire on 7i85s TB1)
2. Are A and B channels connected? (Check wiring against the pinout in wiring-map.md)
3. Is the encoder scale set? Check `hm2_7i96s.0.encoder.00.scale` in HAL Monitor — should be 5080
4. Manually push the axis by hand (with steppers disabled) — does the encoder count change?

### GUI won't launch

**Check:**
1. Is Python 3 installed? (`python3 --version`)
2. Is PyQt5 installed? (`python3 -c "import PyQt5"`)
3. Are all GUI dependencies installed? (`pip3 install -r requirements.txt`)
4. Check the terminal output for the actual Python error message

### Mesa board not found

**Check:**
1. `ping 192.168.1.121` — does it respond?
2. Is the ethernet cable plugged into the correct port? (Must be the port configured with static IP)
3. Is the PC's ethernet configured as static 192.168.1.100 / 255.255.255.0?
4. Is the 5V power supply on? (Mesa boards need 5V to boot)
5. Try `mesaflash --device 7i96s --addr 192.168.1.121 --readhmid` — does it respond?

---

## Key Numbers to Remember

| Parameter | X Axis | Z Axis | Units |
|-----------|--------|--------|-------|
| Max velocity | 2.0 | 2.0 | in/sec |
| Max acceleration | 10.0 | 10.0 | in/sec² |
| Travel | 0 to 4.25 | 0 to 23.5 | inches |
| Step scale | 54186.667 | 27093.333 | steps/inch |
| Encoder scale | 5080 | 5080 | counts/inch |
| Encoder resolution | 0.000197 | 0.000197 | inches (5µm) |
| FERROR (tuning) | 0.050 | 0.050 | inches |
| FERROR (production) | 0.005 | 0.005 | inches |
| Stepgen → Joint | stepgen.01 | stepgen.00 | **REVERSED!** |

---

## The Stepgen/Joint Reversal (Important!)

This is the most confusing thing about this machine's configuration:

```
Joint 0 (X axis) → uses stepgen.01 (TB1 Step/Dir slot 1)
Joint 1 (Z axis) → uses stepgen.00 (TB1 Step/Dir slot 0)
```

This is because the Z stepper was physically wired to the first step/dir output on TB1, and X to the second. The HAL file handles this mapping — you don't need to think about it during normal operation. But if you're debugging HAL signals, remember:

- `stepgen.00` anything = **Z axis**
- `stepgen.01` anything = **X axis**
- `encoder.00` = **X linear scale**
- `encoder.01` = **Z linear scale**

---

## Compound Slide (Virtual)

The GUI includes a virtual compound slide feature that decomposes single-handwheel motion into coordinated X+Z movement along an angle. This is used for:
- Threading infeed at 29.5°
- Taper turning
- Any angled approach

The compound slide is controlled entirely from the GUI. The `postgui.hal` file wires the MPG encoder counts through the compound-slide component. When compound mode is OFF, MPG counts pass through unchanged. When ON, they're decomposed trigonometrically.

**You don't need to do anything to set this up** — it works automatically when the GUI loads.

---

## Future Hardware (Not Yet Wired)

These items are planned but not yet physically connected:

| Item | What It Does | Where It Connects |
|------|-------------|-------------------|
| Mesa 7i73 panel card | Rotary switches, override pots, panel LEDs | 7i85s RS-422 serial port |
| 6-position jog increment knob | Select MPG increment (0.0001–0.050") | 7i73 digital inputs 0–5 |
| 6-position jog speed knob | Select button jog speed (6–120 IPM) | 7i73 digital inputs 6–11 |
| Feed override pot | Continuous 0–200% feed rate control | 7i73 analog input 0 |
| Spindle override pot | Continuous 25–150% spindle override | 7i73 analog input 1 |
| Panel LEDs | Machine on, homed, running, estop indicators | 7i73 digital outputs |
| Cycle pause button | Pause running program | 7i85s GPIO (gpio.011) |

When you're ready to add these, see the `7i73-panel-integration.md` steering file for full wiring and HAL details.

---

## Getting Help

- **LinuxCNC Forum:** https://forum.linuxcnc.org/ — the Mesa boards subforum is very active
- **Mesa Documentation:** http://mesanet.com/ — board manuals and firmware files
- **HAL Manual:** http://linuxcnc.org/docs/stable/html/hal/hal-tutorial.html
- **INI Reference:** http://linuxcnc.org/docs/stable/html/config/ini-config.html
