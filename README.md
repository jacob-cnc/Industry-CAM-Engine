# Industry CAM Engine — Linux Deployment Package

This folder is the complete deployment package for your CNC lathe running LinuxCNC.
Everything needed to run the CAM engine, control the machine, and tune the servos is here.

**Target machine path:** `/home/jacob/linuxcnc/configs/industry-cam/`

---

## What's In This Package

```
industry-cam/
├── gui/                        ← Full GUI application
│   ├── commissioning/          ← Setup tab (HAL monitor, PID tuning, checklist)
│   ├── components/             ← Reusable widgets (graph, status bar, etc.)
│   ├── manual/                 ← Manual control tab (jog, MPG, DRO)
│   ├── main_window.py          ← Application entry point
│   ├── colors.py               ← Color theme
│   ├── program_tab.py          ← Conversational programming
│   ├── edit_tab.py             ← G-code editor
│   ├── tools_tab.py            ← Tool table management
│   └── debug_tab.py            ← Debug/diagnostics
├── models/                     ← Data structures (profiles, tools, moves)
├── tools/                      ← Tool geometry and reach analysis
├── geometry/                   ← Build123d zone construction (OCCT kernel)
├── intervals/                  ← Fiber/interval boundary finding
├── planners/                   ← Pass planning (staircase, face, finish, cleanup)
├── transitions/                ← Retract/approach logic between passes
├── validation/                 ← Shapely-based safety checking
├── outputs/                    ← G-code writer, graph adapter, DXF/SVG export
├── pipeline/                   ← Orchestration (wires all modules together)
├── hal/                        ← LinuxCNC HAL abstraction layer
│   ├── interface.py            ← Abstract backend (Live or Mock)
│   ├── live_backend.py         ← Real LinuxCNC connection
│   ├── mock_backend.py         ← Offline simulation (Windows dev)
│   ├── factory.py              ← Auto-selects Live or Mock
│   └── constants.py            ← Machine parameters
├── industry-cam.ini            ← LinuxCNC machine configuration
├── industry-cam.hal            ← HAL wiring (Mesa hardware → motion controller)
├── custom.hal                  ← Your custom HAL additions (empty, ready for use)
├── postgui.hal                 ← Post-GUI HAL (compound slide MPG routing)
├── industry-cam.var            ← Persistent parameters (G54 offsets, tool offsets)
├── launch_gui.sh               ← Script that starts the GUI
├── tool.tbl                    ← Tool table (tool offsets, nose radius, orientation)
├── industry-cam.desktop        ← Desktop shortcut file
├── install_desktop_icon.sh     ← Script to install the desktop shortcut
├── requirements.txt            ← Python dependencies
└── pyproject.toml              ← Project metadata
```

---

## Step-by-Step Installation

### Step 1: Copy This Folder to the LinuxCNC Machine

**Using a USB drive:**
1. Plug a USB drive into your Windows PC
2. Copy the entire contents of this folder onto the USB drive (into a folder called `industry-cam`)
3. Safely eject the USB
4. Plug the USB into your LinuxCNC computer
5. Open the file manager — the USB should appear in the sidebar
6. Copy the `industry-cam` folder to: `/home/jacob/linuxcnc/configs/`

When done, you should have:
```
/home/jacob/linuxcnc/configs/industry-cam/industry-cam.ini
/home/jacob/linuxcnc/configs/industry-cam/industry-cam.hal
/home/jacob/linuxcnc/configs/industry-cam/gui/main_window.py
... (all other files)
```

**Using SCP (if both machines are on the same network):**
```bash
scp -r /path/to/usb/industry-cam jacob@<machine-ip>:/home/jacob/linuxcnc/configs/
```

---

### Step 2: Open a Terminal

You need a terminal to run the setup commands. Here's how to open one:

- **Method 1:** Right-click on the desktop → "Open Terminal Here"
- **Method 2:** Press `Ctrl+Alt+T` (works on most Linux desktops)
- **Method 3:** Find "Terminal" in your applications menu (usually under System or Utilities)

You'll see a window with a blinking cursor. This is where you type commands.

---

### Step 3: Navigate to the Folder

Type this and press Enter:
```bash
cd /home/jacob/linuxcnc/configs/industry-cam
```

If you get "No such file or directory," double-check that you copied the folder to the right place. You can check with:
```bash
ls /home/jacob/linuxcnc/configs/
```
You should see `industry-cam` in the list.

---

### Step 4: Make Scripts Executable

Linux requires you to explicitly mark scripts as executable. Run these two commands:

```bash
chmod +x launch_gui.sh
chmod +x install_desktop_icon.sh
```

Nothing will print if it worked. If you get "Permission denied," try:
```bash
sudo chmod +x launch_gui.sh install_desktop_icon.sh
```
(Enter your password when prompted — characters won't show as you type, that's normal.)

---

### Step 5: Install Python Dependencies

The CAM engine needs several Python libraries. Install them all at once:

```bash
pip3 install -r requirements.txt
```

This downloads and installs the required packages. It may take 2-5 minutes and will show a lot of text scrolling by — that's normal.

**If you get "pip3: command not found":**
```bash
python3 -m pip install -r requirements.txt
```

**If you get "Permission denied":**
```bash
pip3 install --user -r requirements.txt
```

**If a specific package fails to install:**
Try installing it individually to see the error:
```bash
pip3 install build123d
pip3 install PyQt5
pip3 install pyqtgraph
```

---

### Step 6: Install the Desktop Icon

This creates a clickable shortcut on your desktop so you don't need the terminal every time:

```bash
./install_desktop_icon.sh
```

You should see:
```
✓ Desktop icon installed at /home/jacob/Desktop/industry-cam.desktop
✓ Application menu entry installed
```

**If the icon doesn't work when you double-click it:**
1. Right-click the icon on your desktop
2. Look for "Allow Launching" or "Trust and Launch" or "Properties → Permissions → Allow executing"
3. Click it, then try double-clicking again

**If you don't see the icon on your desktop:**
Some Linux desktops don't show desktop files by default. You can always launch from the terminal (Step 7) or find "Industry CAM Engine" in your applications menu.

---

### Step 7: Verify Mesa Board Communication

Before launching LinuxCNC, make sure the Mesa 7i96s is reachable:

```bash
ping 192.168.1.121
```

You should see replies like:
```
64 bytes from 192.168.1.121: icmp_seq=1 ttl=64 time=0.2 ms
```

Press `Ctrl+C` to stop the ping.

**If you get "Destination Host Unreachable" or no response:**
- Check the ethernet cable between the PC and the 7i96s
- The PC's ethernet port must have a static IP on the same subnet
- Configure it as: IP = `192.168.1.100`, Netmask = `255.255.255.0`, Gateway = blank
- The 7i96s default IP is `192.168.1.121`
- Make sure the 5V power supply is on (Mesa boards need power to respond to ping)

---

### Step 8: Launch LinuxCNC

**Option A — Double-click the desktop icon** (if you installed it in Step 6)

**Option B — From the terminal:**
```bash
linuxcnc /home/jacob/linuxcnc/configs/industry-cam/industry-cam.ini
```

**Option C — From the LinuxCNC picker:**
If you use the LinuxCNC application picker (the default launcher), your config should appear in the list. If it doesn't, use Option B.

The Industry CAM Engine GUI should appear with tabs: Program, Edit, Tools, Debug, Run, Manual, Setup, Help.

---

## Setting Up the Desktop Icon — Detailed Guide

The desktop icon lets you launch the entire system (LinuxCNC + your custom GUI) with a single double-click. Here's exactly what happens behind the scenes and how to troubleshoot:

### What the Desktop Icon Does

The file `industry-cam.desktop` tells Linux:
- **Name:** "Industry CAM Engine" (what shows under the icon)
- **Command:** `linuxcnc /home/jacob/linuxcnc/configs/industry-cam/industry-cam.ini`
- **Working directory:** `/home/jacob/linuxcnc/configs/industry-cam`
- **Icon:** Uses the standard LinuxCNC icon

When you double-click it, Linux runs that command — which starts LinuxCNC, which reads the INI file, which loads the HAL files, which then launches your custom GUI via `launch_gui.sh`.

### Manual Desktop Icon Setup (If the Script Doesn't Work)

If `install_desktop_icon.sh` didn't work for any reason, you can do it manually:

1. Copy the desktop file to your desktop:
```bash
cp /home/jacob/linuxcnc/configs/industry-cam/industry-cam.desktop ~/Desktop/
```

2. Make it executable:
```bash
chmod +x ~/Desktop/industry-cam.desktop
```

3. On some desktops (XFCE, MATE), you also need to right-click the icon and select "Allow Launching" or check "Trust this executable" in Properties.

### Adding to the Applications Menu

The install script also puts the icon in your applications menu. If you want to do this manually:

```bash
mkdir -p ~/.local/share/applications
cp /home/jacob/linuxcnc/configs/industry-cam/industry-cam.desktop ~/.local/share/applications/
```

You'll find "Industry CAM Engine" in your applications menu under Manufacturing or Engineering categories. If it doesn't appear immediately, log out and back in.

### Customizing the Icon Image

The desktop file uses `Icon=linuxcnc` which shows the standard LinuxCNC logo. If you want a custom icon:

1. Save a PNG image (e.g., `industry-cam-icon.png`) to the configs folder
2. Edit `industry-cam.desktop` and change the Icon line:
```
Icon=/home/jacob/linuxcnc/configs/industry-cam/industry-cam-icon.png
```

---

## First Power-On — Complete Procedure

**READ THIS ENTIRE SECTION BEFORE TURNING ANYTHING ON.**

### Before You Start — Safety Checklist

- [ ] E-stop mushroom button is within arm's reach
- [ ] Spindle is OFF (manual switch in off position)
- [ ] No tools in the tool post (or tool is clear of any workpiece)
- [ ] Both axes have clearance to move their full travel without hitting anything
- [ ] Chuck jaws are clear of the cross-slide
- [ ] 48V stepper power supply is OFF (you'll turn it on last)
- [ ] You know which direction is X+ and Z+ on your machine

### Power-On Sequence (Order Matters!)

1. **Turn on 5V power supply** — this powers the Mesa boards and encoders
   - The 7i96s green LED should come on
   - Wait 2-3 seconds for the FPGA to boot

2. **Turn on 24V power supply** — this powers control logic, buttons, switches
   - E-stop circuit is now live
   - Jog buttons, home switches, and cycle buttons are powered

3. **Verify Mesa communication** — from a terminal:
   ```bash
   ping 192.168.1.121
   ```
   You should get replies. If not, stop here and fix networking.

4. **Launch LinuxCNC** — double-click the desktop icon or:
   ```bash
   linuxcnc /home/jacob/linuxcnc/configs/industry-cam/industry-cam.ini
   ```

5. **Verify the GUI loads without errors** — you should see the full GUI with all tabs

6. **Test E-stop:**
   - Press the physical E-stop button
   - The GUI should show "ESTOP" state (red indicator)
   - Release/twist the E-stop button
   - Click "Reset E-Stop" in the GUI
   - The state should change to "ESTOP RESET"

7. **Turn on 48V power supply** — now the steppers have power
   - You may hear a slight hum or click as the stepper drivers energize

8. **Click "Machine On" in the GUI**
   - The state should change to "ON"
   - The PID loops are now active
   - Encoders are being read

**If the machine immediately faults with "following error":**
Don't panic. This usually means an encoder is counting in the wrong direction. See the Encoder Direction Verification section in the commissioning README (`linuxcnc/README.md` — also included in this package as the detailed commissioning guide).

---

## What Each Tab Does

| Tab | Purpose | When You Use It |
|-----|---------|-----------------|
| **Program** | Define part geometry, set cutting parameters, generate toolpaths | Creating a new part program |
| **Edit** | View/edit the generated G-code, syntax highlighting | Reviewing or tweaking G-code |
| **Tools** | Manage tool table (offsets, nose radius, orientation) | Setting up tools, touch-off |
| **Debug** | View plan results, zone data, validation status | Troubleshooting toolpath issues |
| **Run** | Program execution controls (future) | Running a program on the machine |
| **Manual** | Jog controls, MPG settings, DRO, spindle | Manual machine operation |
| **Setup** | HAL Monitor, PID Tuning, Commissioning Checklist | Machine setup and tuning |
| **Help** | Documentation (future) | — |

### The Setup Tab (Most Important for Commissioning)

The Setup tab has three sub-tabs:

**HAL Monitor** — Browse all HAL pins in a tree view, filter by category (PID, Stepgen, Encoders, etc.), add pins to a watch list with live value updates. Use this to verify signals are working.

**Tuning** — Real-time following error graph, PID parameter editor, Load from INI / Save to INI / Apply Live buttons. This is where you tune the servo loop.

**Commission** — 9-step guided checklist (Verify I/O → E-Stop → Jog → Home → Encoder → PID → FERROR → Spindle → Tool Change). Each step has pass/fail status and notes. Progress saves to a JSON file.

---

## File Descriptions

### LinuxCNC Configuration Files

| File | What It Does | When to Edit |
|------|-------------|--------------|
| `industry-cam.ini` | Defines everything about the machine: axis limits, velocities, PID gains, encoder scales, homing, FERROR limits | When tuning PID, changing FERROR, enabling homing, adjusting limits |
| `industry-cam.hal` | Wires Mesa hardware pins to LinuxCNC's motion controller. Defines the signal flow from encoders → PID → stepgens | Rarely — only if you change physical wiring |
| `custom.hal` | Your custom additions. Loaded after the main HAL file. | When adding new hardware (7i73 panel, coolant relay, etc.) |
| `postgui.hal` | Connections that need the GUI running first (compound slide MPG routing) | Rarely — only if compound slide logic changes |
| `industry-cam.var` | Persistent parameters — G54/G55 offsets, G92 offsets, tool length offsets. LinuxCNC updates this automatically. | Never edit manually — LinuxCNC manages it |
| `launch_gui.sh` | Shell script that starts the Python GUI. Referenced by the INI file's DISPLAY setting. | Only if you move the installation to a different path |
| `tool.tbl` | Tool table — defines tool numbers, X/Z offsets, nose radius, orientation | When adding/changing tools, after touch-off |

### Key INI Settings You'll Change During Commissioning

```ini
# In [JOINT_0] and [JOINT_1]:
P = 500.0              # PID proportional gain — tune this up
DEADBAND = 0.000100    # Ignore errors smaller than this
FERROR = 0.050         # Following error limit (relaxed for tuning)
MIN_FERROR = 0.010     # Following error at rest (relaxed for tuning)
ENCODER_SCALE = 5080   # Negate (-5080) if encoder direction is wrong

# In [TRAJ]:
NO_FORCE_HOMING = 1    # Set to 0 when you want to require homing
```

---

## Updating the Package

If you make changes to the source code on Windows and need to re-export:

1. On your Windows development machine, open a terminal in the project folder
2. Run:
```
python "Ship to LinuxPC\package_for_linux.py"
```
3. Copy the updated `Ship to LinuxPC/` contents to USB or SCP to the machine
4. On the Linux machine, replace the old files:
```bash
rm -rf /home/jacob/linuxcnc/configs/industry-cam/gui
rm -rf /home/jacob/linuxcnc/configs/industry-cam/hal
rm -rf /home/jacob/linuxcnc/configs/industry-cam/models
# ... etc for each module directory
# Then copy new files in
```

Or just delete the whole folder and re-copy (your `industry-cam.var` will be regenerated, but you'll lose any G54 offsets you've set — back it up first if needed).

---

## Troubleshooting

### LinuxCNC won't start — "HAL error" or "pin not found"

This usually means a HAL pin name in the config doesn't match what the Mesa firmware provides. Common causes:
- Wrong firmware loaded on the 7i96s
- The `sserial_port_0` config doesn't match your hardware

**Fix:** Run `mesaflash --device 7i96s --addr 192.168.1.121 --readhmid` to see what the firmware actually provides, and compare with what the HAL file expects.

### GUI launches but shows "OFFLINE — Demo Data" everywhere

The GUI couldn't connect to LinuxCNC. This happens if:
- You launched the GUI directly (`python3 gui/main_window.py`) instead of through LinuxCNC
- The `linuxcnc` Python module isn't importable

**Fix:** Always launch via `linuxcnc industry-cam.ini` — this starts the realtime system first, then launches the GUI.

### "Following error on joint 0" immediately on Machine On

Encoder direction is wrong. See the Encoder Direction Verification section in the commissioning guide (open Setup → Commission tab, or read the detailed README in the linuxcnc/ source folder).

**Quick fix:** In `industry-cam.ini`, change `ENCODER_SCALE = 5080` to `ENCODER_SCALE = -5080` for the affected joint. Restart LinuxCNC.

### Jog buttons don't work

Check in order:
1. Machine must be ON (not just ESTOP RESET)
2. Must be in Manual mode
3. `NO_FORCE_HOMING = 1` must be set in INI (it is by default in this config)
4. Open Setup → HAL Monitor, watch `halui.joint.0.jog-speed` — must be > 0

### MPG handwheel doesn't move the axis

1. Check encoder counts: Setup → HAL Monitor → watch `hm2_7i96s.0.encoder.03.count` (X MPG) or `.encoder.04.count` (Z MPG). Turn the wheel — count should change.
2. If count doesn't change: check 5V power to the MPG, check A/B wiring
3. If count changes but axis doesn't move: check `joint.0.jog-enable` is TRUE, check jog scale is > 0

### Python import errors on launch

If you see errors like "No module named 'build123d'" or "No module named 'PyQt5'":
```bash
cd /home/jacob/linuxcnc/configs/industry-cam
pip3 install -r requirements.txt
```

If that doesn't work, install packages individually:
```bash
pip3 install build123d shapely ezdxf PyQt5 pyqtgraph numpy matplotlib
```

---

## Getting Help

- **LinuxCNC Forum:** https://forum.linuxcnc.org/ (Mesa boards subforum is very active)
- **Mesa Documentation:** http://mesanet.com/ (board manuals, firmware files)
- **HAL Tutorial:** http://linuxcnc.org/docs/stable/html/hal/hal-tutorial.html
- **INI Reference:** http://linuxcnc.org/docs/stable/html/config/ini-config.html
- **LinuxCNC Wiki:** http://wiki.linuxcnc.org/
