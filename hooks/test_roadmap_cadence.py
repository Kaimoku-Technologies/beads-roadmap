#!/usr/bin/env python3
"""Suite for roadmap-cadence.py -- both directions, because a hook that always
speaks and one that never speaks are byte-identical from outside.

Its own falsifiability is one command:
    python3 test_roadmap_cadence.py /tmp/always_speaks.py -> must fail the SILENT arms
    python3 test_roadmap_cadence.py /tmp/never_speaks.py  -> must fail the SPEAK arms

The hook shells out to `bin/roadmap --json`, so each arm supplies a FAKE
roadmap whose stdout and exit code are scripted. Nothing here touches bd.
"""
import ast
import json
import os
import subprocess
import sys
import tempfile

HOOK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'roadmap-cadence.py')

# HOOK may be a substitute passed as argv[1] -- that is how this suite is
# falsified. Source-level assertions must always read the REAL hook, so a
# stub fails only the behavioural arms it is meant to fail.
REAL_HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'roadmap-cadence.py')

FAILURES = []


def fake_roadmap(payload, rc=0):
    """Write a stub that prints `payload` and exits `rc`."""
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    with open(path, 'w') as fh:
        fh.write('#!/usr/bin/env python3\nimport sys\n')
        fh.write('sys.stdout.write(%r)\n' % payload)
        fh.write('sys.exit(%d)\n' % rc)
    os.chmod(path, 0o755)
    return path


def fake_roadmap_sleep(seconds, payload=None):
    """Write a stub that sleeps past the hook's own subprocess timeout, then
    (if it were ever allowed to finish) would print `payload` and exit 0."""
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    with open(path, 'w') as fh:
        fh.write('#!/usr/bin/env python3\nimport sys, time\n')
        fh.write('time.sleep(%r)\n' % seconds)
        fh.write('sys.stdout.write(%r)\n' % (payload if payload is not None else CLEAN))
        fh.write('sys.exit(0)\n')
    os.chmod(path, 0o755)
    return path


def run_hook(roadmap_path, days='3', state=None, timeout='10'):
    if state is None:
        fd, state = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        os.unlink(state)
    env = dict(os.environ,
               ROADMAP_CADENCE_BIN=roadmap_path,
               ROADMAP_CADENCE_STATE=state,
               ROADMAP_CADENCE_DAYS=days,
               ROADMAP_CADENCE_TIMEOUT=timeout)
    p = subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
                       env=env, timeout=30)
    return p.returncode, p.stdout, state


def check(label, cond):
    if not cond:
        FAILURES.append(label)


BYPASS = json.dumps({'conditions': [
    {'id': 1, 'bypass': True, 'lines': ['HORIZON EMPTY -- nothing tagged above v0.16.0.']}]})
THROTTLED = json.dumps({'conditions': [
    {'id': 2, 'bypass': False, 'lines': ['SCOPE CREEP -- v0.16.0 grew.']}]})
CLEAN = json.dumps({'conditions': []})

# --- SPEAK arms -----------------------------------------------------------
rc, out, _ = run_hook(fake_roadmap(BYPASS))
check('bypass condition speaks', 'HORIZON EMPTY' in out)
check('speaking still exits 0', rc == 0)
check('output is hook JSON',
      json.loads(out or '{}').get('hookSpecificOutput', {}).get('hookEventName') == 'SessionStart')

rc, out, st = run_hook(fake_roadmap(THROTTLED))
check('throttled condition speaks on a fresh stamp', 'SCOPE CREEP' in out)

# --- SILENT arms ----------------------------------------------------------
rc, out, _ = run_hook(fake_roadmap(CLEAN))
check('no conditions -> total silence', out.strip() == '')
check('silence exits 0', rc == 0)

# Second run inside the throttle window must be silent for a NON-bypass
# condition, and must still speak for a bypass one.
rm2 = fake_roadmap(THROTTLED)
_, _, st2 = run_hook(rm2)
_, out2, _ = run_hook(rm2, state=st2)
check('throttled condition is silent on the second run', out2.strip() == '')

rm3 = fake_roadmap(BYPASS)
_, _, st3 = run_hook(rm3)
_, out3, _ = run_hook(rm3, state=st3)
check('bypass condition repeats inside the throttle', 'HORIZON EMPTY' in out3)

# --- FAIL-OPEN arms, each asserted separately -----------------------------
rc, out, _ = run_hook('/nonexistent/roadmap')
check('missing binary: exit 0', rc == 0)
check('missing binary: no output', out.strip() == '')

rc, out, _ = run_hook(fake_roadmap('not json at all'))
check('unparseable json: exit 0', rc == 0)
check('unparseable json: no output', out.strip() == '')

# The payload here MUST be populated, not CLEAN -- a CLEAN payload passes
# this arm even with the `returncode != 0` guard deleted outright, because
# `not conditions` already returns 0 for an empty conditions list regardless
# of exit code. BYPASS carries a real condition, so only the guard saves it.
rc, out, _ = run_hook(fake_roadmap(BYPASS, rc=1))
check('non-zero exit with populated payload: exit 0', rc == 0)
check('non-zero exit with populated payload: no output', out.strip() == '')

rc, out, _ = run_hook(fake_roadmap(json.dumps({})))
check('missing conditions key: exit 0', rc == 0)
check('missing conditions key: no output', out.strip() == '')

# There was no timeout arm at all. The payload the slow stub carries is
# POPULATED (BYPASS), not CLEAN: with the timeout properly enforced,
# subprocess.run is killed at 1s, well before the 2s sleep finishes, so the
# populated payload is never read and the hook stays silent. If the timeout
# enforcement is removed (or the `timeout=` kwarg dropped), the subprocess
# runs to completion and this arm would report the BYPASS text instead of
# silence -- the assertion is falsifiable, not vacuous.
rc, out, _ = run_hook(fake_roadmap_sleep(2, payload=BYPASS), timeout='1')
check('subprocess timeout: exit 0', rc == 0)
check('subprocess timeout: no output', out.strip() == '')

# --- READ-ONLY arm: structural, not a grep --------------------------------
# The hook's docstring deliberately quotes `bd label add <id> release:...` as
# remediation text, so a substring search for a write verb fails against the
# CORRECT hook while proving nothing about what it runs. Walk the argv list
# literals instead, the same way bin/roadmap-selftest.py does.
WRITE_VERBS = {'label', 'close', 'create', 'update', 'defer', 'compact', 'gc',
               'prune', 'dep', 'remember', 'edit', 'push', 'commit', 'tag'}
_literals = [
    [e.value for e in node.elts
     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    for node in ast.walk(ast.parse(open(REAL_HOOK).read()))
    if isinstance(node, ast.List)
]
_tokens = {t for lit in _literals for t in lit}

# MUST-HIT control: if the walk finds nothing the assertion below is vacuous
# and would pass against a hook that shells out freely.
check('control — AST walk found the hook argv', '--json' in _tokens)
check('control — AST walk found the state flag', '--state' in _tokens)
check('no write verb reaches any hook argv literal', not (_tokens & WRITE_VERBS))

# --- two-writer contract: write_stamp must not clobber bin/roadmap's fields
# The state file is shared: bin/roadmap writes 'baselines' and 'last_cut'
# into it, this hook writes 'last_reported_at'. A read-modify-write
# violation (e.g. write_stamp replacing the whole file with just its own
# key) would silently wipe creep detection on every SessionStart, and the
# resulting endless "no baseline yet" would look exactly like correct
# behaviour. Seed the file with both bin/roadmap fields, run the hook with a
# fake roadmap that produces a throttled (non-bypass) condition on a FRESH
# stamp -- so the hook actually speaks and stamps -- and assert both keys
# survive alongside a freshly-written last_reported_at.
fd, _shared_state = tempfile.mkstemp(suffix='.json')
os.close(fd)
with open(_shared_state, 'w') as _fh:
    json.dump({'baselines': {'0.16.0': ['a', 'b']}, 'last_cut': '0.16.0'}, _fh)
rc, out, _ = run_hook(fake_roadmap(THROTTLED), state=_shared_state)
check('two-writer: hook still speaks on a fresh stamp', 'SCOPE CREEP' in out)
with open(_shared_state) as _fh:
    _after = json.load(_fh)
check('two-writer: baselines survive the hook stamp',
      _after.get('baselines') == {'0.16.0': ['a', 'b']})
check('two-writer: last_cut survives the hook stamp',
      _after.get('last_cut') == '0.16.0')
check('two-writer: last_reported_at was written',
      _after.get('last_reported_at', 0) > 0)
os.unlink(_shared_state)

if FAILURES:
    print('FAIL (%d)' % len(FAILURES))
    for f in FAILURES:
        print('  ' + f)
    sys.exit(1)
print('ok')
