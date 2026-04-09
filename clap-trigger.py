"""
Clap Trigger - launches workspace-launcher on double clap.

Installation:
    pip install sounddevice numpy

Usage:
    python clap-trigger.py
    python clap-trigger.py --calibrate
    python clap-trigger.py --threshold 70 --debug
    python clap-trigger.py --profile praca
"""

import argparse
import subprocess
import sys
import os
import time
import math

try:
    import sounddevice as sd
except ImportError:
    print("Missing sounddevice! pip install sounddevice")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("Missing numpy! pip install numpy")
    sys.exit(1)


# --- CONFIGURATION ---

DEFAULT_PROFILE = "default"

LAUNCHER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "workspace-launcher.ps1"
)

CLAP_THRESHOLD_DB = 75    # Min. clap volume (dB)
CLAP_MIN_GAP = 0.08       # Min. gap between claps (s) - fast claps
CLAP_MAX_GAP = 1.0        # Max. gap between claps (s)
COOLDOWN = 5.0             # Lock after trigger (s)

SAMPLE_RATE = 44100
BLOCK_SIZE = 2048

# --- END OF CONFIGURATION ---


def rms_db(data):
    """RMS in dB, normalized 0-96."""
    rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
    if rms < 1e-10:
        return 0.0
    return max(0.0, 20 * math.log10(rms) + 96)


def launch_workspace(profile):
    print(f"\n{'='*50}", flush=True)
    print(f"  DOUBLE CLAP! Launching: {profile}", flush=True)
    print(f"{'='*50}\n", flush=True)
    subprocess.Popen([
        "powershell.exe", "-ExecutionPolicy", "Bypass",
        "-File", LAUNCHER_SCRIPT, "-Profile", profile
    ])


def run_calibration(threshold):
    print("=" * 55)
    print("  CALIBRATION - clap a few times, then Ctrl+C")
    print(f"  Current threshold: {threshold} dB")
    print("=" * 55, flush=True)

    peak = 0.0

    def cb(indata, frames, t, status):
        nonlocal peak
        try:
            db = rms_db(indata[:, 0])
            peak = max(peak, db)
            bar = "#" * min(int(db / 2), 45)
            tag = " <<< CLAP!" if db >= threshold else ""
            print(f"\r  {db:5.1f} dB |{bar:<45}| peak:{peak:5.1f}{tag}   ", end="", flush=True)
        except Exception:
            pass

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, channels=1, callback=cb):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        lo = max(peak - 15, 50)
        hi = max(peak - 5, 60)
        print(f"\n\n  Peak: {peak:.0f} dB")
        print(f"  Suggested --threshold: {lo:.0f} to {hi:.0f}")
        print(f"\n  python clap-trigger.py --threshold {lo:.0f}")


def run_listener(profile, threshold, debug):
    print("=" * 50)
    print("  Clap Trigger")
    print("=" * 50)
    print(f"  Profile:    {profile}")
    print(f"  Threshold:  {threshold} dB")
    print(f"  Window:     {CLAP_MIN_GAP}-{CLAP_MAX_GAP}s")
    print(f"  Cooldown:   {COOLDOWN}s")
    if debug:
        print(f"  DEBUG:      ON")
    print()
    print("  Clap 2x to launch workspace!")
    print("-" * 50, flush=True)

    # Detection state - simple: remember time of last threshold crossings
    clap_times = []
    last_trigger = 0.0
    prev_db = 0.0

    def cb(indata, frames, t, status):
        nonlocal clap_times, last_trigger, prev_db

        try:
            db = rms_db(indata[:, 0])
            now = time.time()

            if debug:
                bar = "#" * min(int(db / 2), 40)
                print(f"\r  {db:5.1f} dB |{bar:<40}|   ", end="", flush=True)

            # Cooldown
            if now - last_trigger < COOLDOWN:
                prev_db = db
                return

            # Detection: transition from quiet to loud (rising edge)
            if db >= threshold and prev_db < threshold:
                # Clear old claps
                clap_times = [t for t in clap_times if now - t < CLAP_MAX_GAP]
                clap_times.append(now)

                count = len(clap_times)
                print(f"\n  [{'*' * count}] Clap #{count} ({db:.0f} dB)", flush=True)

                if count >= 2:
                    gap = clap_times[-1] - clap_times[-2]
                    if gap >= CLAP_MIN_GAP:
                        launch_workspace(profile)
                        last_trigger = now
                        clap_times = []
                    else:
                        print(f"      (too fast: {gap:.2f}s < {CLAP_MIN_GAP}s)", flush=True)

            prev_db = db

        except Exception as e:
            if debug:
                print(f"\n  [err] {e}", flush=True)

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, channels=1, callback=cb):
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDone.")


def main():
    p = argparse.ArgumentParser(description="Clap Trigger - double clap launches workspace")
    p.add_argument("--calibrate", action="store_true", help="Calibration mode")
    p.add_argument("--profile", default=DEFAULT_PROFILE, help="Workspace profile")
    p.add_argument("--threshold", type=float, default=CLAP_THRESHOLD_DB, help="Threshold dB")
    p.add_argument("--debug", action="store_true", help="Show dB level live")
    args = p.parse_args()

    if args.calibrate:
        run_calibration(args.threshold)
    else:
        run_listener(args.profile, args.threshold, args.debug)


if __name__ == "__main__":
    main()
