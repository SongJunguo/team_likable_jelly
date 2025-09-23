#!/usr/bin/env bash
# Kill stuck Python multiprocessing children started via spawn/forkserver.
# Default pattern matches processes like:
#   python -c 'from multiprocessing.spawn import spawn_main; ...'
# Usage:
#   bash scripts/kill_multiprocessing_zombies.sh            # use default pattern
#   bash scripts/kill_multiprocessing_zombies.sh "python.*spawn_main"   # custom pattern
#   bash scripts/kill_multiprocessing_zombies.sh "^/opt/miniconda3/envs/opensky/bin/python .*spawn_main"

set -euo pipefail

PATTERN=${1:-"python .*spawn_main"}

echo "[cleanup] Looking for processes matching: $PATTERN"
# Collect matching PIDs (ignore the grep itself)
mapfile -t PIDS < <(pgrep -f "$PATTERN" || true)

if [[ ${#PIDS[@]} -eq 0 ]];
then
  echo "[cleanup] No matching processes found."
  exit 0
fi

echo "[cleanup] Found ${#PIDS[@]} processes: ${PIDS[*]}"
echo "[cleanup] Preview (pid ppid %cpu %mem etime cmd):"
ps -o pid,ppid,pcpu,pmem,etime,cmd -p "${PIDS[@]}" --no-headers || true

read -r -p "Send SIGTERM to these processes? [y/N] " ans
if [[ ! "$ans" =~ ^[Yy]$ ]]; then
  echo "[cleanup] Aborted by user."
  exit 1
fi

echo "[cleanup] Sending SIGTERM ..."
kill -s TERM "${PIDS[@]}" 2>/dev/null || true
sleep 3

# Check for leftovers
mapfile -t LEFT < <(pgrep -f "$PATTERN" || true)
if [[ ${#LEFT[@]} -eq 0 ]]; then
  echo "[cleanup] All processes exited cleanly."
  exit 0
fi

echo "[cleanup] Still alive: ${LEFT[*]}"
ps -o pid,ppid,pcpu,pmem,etime,cmd -p "${LEFT[@]}" --no-headers || true
read -r -p "Force kill with SIGKILL? [y/N] " ans2
if [[ ! "$ans2" =~ ^[Yy]$ ]]; then
  echo "[cleanup] Leaving remaining processes running."
  exit 2
fi

echo "[cleanup] Sending SIGKILL ..."
kill -s KILL "${LEFT[@]}" 2>/dev/null || true
sleep 1

mapfile -t FINAL < <(pgrep -f "$PATTERN" || true)
if [[ ${#FINAL[@]} -eq 0 ]]; then
  echo "[cleanup] Cleanup complete."
else
  echo "[cleanup] Some processes could not be killed: ${FINAL[*]}"
fi

