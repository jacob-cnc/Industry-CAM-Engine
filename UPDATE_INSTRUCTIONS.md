# Updating Industry CAM Engine on the Linux Machine

These instructions are for when you have a new revision on the USB drive
and want to update the Linux machine. This is NOT the first-time install —
see README.md for that.

---

## Quick Update (30 seconds)

Plug in the USB drive, then open a terminal and run:

```bash
cd /home/jacob/linuxcnc/configs

# Back up your machine state (offsets, tool table, tuning values)
cp industry-cam/industry-cam.var /tmp/industry-cam.var.bak
cp industry-cam/industry-cam.ini /tmp/industry-cam.ini.bak
cp industry-cam/tool.tbl /tmp/tool.tbl.bak

# Remove old code
rm -rf industry-cam

# Copy new revision from USB
# (Replace <USB> with your USB drive name — check file manager or run: ls /media/jacob/)
cp -r /media/jacob/<USB>/industry-cam .

# Restore your machine state
cp /tmp/industry-cam.var.bak industry-cam/industry-cam.var
cp /tmp/tool.tbl.bak industry-cam/tool.tbl

# Fix permissions (USB/FAT32 strips execute bits)
chmod +x industry-cam/launch_gui.sh industry-cam/display_gui.sh
```

Done. Double-click the desktop icon to launch.

---

## What Gets Preserved vs Replaced

| File | What happens | Why |
|------|-------------|-----|
| `industry-cam.var` | **PRESERVE** (backed up and restored) | Contains your G54/G55 offsets — losing these means re-touching-off |
| `tool.tbl` | **PRESERVE** (backed up and restored) | Contains your tool offsets — losing these means re-measuring tools |
| `industry-cam.ini` | **REPLACED** (but backup kept in /tmp) | May contain new PID values, FERROR changes, etc. from development. If you've tuned PID on the machine, merge your values back (see below) |
| Everything else | **REPLACED** | New code, new GUI, new features |

---

## If You've Tuned PID on the Machine

If you adjusted PID values (P, deadband, FERROR) on the machine and saved to INI,
those values are in your old `industry-cam.ini`. After updating:

1. Check if the new INI has different PID values:
```bash
diff /tmp/industry-cam.ini.bak industry-cam/industry-cam.ini
```

2. If your tuned values are better, copy them back:
```bash
# Open the new INI and paste your tuned values into [JOINT_0] and [JOINT_1]
nano industry-cam/industry-cam.ini
```

Or just restore the whole INI if you haven't changed anything on the dev side:
```bash
cp /tmp/industry-cam.ini.bak industry-cam/industry-cam.ini
```

---

## What You Do NOT Need to Redo

| Task | Needed again? | Why |
|------|--------------|-----|
| `pip3 install -r requirements.txt` | **No** | Python packages persist between updates |
| `./install_desktop_icon.sh` | **No** | Desktop icon points to the folder path, not file contents |
| "Allow Launching" on desktop icon | **No** | Permission is remembered |
| Network/Mesa setup | **No** | That's system config, not in this folder |

---

## When You DO Need to Re-Install Dependencies

Only if I tell you "a new library was added." You'll know because the app will crash with:
```
ModuleNotFoundError: No module named 'some_new_library'
```

Fix:
```bash
cd /home/jacob/linuxcnc/configs/industry-cam
pip3 install -r requirements.txt
```

---

## Finding Your USB Drive Path

If you're not sure what your USB drive is called:

```bash
ls /media/jacob/
```

This shows all mounted USB drives. The name is usually something like `USB_DRIVE` or `4GB_USB` or a random string. Use whatever shows up:

```bash
cp -r /media/jacob/WHATEVER_IT_SAYS/industry-cam /home/jacob/linuxcnc/configs/
```

---

## Emergency: Something Broke After Update

If the new version doesn't work and you need to go back:

```bash
# Your backups are in /tmp (they survive until reboot)
cd /home/jacob/linuxcnc/configs/industry-cam
cp /tmp/industry-cam.ini.bak industry-cam.ini
cp /tmp/industry-cam.var.bak industry-cam.var
cp /tmp/tool.tbl.bak tool.tbl
```

If the code itself is broken (Python errors), you'll need the previous USB revision.
Keep old USB copies around until you confirm the new version works.

---

## On the Windows Development Machine

To prepare a new revision for the USB drive:

1. Make your changes in the project
2. Run the packager:
```
python "Ship to LinuxPC\package_for_linux.py"
```
3. Copy `Ship to LinuxPC\` contents to the USB drive's `industry-cam` folder
4. Or if the D drive IS the USB: it's already there after the packager runs

The packager automatically:
- Cleans the output folder
- Copies all source modules (gui, models, planners, etc.)
- Copies LinuxCNC config files (INI, HAL, var, launch scripts)
- Removes test-only dependencies from requirements.txt
- Prints a summary of what was packaged
