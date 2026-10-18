#!/usr/bin/env python3
"""Daily pipeline (cross-platform replacement for run_daily.sh): collect -> fetch_og -> build.
collect.py already applies dedupe on insert. Safe to re-run. Single-instance via lock file."""
import os, subprocess, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(BASE, "data", ".run.lock")
STALE_SEC = 3 * 3600

def step(name, required=True):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] == {name}", flush=True)
    rc = subprocess.call([sys.executable, os.path.join(BASE, name)], cwd=BASE)
    if rc and required:
        raise SystemExit(f"{name} failed (exit {rc})")
    if rc:
        print(f"[WARN] {name} failed (exit {rc}, continuing)", file=sys.stderr, flush=True)

def main():
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) > STALE_SEC:
        os.remove(LOCK)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("already running"); return
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        step("collect.py")
        step("fetch_og.py", required=False)
        step("build_html.py")
    finally:
        try: os.remove(LOCK)
        except OSError: pass

if __name__ == "__main__":
    main()
