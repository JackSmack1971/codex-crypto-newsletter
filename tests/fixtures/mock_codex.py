"""A no-network stand-in for `codex exec` used only by offline acceptance."""

import argparse
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--exit-code", type=int, default=0)
parser.add_argument("--delay", type=float, default=0)
args, _unknown = parser.parse_known_args()

if args.delay:
    import time

    time.sleep(args.delay)

print(json.dumps({"type": "turn.started"}), flush=True)
if args.exit_code == 0:
    print(json.dumps({"type": "turn.completed", "status": "completed"}), flush=True)
else:
    print(json.dumps({"type": "turn.failed", "status": "failed"}), flush=True)
sys.exit(args.exit_code)
