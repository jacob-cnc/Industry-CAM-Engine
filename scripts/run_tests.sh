#!/bin/bash
# Run the test suite on the lathe's runtime (requirements-lathe.txt): Debian's
# /usr/bin/python3 3.11 with the ~/.local packages - exactly what the GUI runs.
# Refuses while LinuxCNC is up (tests/conftest.py also enforces it).
#
#   scripts/run_tests.sh                 # whole suite
#   scripts/run_tests.sh tests/unit -x   # any pytest arguments
set -u
cd "$(dirname "$0")/.."
for p in milltask rtapi_app linuxcncsvr; do
    if pgrep -x "$p" >/dev/null; then
        echo "LinuxCNC is running ($p): shut it down before running the tests." >&2
        exit 3
    fi
done
[ $# -eq 0 ] && set -- tests
exec env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH QT_QPA_PLATFORM=offscreen \
    timeout 1800 nice -n 10 /usr/bin/python3 -m pytest -q -p no:cacheprovider -rf "$@"
