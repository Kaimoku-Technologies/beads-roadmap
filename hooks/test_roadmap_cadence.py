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


def _write_stub(*lines):
    """Write an executable python stub (shebang + `lines`, each already
    newline-terminated) to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    with open(path, 'w') as fh:
        fh.write('#!/usr/bin/env python3\n')
        for line in lines:
            fh.write(line)
    os.chmod(path, 0o755)
    return path


def fake_roadmap(payload, rc=0):
    """Write a stub that prints `payload` and exits `rc`."""
    return _write_stub('import sys\n',
                       'sys.stdout.write(%r)\n' % payload,
                       'sys.exit(%d)\n' % rc)


def fake_roadmap_sleep(seconds, payload=None):
    """Write a stub that sleeps past the hook's own subprocess timeout, then
    (if it were ever allowed to finish) would print `payload` and exit 0."""
    return _write_stub('import sys, time\n',
                       'time.sleep(%r)\n' % seconds,
                       'sys.stdout.write(%r)\n' % (payload if payload is not None else CLEAN),
                       'sys.exit(0)\n')


def fresh_state():
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    os.unlink(path)
    return path


def run_hook(roadmap_path, days='3', state=None, timeout='10', extra=()):
    if state is None:
        state = fresh_state()
    env = dict(os.environ,
               ROADMAP_CADENCE_BIN=roadmap_path,
               ROADMAP_CADENCE_STATE=state,
               ROADMAP_CADENCE_DAYS=days,
               ROADMAP_CADENCE_TIMEOUT=timeout)
    p = subprocess.run([sys.executable, HOOK] + list(extra), capture_output=True,
                       text=True, env=env, timeout=30)
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
    return _write_stub('import sys, json\n',
                       'open(%r, "w").write(json.dumps(sys.argv))\n' % capture_path,
                       'sys.stdout.write(%r)\n' % CLEAN,
                       'sys.exit(0)\n')

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

# --- github-3i67y: --text, the same check for agents other than Claude Code -
# Identical decisions (silence, throttle, bypass, once-ever) -- only the
# envelope differs: plain lines on stdout instead of Claude Code's
# hookSpecificOutput JSON, so any hook system, git hook or agent can show it.
rc, out, _ = run_hook(fake_roadmap(BYPASS), extra=['--text'])
check('text: a bypass condition speaks', 'HORIZON EMPTY' in out)
check('text: exits 0', rc == 0)
check('text: opens with the check banner',
      out.startswith('ROADMAP CADENCE CHECK'))
try:
    json.loads(out)
    _is_json = True
except ValueError:
    _is_json = False
check('text: output is NOT JSON', _is_json is False)
# Control: the same payload WITHOUT --text is still the Claude Code envelope,
# so the flag switched the format rather than the default having changed.
_, out_json, _ = run_hook(fake_roadmap(BYPASS))
check('text: default output is still hook JSON (control)',
      'hookSpecificOutput' in json.loads(out_json or '{}'))

rc, out, _ = run_hook(fake_roadmap(CLEAN), extra=['--text'])
check('text: a clean board is silent', out == '')

rc, out, st_t = run_hook(fake_roadmap(THROTTLED), extra=['--text'])
check('text: a throttled condition speaks on a fresh stamp', 'SCOPE CREEP' in out)
rc, out, _ = run_hook(fake_roadmap(THROTTLED), state=st_t, extra=['--text'])
check('text: ...and is throttled on the next run', out == '')

rc, out, _ = run_hook(fake_roadmap(UNCONFIGURED), extra=['--text'])
check('text: the unconfigured nudge prints as plain text',
      'roadmap init' in out and not out.lstrip().startswith('{'))

# The binary runs under the HOOK'S interpreter, never its shebang. Through
# the shebang (`/usr/bin/env python3`) a machine whose PATH python3 is 3.9
# runs roadmap below its floor; it fails open and the check is silent
# forever -- indistinguishable from a clean board. This fake's shebang names
# an interpreter that does not exist, so only the hook's own interpreter can
# make it speak.
_fd, _nosheb = tempfile.mkstemp(suffix='.py')
os.close(_fd)
with open(_nosheb, 'w') as _fh:
    _fh.write('#!/nonexistent/python3\nimport sys\nsys.stdout.write(%r)\n' % BYPASS)
os.chmod(_nosheb, 0o755)
rc, out, _ = run_hook(_nosheb, extra=['--text'])
check('the binary runs under the hook\'s interpreter, not its shebang',
      'HORIZON EMPTY' in out)

# --- github-7jn0v: the single-board form, pinned EXACTLY ---------------------
# The multi-board hook must degenerate to today's output when the catch-all's
# payload carries no `boards`. Every arm above is a substring test; this one
# is the first exact-string assertion in the suite, so a header, a directory
# or an extra line leaking into the single-board form fails loudly rather
# than by inspection. %g renders 3.0 as 3.
_EXACT_BYPASS = ('ROADMAP CADENCE CHECK (roadmap, github-4jmwr)\n'
                 'HORIZON EMPTY -- nothing tagged above v0.16.0.\n'
                 'Full board: `roadmap`  ·  queue: `roadmap hotfix`\n'
                 '(Throttled conditions run at most once every 3 days;'
                 ' bypass conditions repeat every session.)')
rc, out, _ = run_hook(fake_roadmap(BYPASS), extra=['--text'])
check('exact: the single-board --text form is byte-identical', out == _EXACT_BYPASS + '\n')
_, out_json, _ = run_hook(fake_roadmap(BYPASS))
check('exact: the single-board JSON additionalContext is byte-identical',
      json.loads(out_json or '{}').get('hookSpecificOutput', {})
      .get('additionalContext') == _EXACT_BYPASS)
# MUST-MISS control: the exact string is specific -- a one-character change
# in the fixture's condition line is not equal.
rc, out, _ = run_hook(fake_roadmap(BYPASS.replace('v0.16.0', 'v0.17.0')), extra=['--text'])
check('exact: a different payload is not equal (control)', out != _EXACT_BYPASS + '\n')

# --- github-7jn0v: the catch-all LISTS its sibling boards ----------------------
# ONE ROADMAP_CADENCE_BIN plays every board: the stub answers by the
# ROADMAP_CONFIG the hook set for a listed board, and by None for the
# catch-all, whose run inherits the hook's env -- so the suite's own
# ROADMAP_CONFIG, if a developer's shell had one, is dropped first.
# Nothing here touches bd.
os.environ.pop('ROADMAP_CONFIG', None)


def fake_roadmap_boards(by_config, rc=0):
    """A stub that prints by_config[os.environ.get('ROADMAP_CONFIG')] -- the
    catch-all's payload under the key None -- so ONE ROADMAP_CADENCE_BIN plays
    every board of a fixture. A value is a payload string, or a dict
    {'payload': str, 'rc': int, 'sleep': float} for a board that must fail
    or stall. A config the table does not know exits 3 with a message on
    stderr, so a hook that runs a listed board under the WRONG ROADMAP_CONFIG
    reports it unavailable instead of quietly getting another board's
    answer. Nothing here touches bd."""
    return _write_stub(
        'import os, sys, time\n',
        'TABLE = %r\n' % by_config,
        'key = os.environ.get("ROADMAP_CONFIG")\n',
        'if key not in TABLE:\n',
        '    sys.stderr.write("stub: unknown ROADMAP_CONFIG %r\\n" % (key,))\n',
        '    sys.exit(3)\n',
        'spec = TABLE[key]\n',
        'if isinstance(spec, str):\n    spec = {"payload": spec}\n',
        'time.sleep(spec.get("sleep", 0))\n',
        'sys.stdout.write(spec["payload"])\n',
        'sys.exit(spec.get("rc", %d))\n' % rc)


def listed_board(name, **payload):
    """-> (entry, payload_json): a listed board in its own temp dir with a real
    (empty) roadmap.toml, so `exists` is honest, and its own state_path inside
    that dir -- the per-board file the hook must judge it on."""
    d = tempfile.mkdtemp()
    cfg = os.path.join(d, 'roadmap.toml')
    open(cfg, 'w').close()
    payload.setdefault('state_path', os.path.join(d, '.roadmap-state.json'))
    payload.setdefault('conditions', [])
    return {'name': name, 'config_path': cfg, 'exists': True}, json.dumps(payload)


def catch_all(boards, workspace='/ws/acme-app', **payload):
    """-> the catch-all's payload JSON naming `boards`. workspace=None omits
    the key (an older or stubbed producer)."""
    payload.setdefault('conditions', [])
    payload['boards'] = list(boards)
    if workspace is not None:
        payload['workspace'] = workspace
    return json.dumps(payload)


def seed_stamp(path, age=0.0):
    """Write last_reported_at = now - age (fresh by default: THROTTLED)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    value = time.time() - age
    with open(path, 'w') as fh:
        json.dump({'last_reported_at': value}, fh)
    return value


def stamp_of(path):
    try:
        with open(path) as fh:
            return json.load(fh).get('last_reported_at')
    except Exception:
        return None


CREEP = [{'id': 2, 'bypass': False, 'lines': ['SCOPE CREEP -- v0.16.0 grew.']}]
HORIZON = [{'id': 1, 'bypass': True, 'lines': ['HORIZON EMPTY -- nothing tagged above v0.16.0.']}]
OTHER_CREEP = [{'id': 2, 'bypass': False, 'lines': ['SCOPE CREEP -- other-app v1.1.0 grew.']}]
MISSING = {'name': 'third-app',
           'config_path': os.path.join(tempfile.mkdtemp(), 'roadmap.toml'), 'exists': False}

# 1. INDEPENDENT THROTTLES: each board on ITS OWN stamp, both directions in
# two runs, and the silent board's file is never written.
_e1, _p1 = listed_board('other-app', conditions=OTHER_CREEP)
_st1 = json.loads(_p1)['state_path']
_stub1 = fake_roadmap_boards({None: catch_all([_e1], conditions=CREEP), _e1['config_path']: _p1})
_seed1 = seed_stamp(_st1)                                   # other-app throttled, catch-all fresh
rc, out1, _ca1 = run_hook(_stub1)
check('throttles: the catch-all speaks on its fresh stamp', 'SCOPE CREEP -- v0.16.0 grew.' in out1)
check('throttles: the seeded listed board has no block (must-miss)', '-- other-app' not in out1)
check('throttles: ...and its creep line is absent', 'other-app v1.1.0' not in out1)
check('throttles: the silent board\'s stamp was NOT rewritten', stamp_of(_st1) == _seed1)
check('throttles: the speaking board\'s stamp was written', (stamp_of(_ca1) or 0) > _seed1 - 1)
check('throttles: exits 0', rc == 0)
os.unlink(_st1)                                             # swap: catch-all throttled, other-app fresh
_ca2 = fresh_state()
_seed2 = seed_stamp(_ca2)
rc, out2, _ = run_hook(_stub1, state=_ca2)
check('throttles (swapped): the listed board\'s block is present (must-hit)', '-- other-app' in out2)
check('throttles (swapped): ...with its creep line', 'other-app v1.1.0' in out2)
check('throttles (swapped): the throttled catch-all\'s line is absent', 'v0.16.0 grew' not in out2)
check('throttles (swapped): no pointer line for an empty catch-all block',
      'Full board: `roadmap`' not in out2)
check('throttles (swapped): the header and footer still frame the report',
      'ROADMAP CADENCE CHECK' in out2 and '(Throttled conditions' in out2)
check('throttles (swapped): the catch-all\'s seeded stamp is untouched', stamp_of(_ca2) == _seed2)
check('throttles (swapped): the listed board\'s stamp was written', (stamp_of(_st1) or 0) > 0)
# Review focus 1 + 5 control: the header carries the name AS WRITTEN and an
# unquoted plain directory. Read from the PARSED additionalContext: the raw
# hook JSON escapes the header's middle dot as \u00b7.
_dir1 = os.path.dirname(_e1['config_path'])
check('header: name as written, directory, and an unquoted cd (control)',
      '-- other-app  ·  %s  ·  full board: cd %s && roadmap' % (_dir1, _dir1)
      in json.loads(out2 or '{}').get('hookSpecificOutput', {}).get('additionalContext', ''))

# 2. A MISSING listed board speaks; a present CLEAN board is silent.
_e2, _p2 = listed_board('other-app')
_stub2 = fake_roadmap_boards({None: catch_all([_e2, MISSING]), _e2['config_path']: _p2})
rc, out, _ = run_hook(_stub2)
check('missing board: named', 'boards: third-app listed, no roadmap.toml there' in out)
check('missing board: a clean present board has no block (must-miss)', '-- other-app' not in out)
check('missing board: the catch-all pointer line still prints', 'Full board: `roadmap`' in out)
check('missing board: the problem line sits before the pointer line',
      'third-app listed' in out and 'Full board: `roadmap`' in out
      and out.index('third-app listed') < out.index('Full board: `roadmap`'))
check('missing board: exits 0', rc == 0)
_e2b, _p2b = listed_board('third-app')
_stub2b = fake_roadmap_boards({None: catch_all([_e2, _e2b]),
                               _e2['config_path']: _p2, _e2b['config_path']: _p2b})
rc, out, _ = run_hook(_stub2b)
check('two clean listed boards and a clean catch-all -> total silence (control)', out == '')
check('...and exits 0', rc == 0)
# Review focus 3: EVERY listed board missing -- no pool may be created
# (ThreadPoolExecutor(max_workers=0) raises, and the hook-wide except would
# turn that into silence).
rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([MISSING])}))
check('every listed board missing: still reported (no empty pool)',
      'boards: third-app listed, no roadmap.toml there' in out)

# 3. PROBLEM LINES ride the catch-all's throttle and write ITS stamp.
_ca3 = fresh_state()
_seed3 = seed_stamp(_ca3)
rc, out, _ = run_hook(_stub2, state=_ca3)
check('problem lines: throttled with the catch-all (must-miss)', out == '')
check('problem lines: the seeded stamp is untouched', stamp_of(_ca3) == _seed3)
rc, out, _st3 = run_hook(_stub2)
check('problem lines: speak on a fresh stamp (must-hit)', 'third-app listed' in out)
check('problem lines: ...and write the catch-all stamp', (stamp_of(_st3) or 0) > 0)
_stub3 = fake_roadmap_boards({None: catch_all([_e2, MISSING], conditions=HORIZON),
                              _e2['config_path']: _p2})
_ca3b = fresh_state()
seed_stamp(_ca3b)
rc, out, _ = run_hook(_stub3, state=_ca3b)
check('problem lines: a bypass catch-all on a seeded stamp still speaks (control)',
      'HORIZON EMPTY' in out)
check('problem lines: ...but the throttled problem line stays out of it',
      'third-app listed' not in out)

# 4. An UNAVAILABLE listed board is a line with its reason -- the one
# exception to property 4, scoped to LISTED boards.
_e4, _p4 = listed_board('other-app')
for _label, _spec, _reason in (
        ('exits 1', {'payload': _p4, 'rc': 1}, 'exited 1'),
        ('prints garbage', 'not json', 'unparseable json'),
        ('reports unavailable', json.dumps({'unavailable': 'bd exited 1'}), 'bd exited 1'),
        ('has no conditions key', json.dumps({'state_path': '/x'}), 'no conditions in payload'),
        ('has no state_path', json.dumps({'conditions': []}), 'payload carries no state_path'),
        ('is unconfigured', UNCONFIGURED, 'no roadmap.toml found')):
    _stub4 = fake_roadmap_boards({None: catch_all([_e4]), _e4['config_path']: _spec})
    rc, out, _ = run_hook(_stub4)
    check('unavailable listed board (%s): named with its reason' % _label,
          'boards: other-app unavailable: %s' % _reason in out)
    check('unavailable listed board (%s): exits 0' % _label, rc == 0)
check('unavailable listed board (is unconfigured): no roadmap-init NUDGE for a listed board',
      'No roadmap.toml found -- run' not in out)
_t4 = time.monotonic()
_stub4t = fake_roadmap_boards({None: catch_all([_e4]), _e4['config_path']: {'payload': _p4, 'sleep': 3}})
rc, out, _ = run_hook(_stub4t, timeout='1')
check('unavailable listed board (times out): named',
      'boards: other-app unavailable: timed out after 1s' in out)
check('unavailable listed board (times out): returns well inside the suite timeout',
      time.monotonic() - _t4 < 5)
rc, out, _ = run_hook(fake_roadmap(UNAVAILABLE_ORDINARY))
check('the catch-all\'s OWN unavailable payload is still silent (I8 control)', out.strip() == '')
# Review focus 4: two slow boards run in PARALLEL -- one timeout, not the sum.
_e4a, _p4a = listed_board('other-app')
_e4b, _p4b = listed_board('third-app')
_stub4p = fake_roadmap_boards({None: catch_all([_e4a, _e4b]),
                               _e4a['config_path']: {'payload': _p4a, 'sleep': 3},
                               _e4b['config_path']: {'payload': _p4b, 'sleep': 3}})
_t4p = time.monotonic()
rc, out, _ = run_hook(_stub4p, timeout='1')
_elapsed = time.monotonic() - _t4p
check('parallel: both slow boards are reported', out.count('timed out after 1s') == 2)
check('parallel: wall time is one timeout, not the sum (%.2fs)' % _elapsed, _elapsed < 2.0)

# 6. The ONCE-EVER state-move notice is per board: marker in ITS file.
_e6, _p6 = listed_board('other-app', legacy_state_available=True)
_st6 = json.loads(_p6)['state_path']
_stub6 = fake_roadmap_boards({None: catch_all([_e6]), _e6['config_path']: _p6})
rc, out, _ca6 = run_hook(_stub6)
check('per-board notice: the listed board\'s block carries it',
      '-- other-app' in out and 'ROADMAP STATE MOVED' in out)
check('per-board notice: names ITS state path', _st6 in out)
check('per-board notice: no CADENCE header for a notice-only report',
      'ROADMAP CADENCE CHECK' not in out)
_after6 = json.load(open(_st6)) if os.path.exists(_st6) else {}
check('per-board notice: marker in the listed board\'s file',
      _after6.get('legacy_state_reported') is True)
check('per-board notice: no stamp consumed', not _after6.get('last_reported_at'))
check('per-board notice: NOT in the catch-all\'s file',
      not (os.path.exists(_ca6) and json.load(open(_ca6)).get('legacy_state_reported')))
rc, out, _ = run_hook(_stub6, state=_ca6)
check('per-board notice: speaks once', out == '')

# 7. NO --state leaks to a listed board: the catch-all's argv carries the
# forced path, the listed board's carries --json only, under ITS config.
def _record_env_stub(capture_dir, by_config):
    """fake_roadmap_boards that first writes {'argv': sys.argv, 'config':
    $ROADMAP_CONFIG} to capture_dir/<pid>.json -- one file per invocation,
    so the parallel listed runs never interleave."""
    return _write_stub(
        'import os, sys, json\n',
        'open(os.path.join(%r, "%%d.json" %% os.getpid()), "w").write(json.dumps(\n'
        '    {"argv": sys.argv, "config": os.environ.get("ROADMAP_CONFIG")}))\n' % capture_dir,
        'TABLE = %r\n' % by_config,
        'sys.stdout.write(TABLE.get(os.environ.get("ROADMAP_CONFIG"), ""))\n',
        'sys.exit(0)\n')


_cap = tempfile.mkdtemp()
_e7, _p7 = listed_board('other-app')
_forced7 = fresh_state()
run_hook(_record_env_stub(_cap, {None: catch_all([_e7]), _e7['config_path']: _p7}), state=_forced7)
_recs = [json.load(open(os.path.join(_cap, f))) for f in os.listdir(_cap)]
_by_cfg = {r['config']: r['argv'] for r in _recs}
check('state leak: both boards ran (control)', set(_by_cfg) == {None, _e7['config_path']})
_ca_argv = _by_cfg.get(None)
_lb_argv = _by_cfg.get(_e7['config_path'])
check('state leak: the catch-all carries --state <forced>',
      _ca_argv is not None and '--state' in _ca_argv
      and _ca_argv[_ca_argv.index('--state') + 1] == _forced7)
check('state leak: the listed board carries --json only',
      _lb_argv is not None and _lb_argv[1:] == ['--json'])

# 8. ONE JSON object, blocks in the spec's order; --text opens with the banner.
_e8, _p8 = listed_board('other-app', conditions=OTHER_CREEP)
_stub8 = fake_roadmap_boards({None: catch_all([_e8], conditions=CREEP), _e8['config_path']: _p8})
rc, out, _ = run_hook(_stub8)
_obj8 = json.loads(out or '{}')
check('two-board: one JSON object', _obj8.get('hookSpecificOutput', {}).get('hookEventName') == 'SessionStart')
_ctx8 = _obj8.get('hookSpecificOutput', {}).get('additionalContext', '')
check('two-board: exactly one CADENCE header', _ctx8.count('ROADMAP CADENCE CHECK') == 1)
check('two-board: exactly one footer', _ctx8.count('(Throttled conditions') == 1)
check('two-board: catch-all line, pointer, then the listed header, in that order',
      'v0.16.0 grew' in _ctx8 and 'Full board: `roadmap`' in _ctx8 and '-- other-app' in _ctx8
      and _ctx8.index('v0.16.0 grew') < _ctx8.index('Full board: `roadmap`') < _ctx8.index('-- other-app'))
check('two-board: the listed board\'s line is under its header',
      '-- other-app' in _ctx8 and 'other-app v1.1.0' in _ctx8
      and _ctx8.index('-- other-app') < _ctx8.index('other-app v1.1.0'))
_e8t, _p8t = listed_board('other-app', conditions=OTHER_CREEP)
_stub8t = fake_roadmap_boards({None: catch_all([_e8t], conditions=CREEP), _e8t['config_path']: _p8t})
rc, out, _ = run_hook(_stub8t, extra=['--text'])
check('two-board --text: opens with the banner', out.startswith('ROADMAP CADENCE CHECK'))
check('two-board --text: carries both boards', 'v0.16.0 grew' in out and '-- other-app' in out)

# 9. The catch-all is the single point of silence: unreadable -> no list.
_e9, _p9 = listed_board('other-app', conditions=OTHER_CREEP)
_stub9 = fake_roadmap_boards({None: {'payload': catch_all([_e9], conditions=CREEP), 'rc': 1},
                              _e9['config_path']: _p9})
rc, out, _ = run_hook(_stub9)
check('catch-all exits 1: everything silent, listed board included', out == '')
check('catch-all exits 1: exits 0', rc == 0)

# Review focus 5: a name or directory with a space / non-ASCII.
_d_sp = os.path.join(tempfile.mkdtemp(), 'my app')
os.makedirs(_d_sp)
_cfg_sp = os.path.join(_d_sp, 'roadmap.toml')
open(_cfg_sp, 'w').close()
_e_sp = {'name': 'café app', 'config_path': _cfg_sp, 'exists': True}
_p_sp = json.dumps({'state_path': os.path.join(_d_sp, '.roadmap-state.json'), 'conditions': OTHER_CREEP})
rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e_sp]), _cfg_sp: _p_sp}))
_ctx_sp = json.loads(out or '{}').get('hookSpecificOutput', {}).get('additionalContext', '')
check('header: the name is printed as written, non-ASCII intact',
      '-- café app  ·  %s' % _d_sp in _ctx_sp)
check('header: a directory with a space is shell-quoted in the cd target',
      "full board: cd '%s' && roadmap" % _d_sp in _ctx_sp)


# 5. TWO CATCH-ALLS: an unscoped listed board on the SAME workspace. Flagged,
# and still reported as a board. Controls: scoped; a different workspace;
# `workspace` missing from either side (no evidence, no finding); and the
# realpath pair (macOS /var vs /private/var -- trivially equal on Linux).
_ws5 = tempfile.mkdtemp()
_TWO = 'two catch-all boards: other-app repeats every unowned row -- add scoped = true'
for _label, _scoped, _listed_ws, _want in (
        ('unscoped, same workspace', False, _ws5, True),
        ('scoped, same workspace (control)', True, _ws5, False),
        ('unscoped, different workspace (control)', False, tempfile.mkdtemp(), False),
        ('unscoped, same workspace in realpath form', False, os.path.realpath(_ws5), True)):
    _e5, _p5 = listed_board('other-app', scoped=_scoped, workspace=_listed_ws, conditions=OTHER_CREEP)
    _stub5 = fake_roadmap_boards({None: catch_all([_e5], workspace=_ws5, conditions=CREEP),
                                  _e5['config_path']: _p5})
    rc, out, _ = run_hook(_stub5)
    check('two catch-alls (%s): line %s' % (_label, 'present' if _want else 'absent'),
          (_TWO in out) == _want)
    check('two catch-alls (%s): the board is still reported as a board' % _label,
          '-- other-app' in out and 'other-app v1.1.0' in out)
# (label, listed payload kwargs, catch-all workspace, must-hit control?). The
# listed side's workspace is missing, or the catch-all's is, or both are.
for _label, _lkw, _cw, _ctl in (
        ('listed side lacks workspace', {}, _ws5, False),
        ('catch-all side lacks workspace', dict(workspace=_ws5), None, True),
        ('neither side has workspace', {}, None, False)):
    _e5x, _p5x = listed_board('other-app', scoped=False, conditions=OTHER_CREEP, **_lkw)
    rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e5x], workspace=_cw),
                                               _e5x['config_path']: _p5x}))
    check('two catch-alls: %s -> absent (no evidence)' % _label,
          _TWO not in out and (_ctl or '-- other-app' in out))
    if _ctl:
        check('two catch-alls: ...and the board is still reported (control)', '-- other-app' in out)
# The (c) line rides the catch-all's throttle like (a) and (b).
_e5t, _p5t = listed_board('other-app', scoped=False, workspace=_ws5, conditions=OTHER_CREEP)
_ca5t = fresh_state()
seed_stamp(_ca5t)
rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e5t], workspace=_ws5), _e5t['config_path']: _p5t}),
                      state=_ca5t)
check('two catch-alls: the line is throttled with the catch-all', _TWO not in out)
check('two catch-alls: ...while the listed board still speaks on its own stamp', '-- other-app' in out)


# 6. MALFORMED-BUT-PARSEABLE payloads (final review M1): a listed board or a
# `boards` value of the wrong shape must never silence the catch-all. The
# must-hit control in every arm is the catch-all's own SCOPE CREEP line.
_ws6 = tempfile.mkdtemp()
_CA_OWN = 'v0.16.0 grew'
for _label, _cw, _lkw in (
        ('listed workspace is not a string', _ws6, dict(scoped=False, workspace=5, conditions=OTHER_CREEP)),
        ('catch-all workspace is not a string', ['x'], dict(scoped=False, workspace=_ws6, conditions=OTHER_CREEP)),
        ('listed conditions are not dicts', _ws6, dict(scoped=False, workspace=_ws6, conditions=['notadict'])),
        ('listed state_path is not a string', _ws6, dict(scoped=False, workspace=_ws6, conditions=OTHER_CREEP, state_path=7))):
    _e6m, _p6m = listed_board('other-app', **_lkw)
    rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e6m], workspace=_cw, conditions=CREEP),
                                               _e6m['config_path']: _p6m}))
    check('malformed payload (%s): the catch-all still speaks' % _label, _CA_OWN in out)
rc, out, _ = run_hook(fake_roadmap_boards({None: json.dumps({'conditions': CREEP, 'boards': 5})}))
check('malformed payload (boards is not a list): the catch-all still speaks', _CA_OWN in out)


# 7. THE MANIFEST: the hook runs the catch-all and THEN the listed boards, each
# under the per-board timeout, so hooks.json must allow both plus margin
# (final review I1). Control: the constant is read from the hook itself.
_src = open(HOOK).read()
_m = [n.value.value for n in ast.parse(_src).body
      if isinstance(n, ast.Assign) and any(getattr(t, 'id', '') == 'DEFAULT_TIMEOUT' for t in n.targets)]
_manifest = json.load(open(os.path.join(os.path.dirname(os.path.abspath(HOOK)), 'hooks.json')))
_hk = _manifest['hooks']['SessionStart'][0]['hooks'][0]
check('manifest: DEFAULT_TIMEOUT was found in the hook (control)', len(_m) == 1 and isinstance(_m[0], int))
check('manifest: hooks.json timeout covers 2 x DEFAULT_TIMEOUT + 10',
      bool(_m) and isinstance(_hk.get('timeout'), (int, float)) and _hk['timeout'] >= 2 * _m[0] + 10)


if FAILURES:
    print('FAIL (%d)' % len(FAILURES))
    for f in FAILURES:
        print('  ' + f)
    sys.exit(1)
print('ok')
