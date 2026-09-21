#!/usr/bin/env python3
"""SessionStart: report planning drift from bin/roadmap.

WHY THIS EXISTS (github-4jmwr)
-------------------------------
With 824 open bd issues, a roadmap that must be VISITED will not be. This is
the push. It follows the contract of the two cadence hooks already here.

FIVE PROPERTIES, each of which is a way this could fail
-------------------------------------------------------
1. SILENT WHEN CLEAN. A hook that speaks every session gets ignored and then
   torn out, leaving neither the hook nor the roadmap.
2. THROTTLED (default 3 days -- shorter than the other two hooks' 7, because
   planning drift moves faster than a Dolt commit count), EXCEPT conditions
   flagged `bypass`, which repeat every session because they are states that
   should not be sittable-in: an empty horizon means the roadmap does not
   exist, and an unversioned P0/P1 is a planning bug.
3. READ-ONLY, ALWAYS. It runs `bin/roadmap --json` and nothing else. It never
   applies a label. The suite walks this file's AST for argv list literals
   and checks them against a set of write verbs.
4. FAILS OPEN, ALWAYS. Missing binary, non-zero exit, unparseable JSON,
   timeout -- every path exits 0 with no output.
5. IT REPORTS; A HUMAN PLANS. The message carries the whole remediation,
   including that `bd label add` takes the label LAST and prints an error
   while EXITING 0 when it does not.

Output is JSON on stdout as hookSpecificOutput.additionalContext. A hook that
exits 0 has no other channel to the agent; stderr goes to the terminal only.

Testing seams (used by test_roadmap_cadence.py, harmless in production):
    ROADMAP_CADENCE_BIN      path to the roadmap executable
    ROADMAP_CADENCE_STATE    path to the stamp file
    ROADMAP_CADENCE_DAYS     throttle interval in days
    ROADMAP_CADENCE_TIMEOUT  subprocess timeout in seconds
"""
import json
import os
import subprocess
import sys
import time

DEFAULT_BIN = os.path.join(
    os.environ.get('CLAUDE_PLUGIN_ROOT',
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'bin', 'roadmap')
DEFAULT_STATE = os.path.expanduser('~/.claude/roadmap-cadence-state.json')
DEFAULT_DAYS = 3.0
DEFAULT_TIMEOUT = 30


def emit(text):
    """The only output path. Anything else is silence."""
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': text,
        }
    }))


def read_stamp(path):
    try:
        with open(path) as fh:
            return float(json.load(fh).get('last_reported_at', 0) or 0)
    except Exception:
        # Absent or corrupt state must behave like "never reported", so the
        # first run after install still speaks. Treating it as "just
        # reported" would let a broken file silently disable the hook.
        return 0.0


def write_stamp(path):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path) as fh:
                state = json.load(fh)
        except Exception:
            state = {}
        state['last_reported_at'] = time.time()
        with open(path, 'w') as fh:
            json.dump(state, fh)
    except Exception:
        pass  # Failing to record is not worth breaking a session over.


def main():
    binary = os.environ.get('ROADMAP_CADENCE_BIN', DEFAULT_BIN)
    state = os.environ.get('ROADMAP_CADENCE_STATE', DEFAULT_STATE)
    try:
        days = float(os.environ.get('ROADMAP_CADENCE_DAYS', DEFAULT_DAYS))
    except ValueError:
        days = DEFAULT_DAYS
    try:
        timeout = int(os.environ.get('ROADMAP_CADENCE_TIMEOUT', DEFAULT_TIMEOUT))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    if not os.path.exists(binary):
        return 0  # fail open

    try:
        p = subprocess.run([binary, '--json', '--state', state],
                           capture_output=True, text=True, timeout=timeout)
    except Exception:
        return 0  # fail open
    if p.returncode != 0:
        return 0  # fail open

    try:
        conditions = json.loads(p.stdout or '{}').get('conditions')
    except Exception:
        return 0  # fail open
    if not conditions:
        return 0  # clean -> silence

    bypass = any(c.get('bypass') for c in conditions)
    throttled = (time.time() - read_stamp(state)) < days * 86400
    if throttled and not bypass:
        return 0

    lines = ['ROADMAP CADENCE CHECK (bin/roadmap, github-4jmwr)']
    for c in conditions:
        if throttled and not c.get('bypass'):
            continue
        lines.extend(c.get('lines') or [])
    lines.append('Full board: `bin/roadmap`  ·  queue: `bin/roadmap hotfix`')
    lines.append('(Throttled conditions run at most once every %g days;'
                 ' bypass conditions repeat every session.)' % days)

    emit('\n'.join(lines))
    write_stamp(state)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail open, unconditionally
