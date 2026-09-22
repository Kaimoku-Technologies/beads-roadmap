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

# --- I7: remediation text names the bare `roadmap` a plugin install puts on
# PATH, never the origin-workspace-relative `bin/roadmap`. -----------------
rc, out, _ = run_hook(fake_roadmap(BYPASS))
check('hook output does not name bin/roadmap anywhere (I7)',
      'bin/roadmap' not in out)
check('hook output points at the bare Full board pointer (I7)',
      'Full board: `roadmap`' in out)
check('hook output points at the bare hotfix queue pointer (I7)',
      'queue: `roadmap hotfix`' in out)

# --- I8: the ONE unavailable reason that means "not configured yet" must
# speak once; every OTHER unavailable reason (this hook never even sees
# `conditions` for either) must stay silent, matching every arm above it. --
UNCONFIGURED = json.dumps({
    'unavailable': 'no roadmap.toml found; run `roadmap init`',
    'unconfigured': True})
UNAVAILABLE_ORDINARY = json.dumps({'unavailable': 'bd exited 1'})

# MUST-HIT: a fresh state file, never nudged before -- the hook speaks,
# names `roadmap init`, and exits 0.
rc, out, st_unc = run_hook(fake_roadmap(UNCONFIGURED))
check('unconfigured: exits 0', rc == 0)
check('unconfigured: nudges toward roadmap init', 'roadmap init' in out)

# MUST-MISS: the SAME state file, second run -- the nudge fired once and
# must not repeat, even though the underlying condition (no roadmap.toml)
# is still true.
rc2, out2, _ = run_hook(fake_roadmap(UNCONFIGURED), state=st_unc)
check('unconfigured: exits 0 on the second run', rc2 == 0)
check('unconfigured: does not repeat the nudge (speaks ONCE)', out2.strip() == '')

# MUST-MISS control: an ORDINARY unavailable reason (no `unconfigured` key)
# never speaks at all, on a fresh state file or otherwise -- proves the
# nudge is keyed on the flag, not on the mere presence of `unavailable`.
rc3, out3, _ = run_hook(fake_roadmap(UNAVAILABLE_ORDINARY))
check('ordinary unavailable reason: exits 0', rc3 == 0)
check('ordinary unavailable reason: stays silent (control)', out3.strip() == '')

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
# Was a second control on '--state'. The hook no longer passes it
# (github-kkq4a, I3) -- it reads the resolved path back out of the --json
# payload instead -- so this is now a MUST-MISS pinning that contract. The
# '--json' control above still proves the walk found the argv list, so the
# write-verb assertion below cannot pass vacuously.
check('the hook does not pass --state (it reads state_path back)',
      '--state' not in _tokens)
check('no write verb reaches any hook argv literal', not (_tokens & WRITE_VERBS))

# --- I3 (github-kkq4a): the hook stamps the path the BINARY resolved -------
# The hook used to compute ~/.claude/roadmap-cadence-state.json itself and
# pass it with --state, so every workspace on the machine shared one throttle
# stamp. It now runs --json with no --state and stamps payload['state_path'].
# run_hook always sets ROADMAP_CADENCE_STATE, so it cannot exercise this --
# call the hook directly with a controlled environment that pops that var.
_sp_dir = tempfile.mkdtemp()
_sp = os.path.join(_sp_dir, '.roadmap-state.json')
_dirty = json.dumps({'state_path': _sp,
                     'conditions': [{'id': 2, 'bypass': False,
                                     'lines': ['SCOPE CREEP -- probe']}]})
_fake = fake_roadmap(_dirty)
_env = dict(os.environ, ROADMAP_CADENCE_BIN=_fake, ROADMAP_CADENCE_DAYS='3',
            ROADMAP_CADENCE_TIMEOUT='10')
_env.pop('ROADMAP_CADENCE_STATE', None)
_p = subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
                    env=_env, timeout=30)
check('hook speaks on a dirty payload with no --state', 'SCOPE CREEP' in _p.stdout)
# This IS the discriminator for "did not use its own default": _sp is inside a
# fresh temp dir the hook has no way to name on its own, so a hook still
# computing ~/.claude/roadmap-cadence-state.json could never create it. Do not
# assert against the real legacy path instead -- it exists on a developer's
# machine and carries live state.
check('hook stamped the path the payload named', os.path.exists(_sp))
# And the stamp is a real timestamp, not a zero or an empty file -- so a hook
# that merely touched the path would still fail here.
check('the stamp it wrote is a real timestamp',
      json.loads(open(_sp).read()).get('last_reported_at', 0) > 0)

# A payload with NO state_path (the unavailable/unconfigured shape, or an
# older binary) must still work -- the hook falls back rather than crashing.
# This is the arm that keeps the one-time init nudge alive for an install with
# no roadmap.toml, which has no config directory for state to sit beside.
_nudge_state = os.path.join(tempfile.mkdtemp(), 'legacy.json')
_rc, _out, _ = run_hook(fake_roadmap(json.dumps({'unconfigured': True})),
                        state=_nudge_state)
check('unconfigured payload without state_path still nudges',
      'roadmap init' in _out)
check('unconfigured nudge still exits 0', _rc == 0)

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
