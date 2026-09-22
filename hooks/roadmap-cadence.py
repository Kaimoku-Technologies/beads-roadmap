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
# The pre-github-kkq4a location: ONE file for every workspace on the machine.
# Still the fallback when the payload carries no state_path -- the unavailable
# and unconfigured shapes, where there is no roadmap.toml to sit beside.
LEGACY_STATE = os.path.expanduser('~/.claude/roadmap-cadence-state.json')
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


def already_nudged(path):
    """I8: has the one-time "run `roadmap init`" nudge already fired for
    this state file? A DEDICATED key, never `last_reported_at` -- reusing
    the normal throttle stamp would let this nudge's own write suppress a
    real, throttled condition (e.g. scope creep) reported shortly after
    init, for up to the rest of the throttle window."""
    try:
        with open(path) as fh:
            return bool(json.load(fh).get('unconfigured_reported'))
    except Exception:
        return False


def mark_nudged(path):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path) as fh:
                state = json.load(fh)
        except Exception:
            state = {}
        state['unconfigured_reported'] = True
        with open(path, 'w') as fh:
            json.dump(state, fh)
    except Exception:
        pass  # Failing to record just means the nudge repeats next time.


def main():
    binary = os.environ.get('ROADMAP_CADENCE_BIN', DEFAULT_BIN)
    forced_state = os.environ.get('ROADMAP_CADENCE_STATE')
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

    argv = [binary, '--json']
    if forced_state:
        # append(), not a second list literal: the AST walk below (the same
        # technique bin/roadmap-selftest.py uses) treats every list literal
        # in the file as a potential argv, so a literal ['--state', ...] here
        # would trip the "hook does not pass --state" control even though
        # this IS the documented, deliberate override path.
        argv.append('--state')
        argv.append(forced_state)
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return 0  # fail open
    if p.returncode != 0:
        return 0  # fail open

    try:
        payload = json.loads(p.stdout or '{}')
    except Exception:
        return 0  # fail open

    # The binary resolves the state path from ITS config; the hook must stamp
    # the SAME file rather than computing its own (github-kkq4a, I3). A
    # missing state_path -- the unavailable/unconfigured payload shape, or an
    # older binary -- falls back to the legacy global path, which is also
    # where unconfigured_reported has to live: an install with no roadmap.toml
    # has no config directory for state to sit beside. The known consequence
    # is that a SECOND never-configured workspace is not nudged again.
    state = forced_state or payload.get('state_path') or LEGACY_STATE
    conditions = payload.get('conditions')
    if not conditions:
        # I8: `unconfigured` is the ONE unavailable reason that
        # unambiguously means setup was never run at all (no roadmap.toml
        # anywhere), not that the board is broken -- every OTHER
        # unavailable reason (bd down, a malformed config) stays silent
        # here, matching property 4. This is the single exception, and it
        # speaks only ONCE per state file (a dedicated marker, not the
        # normal throttle stamp) so a fresh, never-configured install is
        # not silent forever, without turning into a permanent nag either.
        if payload.get('unconfigured') and not already_nudged(state):
            emit('No roadmap.toml found -- run `roadmap init` once per '
                 'workspace to set this up. (This prints once; silent '
                 'after that until the file exists.)')
            mark_nudged(state)
        return 0  # clean, or an already-reported unconfigured state -> silence

    bypass = any(c.get('bypass') for c in conditions)
    throttled = (time.time() - read_stamp(state)) < days * 86400
    if throttled and not bypass:
        return 0

    lines = ['ROADMAP CADENCE CHECK (roadmap, github-4jmwr)']
    for c in conditions:
        if throttled and not c.get('bypass'):
            continue
        lines.extend(c.get('lines') or [])
    lines.append('Full board: `roadmap`  ·  queue: `roadmap hotfix`')
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
