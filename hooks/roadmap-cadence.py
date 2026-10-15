#!/usr/bin/env python3
"""SessionStart: report planning drift from bin/roadmap.

WHY THIS EXISTS (github-4jmwr)
-------------------------------
With 824 open bd issues, a roadmap that must be VISITED will not be. This is
the push. It follows the contract of the two cadence hooks already here.

FIVE PROPERTIES, each of which is a way this could fail
-------------------------------------------------------
1. SILENT WHEN CLEAN. A hook that speaks every session gets ignored and then
   torn out, leaving neither the hook nor the roadmap. The two ONCE-EVER
   messages are the stated exceptions: the `roadmap init` nudge for an
   install with no roadmap.toml, and the 0.1.x -> 0.2.0 state-move notice.
   Each is keyed on its OWN marker in the state file, so once the marker is
   recorded it does not speak again. (If the marker cannot be written -- an
   unwritable directory -- the message repeats rather than being lost, which
   is the safe direction for something the user has to act on.)
2. THROTTLED (default 3 days -- shorter than the other two hooks' 7, because
   planning drift moves faster than a Dolt commit count), EXCEPT conditions
   flagged `bypass`, which repeat every session because they are states that
   should not be sittable-in: an empty horizon means the roadmap does not
   exist, and an unversioned P0/P1 is a planning bug. The two once-ever
   messages above bypass the throttle too -- it governs how often drift is
   RE-reported, and a message that is delivered once has nothing to repeat.
3. READ-ONLY, ALWAYS. It runs `bin/roadmap --json` -- once for this board
   and once per board the catch-all's `boards` key LISTS (github-7jn0v) --
   and nothing else. It never applies a label. The suite walks this file's
   AST for argv list literals and checks them against a set of write verbs.
4. FAILS OPEN, ALWAYS. Missing binary, non-zero exit, unparseable JSON,
   timeout -- every path exits 0 with no output. ONE deliberate exception
   (github-7jn0v): a board the catch-all LISTS and that is missing,
   unreadable or a second catch-all is reported as a line under the
   catch-all -- listing a board is the user asking to be told when it
   breaks, and a silent listed board would be the false-clean this tool
   exists to refuse. The catch-all itself still fails open: if IT cannot be
   read there is no list, and the hook is silent.
5. IT REPORTS; A HUMAN PLANS. The message carries the whole remediation,
   including that `bd label add` takes the label LAST and prints an error
   while EXITING 0 when it does not.

Output is JSON on stdout as hookSpecificOutput.additionalContext. A hook that
exits 0 has no other channel to the agent; stderr goes to the terminal only.

With --text (github-3i67y) the SAME decisions print as plain lines instead --
the form `roadmap check` uses, for agents other than Claude Code, git hooks
and shells. Only the envelope differs; silence, throttle, bypass and the
once-ever markers are shared, so the two forms can never disagree.

Testing seams (used by test_roadmap_cadence.py, harmless in production):
    ROADMAP_CADENCE_BIN      path to the roadmap executable
    ROADMAP_CADENCE_STATE    path to the stamp file -- the CATCH-ALL's only (github-7jn0v); a listed board is always judged on the state_path its own payload names
    ROADMAP_CADENCE_DAYS     throttle interval in days
    ROADMAP_CADENCE_TIMEOUT  subprocess timeout in seconds
"""
import concurrent.futures
import json
import os
import shlex
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


def emit(text, plain=False):
    """The only output path. Anything else is silence. `plain` is --text:
    the bare message, for anything that is not a Claude Code hook."""
    if plain:
        print(text)
        return
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


def _flag(path, key):
    """-> the boolean `key` recorded in the state file, False if it cannot
    be read. Absent or corrupt must behave like "never said", so the first
    run after install still speaks."""
    try:
        with open(path) as fh:
            return bool(json.load(fh).get(key))
    except Exception:
        return False


def _record_flag(path, key):
    """Set one boolean in the state file, READ-MODIFY-WRITE. The file has two
    writers -- bin/roadmap owns `baselines` and `last_cut`, this hook owns its
    own keys -- so a whole-file overwrite here would silently wipe creep
    detection and the endless "no baseline yet" would look like correct
    behaviour."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path) as fh:
                state = json.load(fh)
        except Exception:
            state = {}
        state[key] = True
        with open(path, 'w') as fh:
            json.dump(state, fh)
    except Exception:
        pass  # Failing to record just means the message repeats next time.


def already_nudged(path):
    """I8: has the one-time "run `roadmap init`" nudge already fired for
    this state file? A DEDICATED key, never `last_reported_at` -- reusing
    the normal throttle stamp would let this nudge's own write suppress a
    real, throttled condition (e.g. scope creep) reported shortly after
    init, for up to the rest of the throttle window."""
    return _flag(path, 'unconfigured_reported')


def mark_nudged(path):
    _record_flag(path, 'unconfigured_reported')


def already_legacy_reported(path):
    """C1 (github-kkq4a): has the one-time 0.1.x -> 0.2.0 state-move notice
    already fired for this state file? Its OWN key, for exactly the reason
    `unconfigured_reported` has one: a message that borrowed
    `last_reported_at` would suppress an unrelated throttled condition, and a
    message that borrowed `unconfigured_reported` would be silenced by a nudge
    it has nothing to do with."""
    return _flag(path, 'legacy_state_reported')


def mark_legacy_reported(path):
    _record_flag(path, 'legacy_state_reported')


def legacy_lines(state_path):
    """The 0.1.x -> 0.2.0 state-move message, worded to match bin/roadmap's
    stderr notice (`legacy_notice`) and the README's "Upgrading from 0.1.x"
    section -- one message, three surfaces.

    WHOSE file the legacy path holds is the load-bearing part: it was shared
    by EVERY workspace on this machine, so in every workspace but the last one
    to write it, the baselines inside belong to another product. Wording that
    tells the reader to keep "this install's baselines" is false there and
    imports another product's numbers -- the corruption that having no
    automatic migration exists to refuse.
    """
    return [
        'ROADMAP STATE MOVED (roadmap 0.2.0, github-kkq4a)',
        'State now lives beside roadmap.toml, at %s' % state_path,
        'A state file from before 0.2.0 is still at %s' % LEGACY_STATE,
        'That file was shared by EVERY workspace on this machine, so it may'
        ' hold another workspace\'s scope-creep baselines. Copy it ONLY if'
        ' this is the workspace that was using it:',
        '    cp %s %s' % (LEGACY_STATE, state_path),
        'Otherwise ignore it and re-baseline with `roadmap pin <version>`.'
        ' Nothing is copied automatically: a WRONG baseline is the false-clean'
        ' signal this tool exists to prevent.',
        '(This prints once.)',
    ]


def board_report(payload, state, days):
    """ONE board's judgement on ITS OWN state file (github-7jn0v):
    -> (prelude, body, stamp).

    prelude: the once-ever state-move notice, keyed on legacy_state_reported
             in THIS file; body: the condition lines that survive THIS
             board's throttle; stamp: whether any condition survived --
             exactly when the single-board hook wrote its stamp. Called once
             for the catch-all and once per listed board. Nothing here reads
             or writes another board's file: that is what keeps the throttles
             independent, and why a listed board is never handed the
             catch-all's forced state."""
    # C1 (github-kkq4a): 0.2.0 moved the state file and deliberately does NOT
    # migrate it -- auto-seeding would hand every workspace the same baselines.
    # The binary announces that on stderr, which this hook discards
    # (capture_output=True, and p.stderr is never read), and the same run
    # creates the new state file, so the binary's own notice never prints
    # again either. additionalContext is the only channel that reaches a
    # session, so the message is re-emitted here, once, on its own marker.
    prelude = []
    if payload.get('legacy_state_available') and not already_legacy_reported(state):
        prelude = legacy_lines(payload.get('state_path') or state)
        mark_legacy_reported(state)
    conditions = payload.get('conditions') or []
    if not conditions:
        return prelude, [], False
    bypass = any(c.get('bypass') for c in conditions)
    throttled = (time.time() - read_stamp(state)) < days * 86400
    if throttled and not bypass:
        # The state-move notice is bypass-class and must not be swallowed by
        # the throttle: it governs how often DRIFT is re-reported, and this
        # is a one-time message. The throttled condition stays silent and no
        # stamp is written, exactly as before.
        return prelude, [], False
    body = []
    for c in conditions:
        if throttled and not c.get('bypass'):
            continue
        body.extend(c.get('lines') or [])
    return prelude, body, True


def _run_board(binary, entry, timeout):
    """Pool worker for ONE listed board (github-7jn0v): -> (payload, None) or
    (None, reason). Every failure is a RETURNED reason, never a raise -- a
    raise would surface from .result() on the main thread, trip the
    hook-wide `except Exception: sys.exit(0)` and silence every board.
    Never --state: that seam is the catch-all's; the listed board's binary
    resolves its own default state path beside its config."""
    try:
        argv = [sys.executable, binary, '--json']
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, ROADMAP_CONFIG=entry['config_path']))
    except subprocess.TimeoutExpired:
        return None, 'timed out after %ds' % timeout
    except Exception as exc:
        return None, str(exc) or exc.__class__.__name__
    if p.returncode != 0:
        return None, 'exited %d' % p.returncode
    try:
        payload = json.loads(p.stdout or '{}')
    except Exception:
        return None, 'unparseable json'
    if not isinstance(payload, dict):
        return None, 'unparseable json'
    if payload.get('unavailable') or payload.get('unconfigured'):
        # A listed board cannot be unconfigured (ROADMAP_CONFIG names a file
        # the catch-all said exists); a payload claiming so is unavailable.
        return None, str(payload.get('unavailable') or 'unconfigured')
    if 'conditions' not in payload:       # the KEY: conditions: [] is a clean board
        return None, 'no conditions in payload'
    if not payload.get('state_path'):
        # Falling back to LEGACY_STATE would share one stamp across boards --
        # the cross-board reset this design forbids.
        return None, 'payload carries no state_path'
    conds = payload['conditions']
    if (not isinstance(conds, list) or not all(isinstance(c, dict) for c in conds)
            or not isinstance(payload['state_path'], str)):
        return None, 'malformed payload'
    return payload, None


def run_listed(binary, boards, timeout):
    """-> [(entry, payload, line)] in LIST order; exactly one of payload /
    line is None, and `line` is a finished problem line (github-7jn0v).
    Subprocesses run in a pool sized to the boards that exist; nothing
    here reads or writes a state file. An `exists: false` entry never
    runs (shape a). The pool is created only when something will run:
    ThreadPoolExecutor(max_workers=0) raises, and the hook-wide except
    would turn that into the silent listed board this design refuses."""
    boards = [b for b in boards if isinstance(b, dict) and b.get('name') is not None]
    todo = [(i, b) for i, b in enumerate(boards) if b.get('exists') and b.get('config_path')]
    results = {}
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(todo)) as pool:
            futures = {pool.submit(_run_board, binary, b, timeout): i for i, b in todo}
            for f in concurrent.futures.as_completed(futures):
                results[futures[f]] = f.result()
    outcomes = []
    for i, b in enumerate(boards):
        if i not in results:
            outcomes.append((b, None, 'boards: %s listed, no roadmap.toml there' % b['name']))
            continue
        payload, reason = results[i]
        if payload is None:
            outcomes.append((b, None, 'boards: %s unavailable: %s' % (b['name'], reason)))
        else:
            outcomes.append((b, payload, None))
    return outcomes


def second_catch_all(catch_payload, listed_payload):
    """(c) in the design (github-7jn0v): a LISTED board that is unscoped on
    the SAME workspace repeats every unowned row the catch-all shows.
    realpath on both sides: _resolve normalises a relative path against a
    realpath'd base but returns an absolute path as written, so /var/x and
    /private/var/x must not read as two workspaces. If either side lacks
    `workspace` the rule does not fire -- a finding needs evidence, and an
    older or stubbed payload is not evidence."""
    if listed_payload.get('scoped'):
        return False
    a = catch_payload.get('workspace')
    b = listed_payload.get('workspace')
    if not (a and b and isinstance(a, str) and isinstance(b, str)):
        return False
    return os.path.realpath(a) == os.path.realpath(b)


def problem_lines(catch_payload, outcomes):
    """The listed-board problem lines in list order (github-7jn0v). They are
    ONE non-bypass pseudo-condition of the catch-all: dropped when it is
    throttled, and when they print the catch-all's stamp is written -- a
    missing board is re-reported every `days`, like scope creep, not every
    session like an empty horizon."""
    lines = []
    for entry, payload, line in outcomes:
        if line is not None:
            lines.append(line)
        elif second_catch_all(catch_payload, payload):
            lines.append('two catch-all boards: %s repeats every unowned row -- '
                         'add scoped = true' % entry['name'])
    return lines


def board_header(entry):
    """`-- <name as written>  ·  <dir>  ·  full board: cd <dir> && roadmap`.
    The cd target is shell-quoted because a human pastes it; shlex.quote
    leaves a plain path untouched, so the usual case reads as before."""
    d = os.path.dirname(entry['config_path'])
    return '-- %s  ·  %s  ·  full board: cd %s && roadmap' % (entry['name'], d, shlex.quote(d))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    plain = '--text' in argv
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

    # sys.executable, never the binary's shebang (github-3i67y): through
    # `/usr/bin/env python3` a 3.9 PATH interpreter runs roadmap below its
    # floor, it fails open, and the check is silent forever -- the same
    # output as a clean board. Whoever started this hook already chose an
    # interpreter; the binary gets the same one.
    argv = [sys.executable, binary, '--json']
    if forced_state:
        argv += ['--state', forced_state]
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

    # github-7jn0v: the catch-all may LIST its sibling boards. Run each now --
    # in parallel, each under its own ROADMAP_CONFIG, never with --state --
    # BEFORE any state is read, so every stamp read and write below happens
    # on this thread, in list order. A listed board that cannot be run is a
    # line under the catch-all: the one deliberate exception to property 4.
    # The catch-all's own `boards` is the only list read (one level).
    boards = payload.get('boards')
    outcomes = run_listed(binary, boards if isinstance(boards, list) else (), timeout)
    problems = problem_lines(payload, outcomes)
    if problems:
        payload['conditions'] = list(payload.get('conditions') or []) + [
            {'id': 'boards', 'bypass': False, 'lines': problems}]

    # C1 (github-kkq4a): the once-ever state-move notice and the throttle are
    # judged per board by board_report (github-7jn0v); the comments that
    # lived here moved with the code. Collected into a list rather than
    # emitted on the spot: emit() writes one JSON object on stdout and a
    # second object would not parse.
    prelude, body, stamp = board_report(payload, state, days)
    if not payload.get('conditions'):
        # I8: `unconfigured` is the ONE unavailable reason that
        # unambiguously means setup was never run at all (no roadmap.toml
        # anywhere), not that the board is broken -- every OTHER
        # unavailable reason (bd down, a malformed config) stays silent
        # here, matching property 4. This is the single exception, and it
        # speaks only ONCE per state file (a dedicated marker, not the normal
        # throttle stamp) so a fresh, never-configured install is not silent
        # forever, without turning into a permanent nag either. Consulted for
        # the catch-all only: a LISTED board cannot be unconfigured.
        if payload.get('unconfigured') and not already_nudged(state):
            prelude.append(
                'No roadmap.toml found -- run `roadmap init` once per '
                'workspace to set this up. (This prints once; silent '
                'after that until the file exists.)')
            mark_nudged(state)

    # One block per listed board with something to say, in list order; its
    # once-ever notice goes INSIDE its block, under its header. The
    # catch-all's block keeps today's unheaded form: the session is in or
    # under its directory, so the unheaded block is "here" and the headed
    # ones are "elsewhere" -- which is also what makes byte-identity free.
    blocks = []                      # (lines, state path to stamp or None)
    for entry, listed, _line in outcomes:
        if listed is None:
            continue
        pre_i, body_i, stamp_i = board_report(listed, listed['state_path'], days)
        if pre_i or stamp_i:
            blocks.append(([board_header(entry)] + pre_i + body_i,
                           listed['state_path'] if stamp_i else None))

    speaking = stamp or any(st_i for _, st_i in blocks)
    lines = list(prelude)
    if speaking:
        lines.append('ROADMAP CADENCE CHECK (roadmap, github-4jmwr)')
    if stamp:
        lines.extend(body)
        lines.append('Full board: `roadmap`  ·  queue: `roadmap hotfix`')
    for block_lines, _ in blocks:
        lines.extend(block_lines)
    if speaking:
        lines.append('(Throttled conditions run at most once every %g days;'
                     ' bypass conditions repeat every session.)' % days)
    if not lines:
        return 0  # nothing from any board -> silence
    emit('\n'.join(lines), plain=plain)
    if stamp:
        write_stamp(state)
    for _, st_i in blocks:
        if st_i:
            write_stamp(st_i)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail open, unconditionally
