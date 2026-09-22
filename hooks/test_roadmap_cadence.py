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
import time

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

# --- C1 (github-kkq4a): the 0.1.x -> 0.2.0 state-move notice --------------
# The binary writes it to stderr, which this hook discards, and the same run
# creates the new state file so the binary never writes it again. The measured
# result before this fix: run 1 emitted the notice to a discarded stream, run 2
# was silent, and nobody on the default install path ever saw it. The hook now
# re-emits it through additionalContext, once, on a dedicated marker.
LEGACY_PATH = os.path.expanduser('~/.claude/roadmap-cadence-state.json')
# Named in the payload and quoted back in the message; nothing ever writes it
# (the hook stamps `state`, which run_hook forces), so it only has to be a
# path the hook could not have invented on its own.
_MOVED_STATE = os.path.join(tempfile.mkdtemp(), '.roadmap-state.json')
LEGACY_CLEAN = json.dumps({'state_path': _MOVED_STATE,
                           'legacy_state_available': True,
                           'conditions': []})

# MUST-HIT: a CLEAN board -- the case that matters, since an upgrading install
# is usually not in drift, and the `not conditions` early return used to make
# this path silent by construction.
fd, _lg_state = tempfile.mkstemp(suffix='.json')
os.close(fd)
os.unlink(_lg_state)
rc, out, _ = run_hook(fake_roadmap(LEGACY_CLEAN), state=_lg_state)
check('state move: speaks on a CLEAN board', 'ROADMAP STATE MOVED' in out)
check('state move: exits 0', rc == 0)
check('state move: names the legacy path', LEGACY_PATH in out)
check('state move: names the new path', _MOVED_STATE in out)
check('state move: gives the exact cp',
      'cp %s %s' % (LEGACY_PATH, _MOVED_STATE) in out)
# I5: the legacy file belongs to whichever workspace last wrote it, so this
# must not tell the reader it holds THIS install's baselines -- following that
# in any other workspace imports another product's numbers.
check('state move: does not call them this install\'s baselines',
      'this install' not in out.lower())
check('state move: says the file may be another workspace\'s',
      'another workspace' in out)
check('state move: names the re-baseline escape hatch', 'roadmap pin' in out)

# The marker is DEDICATED: reusing last_reported_at would let this message
# suppress a real throttled condition for the rest of the window.
#
# GUARDED, and the guard is repeated inside the must-miss below. run_hook was
# handed a path that does not exist yet, so a hook that never speaks never
# creates it, and an unguarded read here would raise and truncate every later
# arm instead of failing this one (the failure mode measured on this very
# assertion during its own falsification drill). `{}` is the fallback, so the
# `not ...` check has to re-test existence: an empty container satisfies every
# negative, which is the vacuous must-miss this suite already fixed once.
_lg_exists = os.path.exists(_lg_state)
_lg_after = json.load(open(_lg_state)) if _lg_exists else {}
check('state move: wrote the state file at all', _lg_exists)
check('state move: records its own marker key',
      _lg_after.get('legacy_state_reported') is True)
check('state move: does not consume the throttle stamp',
      _lg_exists and not _lg_after.get('last_reported_at'))

# MUST-MISS: the SAME state file, second run -- it speaks ONCE even though the
# binary still reports the flag (the legacy file is still there; the user may
# well have chosen to ignore it, which is a legitimate choice).
rc2, out2, _ = run_hook(fake_roadmap(LEGACY_CLEAN), state=_lg_state)
check('state move: does not repeat (speaks ONCE)', out2.strip() == '')
check('state move: exits 0 on the second run', rc2 == 0)

# MUST-MISS control: the same clean payload WITHOUT the flag is silent, so the
# message is keyed on the flag rather than on any clean board.
fd, _lg_ctl = tempfile.mkstemp(suffix='.json')
os.close(fd)
os.unlink(_lg_ctl)
_, out3, _ = run_hook(fake_roadmap(json.dumps({'state_path': _MOVED_STATE,
                                               'legacy_state_available': False,
                                               'conditions': []})),
                      state=_lg_ctl)
check('state move: silent when the flag is False (control)', out3.strip() == '')

# MUST-HIT: the 3-day throttle must not swallow it. Seed a FRESH stamp so the
# non-bypass condition in the payload is throttled, and assert the state-move
# lines arrive while the throttled condition stays silent -- both directions in
# one run.
fd, _lg_thr = tempfile.mkstemp(suffix='.json')
os.close(fd)
with open(_lg_thr, 'w') as _fh:
    json.dump({'last_reported_at': time.time(),
               'baselines': {'0.16.0': ['a', 'b']}}, _fh)
_, out4, _ = run_hook(fake_roadmap(json.dumps(
    {'state_path': _MOVED_STATE, 'legacy_state_available': True,
     'conditions': [{'id': 2, 'bypass': False,
                     'lines': ['SCOPE CREEP -- v0.16.0 grew.']}]})),
    state=_lg_thr)
check('state move: survives the throttle', 'ROADMAP STATE MOVED' in out4)
check('state move: the throttled condition beside it stays silent',
      'SCOPE CREEP' not in out4)
# Two-writer: the marker write is read-modify-write, like write_stamp.
check('state move: the marker write preserves bin/roadmap\'s fields',
      json.load(open(_lg_thr)).get('baselines') == {'0.16.0': ['a', 'b']})

# MUST-MISS control for the arm above: the SAME throttled payload without the
# flag is wholly silent, so the throttle still throttles.
fd, _lg_thr2 = tempfile.mkstemp(suffix='.json')
os.close(fd)
with open(_lg_thr2, 'w') as _fh:
    json.dump({'last_reported_at': time.time()}, _fh)
_, out5, _ = run_hook(fake_roadmap(THROTTLED), state=_lg_thr2)
check('state move: a throttled condition alone is still silent (control)',
      out5.strip() == '')

# MUST-HIT: with a bypass condition the hook reports BOTH, in one JSON object
# (emit() writes one, and a second would not parse).
fd, _lg_both = tempfile.mkstemp(suffix='.json')
os.close(fd)
os.unlink(_lg_both)
_, out6, _ = run_hook(fake_roadmap(json.dumps(
    {'state_path': _MOVED_STATE, 'legacy_state_available': True,
     'conditions': [{'id': 1, 'bypass': True,
                     'lines': ['HORIZON EMPTY -- nothing tagged above v0.16.0.']}]})),
    state=_lg_both)
check('state move: rides along with a real report', 'ROADMAP STATE MOVED' in out6)
check('state move: the real report is not lost', 'HORIZON EMPTY' in out6)
check('state move: still exactly one JSON object',
      json.loads(out6 or '{}').get('hookSpecificOutput', {})
      .get('hookEventName') == 'SessionStart')

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
# A second witness that the walk found the (conditional) override literal
# `['--state', forced_state]` (github-kkq4a, I3). This proves the AST walk
# saw that branch too -- nothing more. It does NOT prove the DEFAULT path
# omits --state, or that the override's path value actually reaches argv at
# runtime: a hook could pass a harmless --state on every run and separately
# read state_path back from the payload, and this control would still pass.
# The real behavioural contract -- default omits --state, override carries
# it with the exact forced path -- is pinned at runtime below, not here.
check('control — AST walk found the override argv literal', '--state' in _tokens)
check('no write verb reaches any hook argv literal', not (_tokens & WRITE_VERBS))

# --- I3 (github-kkq4a), Finding 1: pin the REAL contract at runtime. The AST
# controls above only prove a string literal exists somewhere in the source;
# they cannot tell whether it reaches the actual subprocess argv, or whether
# the two branches (forced vs default) land in the right place. Run the hook
# against a stub that records its own sys.argv, both directions.
def _record_argv_stub(capture_path):
    """A fake roadmap that writes its OWN sys.argv (as JSON) to
    `capture_path`, then answers with a clean payload and exits 0."""
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    with open(path, 'w') as fh:
        fh.write('#!/usr/bin/env python3\nimport sys, json\n')
        fh.write('open(%r, "w").write(json.dumps(sys.argv))\n' % capture_path)
        fh.write('sys.stdout.write(%r)\n' % CLEAN)
        fh.write('sys.exit(0)\n')
    os.chmod(path, 0o755)
    return path

# UNSET: the default path must not carry --state at all.
_fd, _argv_unset = tempfile.mkstemp(suffix='.json')
os.close(_fd)
os.unlink(_argv_unset)
_env_unset = dict(os.environ, ROADMAP_CADENCE_BIN=_record_argv_stub(_argv_unset),
                  ROADMAP_CADENCE_DAYS='3', ROADMAP_CADENCE_TIMEOUT='10')
_env_unset.pop('ROADMAP_CADENCE_STATE', None)
subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
               env=_env_unset, timeout=30)
# Guarded like the stamp check below: under a falsified HOOK (a substitute
# that never shells out to ROADMAP_CADENCE_BIN at all) the capture file is
# never written, and an unguarded read here would raise past every later
# arm instead of failing this one via check(). The sentinel is None, NOT []
# (github-kkq4a) -- an empty container satisfies every `not in`, so a
# must-miss check ('--state' not in ...) would pass VACUOUSLY against a
# falsified run that never captured anything, exactly the input the Step 5
# falsification drill exercises. A dedicated capture must-hit gates both
# directions so neither can pass without real argv underneath it.
_recorded_unset = (json.loads(open(_argv_unset).read())
                   if os.path.exists(_argv_unset) else None)
check('the unset arm captured the hook subprocess argv at all',
      _recorded_unset is not None)
check('argv carries --json when ROADMAP_CADENCE_STATE is unset',
      _recorded_unset is not None and '--json' in _recorded_unset)
check('argv omits --state when ROADMAP_CADENCE_STATE is unset',
      _recorded_unset is not None and '--state' not in _recorded_unset)

# SET: the override must reach argv, followed by the exact forced path.
_fd, _argv_set = tempfile.mkstemp(suffix='.json')
os.close(_fd)
os.unlink(_argv_set)
_fd, _forced_path = tempfile.mkstemp(suffix='.json')
os.close(_fd)
os.unlink(_forced_path)
_env_set = dict(os.environ, ROADMAP_CADENCE_BIN=_record_argv_stub(_argv_set),
                ROADMAP_CADENCE_DAYS='3', ROADMAP_CADENCE_TIMEOUT='10',
                ROADMAP_CADENCE_STATE=_forced_path)
subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
               env=_env_set, timeout=30)
# Guarded for the same reason as the UNSET arm above, same None sentinel
# (github-kkq4a) -- both of THIS arm's checks currently use the `in`
# direction, which is correctly False against an empty-container fallback,
# so [] would not be vacuous here today. Use None anyway: a later edit that
# adds or flips one of these to a `not in` check would silently reintroduce
# the exact bug the UNSET arm just had, with nothing here to catch it. Fix
# the class, not the instance.
_recorded_set = (json.loads(open(_argv_set).read())
                 if os.path.exists(_argv_set) else None)
check('the set arm captured the hook subprocess argv at all',
      _recorded_set is not None)
check('argv carries --state when ROADMAP_CADENCE_STATE is set',
      _recorded_set is not None and '--state' in _recorded_set)
check('the --state value is the exact forced path',
      _recorded_set is not None and '--state' in _recorded_set and
      _recorded_set[_recorded_set.index('--state') + 1] == _forced_path)

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
# that merely touched the path would still fail here. Guarded (short-circuit
# on os.path.exists) so a falsification run where _sp is never created fails
# this ONE check via `check()` rather than raising past it -- an unguarded
# read here would abort the script before every later arm runs, which is not
# a falsification, it is skipping most of the suite.
check('the stamp it wrote is a real timestamp',
      os.path.exists(_sp) and
      json.loads(open(_sp).read()).get('last_reported_at', 0) > 0)

# --- I4 (github-kkq4a): the LEGACY_STATE fallback, exercised for real -----
# A payload with NO state_path -- the unavailable/unconfigured shape, or an
# older binary -- falls back to LEGACY_STATE, which is also where an install
# with no roadmap.toml has to keep its one-time nudge marker: there is no
# config directory for the state file to sit beside.
#
# This arm used to run through run_hook, which ALWAYS sets
# ROADMAP_CADENCE_STATE, so `forced_state` short-circuited
# `forced_state or payload.get('state_path') or LEGACY_STATE` and the fallback
# was never reached. Deleting `or LEGACY_STATE` from the hook left the
# assertion passing while its comment claimed to cover it.
#
# LEGACY_STATE is os.path.expanduser('~/.claude/...') and expanduser reads
# $HOME, so running the hook subprocess with HOME pointed at a temp directory
# makes the constant resolve INSIDE that directory: a genuine behavioural test
# of the fallback that never touches the developer's own file, which exists
# and carries live state.
_home = tempfile.mkdtemp()
_legacy_in_home = os.path.join(_home, '.claude', 'roadmap-cadence-state.json')
_env_home = dict(os.environ, HOME=_home,
                 ROADMAP_CADENCE_BIN=fake_roadmap(json.dumps({'unconfigured': True})),
                 ROADMAP_CADENCE_DAYS='3', ROADMAP_CADENCE_TIMEOUT='10')
_env_home.pop('ROADMAP_CADENCE_STATE', None)
_ph = subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
                     env=_env_home, timeout=30)
check('fallback: an unconfigured payload with no state_path still nudges',
      'roadmap init' in _ph.stdout)
check('fallback: it exits 0', _ph.returncode == 0)
check('fallback: the nudge marker lands on LEGACY_STATE',
      os.path.exists(_legacy_in_home))

# MUST-MISS control, same shape: when the payload DOES carry a state_path the
# marker lands there and the fallback stays untouched. Without this pair the
# must-hit above would also pass for a hook that wrote to LEGACY_STATE
# unconditionally, ignoring the payload entirely.
_home2 = tempfile.mkdtemp()
_legacy_in_home2 = os.path.join(_home2, '.claude', 'roadmap-cadence-state.json')
_named_state = os.path.join(tempfile.mkdtemp(), '.roadmap-state.json')
_env_home2 = dict(os.environ, HOME=_home2,
                  ROADMAP_CADENCE_BIN=fake_roadmap(json.dumps(
                      {'unconfigured': True, 'state_path': _named_state})),
                  ROADMAP_CADENCE_DAYS='3', ROADMAP_CADENCE_TIMEOUT='10')
_env_home2.pop('ROADMAP_CADENCE_STATE', None)
_ph2 = subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
                      env=_env_home2, timeout=30)
check('control: the nudge still fires when the payload names a state path',
      'roadmap init' in _ph2.stdout)
check('control: the marker lands on the path the payload named',
      os.path.exists(_named_state))
check('control: and NOT on the fallback',
      not os.path.exists(_legacy_in_home2))

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
