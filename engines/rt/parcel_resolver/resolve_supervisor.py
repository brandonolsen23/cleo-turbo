#!/usr/bin/env python3
"""
Resilient supervisor for the parcel re-geocode run.

Wraps resolve_v2: runs it, and if it stops before finishing — throttle hard-stop,
geocoder session failure, network blip — it waits out a cooldown and resumes,
looping until the resolver reports nothing left to process. resolve_v2's own
checkpoint/skip makes each resume continue where it left off (and the
forward-geocode cache means already-geocoded addresses fly by on a re-run).

Each round prints a timestamped heartbeat and also appends to a log file, so a
day-long unattended run is auditable. Run it under `caffeinate` so the Mac
won't sleep:

    caffeinate -dimsu ./.venv/bin/python -m parcel_resolver.resolve_supervisor -- --reprocess

(run from engines/rt). Stop anytime with Ctrl-C; restart resumes safely.
"""

import argparse
import datetime
import os
import subprocess
import sys
import time

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # engines/rt


def _ts() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def run_round(module: str, resolve_args, log) -> tuple[bool, bool, int]:
    """Run one resolve_v2 invocation, streaming output. Returns
    (done, throttled, returncode). `done` = the resolver found nothing left."""
    cmd = [sys.executable, '-u', '-m', module] + resolve_args
    proc = subprocess.Popen(
        cmd, cwd=ENGINE_DIR, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    done = throttled = False
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        log.write(line)
        log.flush()
        if 'Nothing to process' in line:
            done = True
        if 'THROTTLE DETECTED' in line:
            throttled = True
    proc.wait()
    return done, throttled, proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description='Resilient supervisor for resolve_v2.')
    ap.add_argument('--module', default='parcel_resolver.resolve_v2',
                    help='module to run each round (overridable for testing)')
    ap.add_argument('--cooldown', type=int, default=600,
                    help='seconds to wait after a throttle stop before resuming')
    ap.add_argument('--short-cooldown', type=int, default=60,
                    help='seconds to wait after a non-throttle stop')
    ap.add_argument('--max-rounds', type=int, default=500)
    ap.add_argument('--log', default=os.path.join(ENGINE_DIR, 'pipeline', 'resolve_supervisor.log'))
    ap.add_argument('resolve_args', nargs=argparse.REMAINDER,
                    help='args passed through to the resolver (place after --)')
    args = ap.parse_args()
    resolve_args = [a for a in args.resolve_args if a != '--']

    os.makedirs(os.path.dirname(args.log), exist_ok=True)
    with open(args.log, 'a') as log:
        hdr = f'[{_ts()}] SUPERVISOR START module={args.module} args={resolve_args} cooldown={args.cooldown}s'
        print(hdr, flush=True)
        log.write('\n' + hdr + '\n')

        for rnd in range(1, args.max_rounds + 1):
            print(f'\n[{_ts()}] ── Round {rnd} ' + '─' * 40, flush=True)
            done, throttled, rc = run_round(args.module, resolve_args, log)
            if done:
                msg = f'[{_ts()}] COMPLETE — nothing left to process after {rnd} round(s).'
                print('\n' + msg, flush=True)
                log.write(msg + '\n')
                try:
                    subprocess.run(
                        ['osascript', '-e',
                         'display notification "Parcel re-geocode complete" with title "Cleo Turbo"'],
                        check=False,
                    )
                except Exception:
                    pass
                return 0
            reason = 'THROTTLE hard-stop' if throttled else f'stopped (rc={rc})'
            cd = args.cooldown if throttled else args.short_cooldown
            note = f'[{_ts()}] Round {rnd} ended: {reason}. Cooling down {cd}s, then resuming...'
            print(note, flush=True)
            log.write(note + '\n')
            time.sleep(cd)

        print(f'[{_ts()}] Hit max-rounds={args.max_rounds} without completing. Stopping.', flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
