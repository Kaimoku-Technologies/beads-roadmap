#!/usr/bin/env python3
"""Suite for bin/roadmap. Both directions on every rule, because a detector
that fires on everything and one that fires on nothing are indistinguishable
from a single passing assertion.

    python3 bin/roadmap-selftest.py

bin/roadmap has no .py extension, so it is loaded by path the same way
bin/perms-selftest.py loads bin/perms.
"""
import ast
import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'roadmap')


# github-b6y2m: this suite must never exit 0 without having run. bin/roadmap
# FAILS OPEN at import on an old interpreter -- `sys.exit(0)`, deliberately,
# so a broken install can never break a session -- and loading it in-process
# used to hand that exit 0 straight to the suite: zero checks run, a green
# exit code. The tool's contract stays; the suite refuses to inherit it.
# Keep everything above the load 3.9-parseable, or this never gets to run.
def _suite_interpreter_error(version_info, executable):
    if tuple(version_info[:3]) < (3, 11, 0):
        return ('FAIL: roadmap-selftest did not run -- it needs Python 3.11 '
                'or newer; this interpreter is %d.%d.%d at %s'
                % (version_info[0], version_info[1], version_info[2], executable))
    return None


def _load_module(name, path):
    """exec a module by path; a SystemExit at its top level is a FAILURE to
    load, never a result -- whatever code it carried."""
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except SystemExit as exc:
        raise RuntimeError('%s exited with code %r at import, so nothing was '
                           'tested' % (path, exc.code))
    return module


_INTERPRETER_ERROR = _suite_interpreter_error(sys.version_info, sys.executable)
if _INTERPRETER_ERROR:
    print(_INTERPRETER_ERROR)
    sys.exit(1)
try:
    rm = _load_module('roadmap_under_test', MODULE_PATH)
except RuntimeError as _load_exc:
    print('FAIL: roadmap-selftest did not run -- %s' % _load_exc)
    sys.exit(1)

# The suite's namespace is deliberately FOREIGN to every default and to the
# reference deployment, so a surviving hardcoded namespace FAILS here rather
# than passing. See the decoupling scan at the end of this file.
TEST_CFG = {'workspace': '/nonexistent/workspace',
            'tag_repo': '/nonexistent/workspace/acme-app',
            'release_namespace': 'acme-app',
            'convention_start': '2026-09-20',
            'auto_label_prefixes': ('audit-fp:', 'resource-fp:',
                                    'resource-watch', 'audit-ack')}
rm.configure(TEST_CFG)

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append('%s: got %r, want %r' % (label, got, want))


def issue(**kw):
    """A bd row with the fields bin/roadmap reads, defaulted."""
    row = {'id': 'github-test', 'title': '', 'labels': [], 'priority': 3,
           'issue_type': 'task', 'status': 'open', 'updated_at': '2026-09-21T00:00:00Z'}
    row.update(kw)
    return row


# --- I6: the documented Python floor must be ENFORCED, not just documented -
# import tomllib under Python < 3.11 raises a bare ModuleNotFoundError and
# exits 1 -- a traceback, not the fail-open contract (exit 0 + a named
# reason) every other unavailable path follows. Through the SessionStart
# hook (discards stderr, treats non-zero exit as silence already) that
# reads as PERMANENT, UNDIAGNOSABLE SILENCE on /usr/bin/python3 (3.9.6 on
# macOS) -- the interpreter a second user is most likely to hit.
#
# There is no real pre-3.11 interpreter to run THIS suite under, so
# _check_python_version() is a standalone, injectable function (real
# sys.version_info/sys.executable only when no override is given) rather
# than an inline check at import time -- both arms are exercised here by
# passing a fake version tuple.

# MUST-HIT: below the floor.
_old_msg = rm._check_python_version(version_info=(3, 9, 6), executable='/usr/bin/python3')
check('old interpreter produces a message, not None', _old_msg is not None, True)
check('old interpreter message names the requirement (3.11)',
      '3.11' in _old_msg, True)
check('old interpreter message names the RUNNING version',
      '3.9.6' in _old_msg, True)
check('old interpreter message names the interpreter PATH',
      '/usr/bin/python3' in _old_msg, True)
check('old interpreter message follows the unavailable contract',
      _old_msg.startswith('roadmap: unavailable:'), True)

# MUST-MISS: exactly at the floor (3.11.0) must NOT trigger -- it is the
# floor, not one below it.
check('exactly the floor version is accepted (control)',
      rm._check_python_version(version_info=(3, 11, 0), executable='/usr/bin/python3'),
      None)
# MUST-MISS control: well above the floor is obviously fine too.
check('a newer interpreter is accepted (control)',
      rm._check_python_version(version_info=(3, 13, 2), executable='/usr/bin/python3'),
      None)
# MUST-MISS: the REAL running interpreter (this suite refuses to run below
# 3.11 -- see _suite_interpreter_error at the top) must pass with no
# override -- proves the default path (real sys.version_info) also works,
# not just the injected one.
check('the real running interpreter passes with no override',
      rm._check_python_version(), None)

# --- github-b6y2m: the suite never inherits the tool's fail-open exit 0 ----
# On 3.9 this suite used to print the tool's `unavailable` line and exit 0
# with zero checks run. CI (3.11+) can never reach that path, so both guards
# are tested by injection, like _check_python_version above.
# MUST-HIT: below the floor the suite reports a FAILURE, not an unavailable.
_suite_old = _suite_interpreter_error((3, 9, 6), '/usr/bin/python3')
check('suite: an old interpreter is a failure message',
      (_suite_old or '').startswith('FAIL:'), True)
check('suite: the message names the running version', '3.9.6' in (_suite_old or ''), True)
# MUST-MISS: exactly the floor runs the suite.
check('suite: exactly the floor is accepted (control)',
      _suite_interpreter_error((3, 11, 0), '/usr/bin/python3'), None)

# MUST-HIT: a module that sys.exit(0)s at import -- the shape of bin/roadmap's
# own fail-open guard -- is a load FAILURE, never a module.
_exit_dir = tempfile.mkdtemp()
_exit_mod = os.path.join(_exit_dir, 'exits_at_import')
with open(_exit_mod, 'w', encoding='utf-8') as _fh:
    _fh.write('import sys\nsys.exit(0)\n')
# SystemExit is caught HERE too: if the guard in _load_module regressed, the
# fixture's exit would otherwise end this suite mid-run with code 0 -- the
# very false green this block exists to prevent.
try:
    _load_module('exits_at_import', _exit_mod)
    check('suite: an exit-0 at import is refused', 'loaded', 'refused')
except SystemExit:
    check('suite: an exit-0 at import is refused', 'SystemExit escaped', 'refused')
except RuntimeError as _exc:
    check('suite: an exit-0 at import is refused', 'code 0' in str(_exc), True)
# MUST-MISS control: an ordinary module loads and is usable, so the refusal
# above is about the exit, not the loader failing on everything.
_ok_mod = os.path.join(_exit_dir, 'loads_fine')
with open(_ok_mod, 'w', encoding='utf-8') as _fh:
    _fh.write('VALUE = 42\n')
check('suite: an ordinary module still loads (control)',
      _load_module('loads_fine', _ok_mod).VALUE, 42)


# --- version parsing ------------------------------------------------------
VERSION_MUST_PARSE = [
    ('plain',            'v0.16.0',                     (0, 16, 0)),
    ('no v prefix',      '0.16.0',                      (0, 16, 0)),
    ('double digit',     'v0.16.10',                    (0, 16, 10)),
]
VERSION_MUST_NOT_PARSE = [
    ('prerelease',       'v0.11.0-beta'),
    ('two components',   'v0.16'),
    ('empty',            ''),
    ('words',            'latest'),
]

for label, text, want in VERSION_MUST_PARSE:
    check('parse_version ' + label, rm.parse_version(text), want)
for label, text in VERSION_MUST_NOT_PARSE:
    check('parse_version rejects ' + label, rm.parse_version(text), None)

# SemVer ordering must be numeric, not lexical. v0.9.0 < v0.10.0 is the case
# a string sort gets backwards, and it is why this is asserted rather than
# assumed.
check('semver order not lexical',
      sorted([rm.parse_version('v0.10.0'), rm.parse_version('v0.9.0')]),
      [(0, 9, 0), (0, 10, 0)])

# --- label -> version -----------------------------------------------------
check('label of this repo',
      rm.version_of_label('release:acme-app-v0.16.0'), ('acme-app', (0, 16, 0)))
check('label of another repo',
      rm.version_of_label('release:acme-lib-v0.4.0'), ('acme-lib', (0, 4, 0)))
check('non-release label', rm.version_of_label('work:available'), None)
check('release label, unparseable version',
      rm.version_of_label('release:acme-app-vNEXT'), None)

check('release_versions filters to REPO',
      rm.release_versions(issue(labels=['release:acme-app-v0.17.0',
                                        'release:acme-lib-v0.4.0'])),
      [(0, 17, 0)])

# --- patch detection ------------------------------------------------------
check('minor is not patch', rm.is_patch((0, 16, 0)), False)
check('patch is patch', rm.is_patch((0, 16, 1)), True)

# --- auto-filed filter ----------------------------------------------------
HUMAN_MUST_KEEP = [
    ('no labels',            issue(labels=[])),
    ('ordinary label',       issue(labels=['security'])),
    ('release label',        issue(labels=['release:acme-app-v0.16.0'])),
]
HUMAN_MUST_DROP = [
    ('audit fingerprint',    issue(labels=['audit-fp:49943dc56f60'])),
    ('resource fingerprint', issue(labels=['resource-fp:abc'])),
    ('resource-watch',       issue(labels=['resource-watch'])),
    ('audit ack',            issue(labels=['audit-ack:49943dc56f60'])),
    ('mixed',                issue(labels=['security', 'resource-watch'])),
]
for label, row in HUMAN_MUST_KEEP:
    check('human keeps ' + label, rm.is_human_authored(row), True)
for label, row in HUMAN_MUST_DROP:
    check('human drops ' + label, rm.is_human_authored(row), False)

# --- security marking: the UNION, because neither marker alone is enough --
SEC_MUST_MATCH = [
    ('label only',        issue(labels=['security'], title='Refresh token reuse')),
    ('label uppercase',   issue(labels=['Security'], title='Refresh token reuse')),
    ('title only',        issue(labels=[], title='[SECURITY] Refresh does not revoke jti')),
    ('title mid-string',  issue(labels=[], title='acme-app: [SECURITY] SPF gap')),
    ('both',              issue(labels=['security'], title='[SECURITY] x')),
]
SEC_MUST_NOT_MATCH = [
    ('neither',           issue(labels=['ci'], title='lint stage is red')),
    ('word in prose',     issue(labels=[], title='improve security posture docs')),
    ('secscan label',     issue(labels=['secscan'], title='Aikido is inert')),
]
for label, row in SEC_MUST_MATCH:
    check('security marks ' + label, rm.is_security_marked(row), True)
for label, row in SEC_MUST_NOT_MATCH:
    check('security skips ' + label, rm.is_security_marked(row), False)

# --- C2: BEADS_DIR must never override workspace ---------------------------
# beads' own multi-workspace docs tell people to set BEADS_DIR. If _bd()
# inherited it unchanged, a caller with BEADS_DIR set in their shell would
# silently get bd's answer for THAT workspace instead of cfg['workspace'],
# even though `cwd` is set correctly -- a fully populated but UNRELATED
# board rendering under this install's own config. Prove it by
# monkeypatching subprocess.run to capture exactly what env it was handed.
_captured_bd_call = {}


def _fake_subprocess_run(argv, **kw):
    _captured_bd_call['env'] = kw.get('env')
    _captured_bd_call['cwd'] = kw.get('cwd')

    class R:
        returncode = 0
        stdout = '[]'
    return R()


_orig_subprocess_run = rm.subprocess.run
_orig_beads_dir = os.environ.get('BEADS_DIR')
os.environ['BEADS_DIR'] = '/some/unrelated/other/workspace/.beads'
rm.subprocess.run = _fake_subprocess_run
try:
    rm._bd('bd', ['list'], 10, cfg={'workspace': '/the/configured/workspace'})
finally:
    rm.subprocess.run = _orig_subprocess_run
    if _orig_beads_dir is None:
        os.environ.pop('BEADS_DIR', None)
    else:
        os.environ['BEADS_DIR'] = _orig_beads_dir

# MUST-HIT: BEADS_DIR is gone from the subprocess environment even though it
# was set (and non-empty) in the caller's own environment throughout the call.
check('_bd strips BEADS_DIR from the subprocess environment (C2)',
      'BEADS_DIR' in (_captured_bd_call.get('env') or {}), False)
# Control: cwd is still exactly cfg['workspace'] -- proves workspace, not
# some other mechanism, is what decides the target now.
check('_bd still passes cwd as the configured workspace (control)',
      _captured_bd_call.get('cwd'), '/the/configured/workspace')
# MUST-MISS: a real, populated environment was passed (not None, not {}) --
# proves the assertion above is a targeted removal, not a null env that
# would trivially lack every key including BEADS_DIR.
check('_bd passes a real, non-empty environment, not a wipe',
      isinstance(_captured_bd_call.get('env'), dict)
      and len(_captured_bd_call['env']) > 0, True)
check('_bd environment still carries an unrelated variable (PATH) (control)',
      'PATH' in (_captured_bd_call.get('env') or {}), True)

# --- model ----------------------------------------------------------------
def tagged(v, **kw):
    kw.setdefault('labels', [])
    kw['labels'] = list(kw['labels']) + ['release:acme-app-' + v]
    return issue(**kw)


OPEN = [
    # v0.16.0 leaves
    tagged('v0.16.0', id='f-business', issue_type='feature', priority=1, title='Business Mode'),
    tagged('v0.16.0', id='b-cred', issue_type='bug', priority=1,
           title='GET system settings returns every credential unredacted'),
    tagged('v0.16.0', id='t-dns', issue_type='task', priority=3, title='DNS validator'),
    # a gating EPIC on v0.18.0, plus one of its children also tagged
    tagged('v0.18.0', id='mailha-1', issue_type='epic', priority=2, title='prod mail HA'),
    tagged('v0.18.0', id='mailha-1.1', issue_type='task', priority=3, title='stage 2'),
    # unscheduled
    issue(id='u-p0', issue_type='feature', priority=0, title='Classifier Interface'),
    issue(id='u-epic', issue_type='epic', priority=2, title='Unified Console'),
    issue(id='u-task', issue_type='task', priority=2, title='not a roadmap line'),
    # hotfix arms
    issue(id='h-bug', issue_type='bug', priority=1, title='prod credentials exposed'),
    issue(id='h-sec', issue_type='bug', priority=2, title='[SECURITY] jti not revoked'),
    issue(id='h-p2bug', issue_type='bug', priority=2, title='ordinary P2 bug'),
    issue(id='h-p3sec', issue_type='bug', priority=3, title='[SECURITY] low severity'),
    # auto-filed noise must never reach any bucket
    issue(id='noise', issue_type='bug', priority=1, labels=['resource-watch'], title='disk'),
]
CLOSED = [tagged('v0.16.0', id='done-1', issue_type='task', priority=3, title='done')]
TAGS = [(0, 15, 0), (0, 14, 1)]

M = rm.build_model(OPEN, CLOSED, TAGS)

check('cut version', M['cut'], (0, 15, 0))
check('in flight', M['in_flight'], (0, 16, 0))
check('planned', M['planned'], [(0, 18, 0)])

# Epic exclusion: mailha-1 is an epic on v0.18.0 and must contribute ZERO to
# the counts while still appearing under gates. rot-1 has 51 dependents in
# real life; rolling those in would make a version's count meaningless.
v18 = M['versions'][(0, 18, 0)]
check('epic not in leaves', [i['id'] for i in v18['leaves_open']], ['mailha-1.1'])
check('epic in gates', [i['id'] for i in v18['gates']], ['mailha-1'])

v16 = M['versions'][(0, 16, 0)]
check('v16 open leaf count', len(v16['leaves_open']), 3)
check('v16 closed leaf count', v16['leaves_closed'], 1)
check('v16 leaf order puts P1 feature first',
      [i['id'] for i in v16['leaves_open']], ['f-business', 'b-cred', 't-dns'])

# Unscheduled is features and epics only -- a task with no version is not a
# roadmap line, and auto-filed rows never appear.
check('unscheduled ids', [i['id'] for i in M['unscheduled']], ['u-p0', 'u-epic'])

# Hotfix queue: P0-P1 bug OR security-marked P0-P2. The P1 bug arm is the
# BACKSTOP for unmarked security work -- b-cred is exactly that case in real
# life, but it is already versioned, so the queue holds only unversioned rows.
check('hotfix ids', [i['id'] for i in M['hotfix']], ['h-bug', 'h-sec'])
check('hotfix excludes ordinary P2 bug',
      'h-p2bug' in [i['id'] for i in M['hotfix']], False)
check('hotfix excludes P3 security',
      'h-p3sec' in [i['id'] for i in M['hotfix']], False)
check('hotfix excludes auto-filed',
      'noise' in [i['id'] for i in M['hotfix']], False)

# MUST-MISS on the whole model: a version nobody created has no entry.
check('absent version absent', (9, 99, 9) in M['versions'], False)

# Horizon-empty shape: with no labels above the cut tag there is no in-flight
# version at all, which is what condition 1 keys on.
EMPTY = rm.build_model([issue(id='x')], [], [(0, 15, 0)])
check('no in flight when nothing tagged', EMPTY['in_flight'], None)
check('no planned when nothing tagged', EMPTY['planned'], [])

# PATCH EXEMPTION. A dot release is unplanned by SemVer definition, and the
# whole hotfix design depends on being able to cut one without roadmapping it.
# MUST-MISS: a patch never appears as a planned version.
PATCH = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.16.1', id='fix')],
                       [], [(0, 15, 0)])
check('patch is not a planned version', PATCH['planned'], [])
check('patch does not displace the in-flight minor', PATCH['in_flight'], (0, 16, 0))
# MUST-HIT control on the same fixture: a MINOR in the same position IS
# planned, which proves the filter is discriminating and not just empty.
MINOR = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='next')],
                       [], [(0, 15, 0)])
check('control — a minor IS planned', MINOR['planned'], [(0, 17, 0)])
# A patch in flight is legitimate -- that is a hotfix shipping.
INFLIGHT_PATCH = rm.build_model([tagged('v0.15.1', id='hf')], [], [(0, 15, 0)])
check('a patch may be in flight', INFLIGHT_PATCH['in_flight'], (0, 15, 1))

# --- I5 (github-kkq4a): no tags means nothing is in flight ----------------
# With tags == [], cut is None, so `above` admitted EVERY version and
# in_flight became the LOWEST one -- an already-shipped release rendering as
# in progress. Nothing has been cut, so nothing is in flight and every
# labelled version is ahead of us.
NT_OPEN = [tagged('v0.16.0', id='a', issue_type='feature'),
           tagged('v0.18.0', id='b', issue_type='feature'),
           tagged('v0.16.1', id='c', issue_type='bug', priority=1)]
NT = rm.build_model(NT_OPEN, [], [])
check('no tags: nothing is in flight', NT['in_flight'], None)
check('no tags: the model says so', NT['no_tags'], True)
check('no tags: every non-patch version is planned',
      NT['planned'], [(0, 16, 0), (0, 18, 0)])

# MUST-MISS control: WITH a tag, in_flight is the lowest version ABOVE it and
# planned excludes it -- the pre-existing behaviour, unchanged.
WT = rm.build_model(NT_OPEN, [], [(0, 15, 0)])
check('with a tag: in_flight is the lowest above the cut (control)',
      WT['in_flight'], (0, 16, 0))
check('with a tag: planned excludes the in-flight version (control)',
      WT['planned'], [(0, 18, 0)])
check('with a tag: no_tags is False (control)', WT['no_tags'], False)

# --- conditions -----------------------------------------------------------
def conds(model, state, today='2026-11-01'):
    return {c['id']: c for c in rm.evaluate(model, state, today)}


FRESH = {'last_reported_at': 0.0, 'convention_start': '2026-09-20', 'baselines': {}}


def state(**kw):
    s = dict(FRESH)
    s['baselines'] = dict(FRESH['baselines'])
    s.update(kw)
    return s


# --- defect: convention_start must not inherit a stale literal (github-cnzq7)
# MUST-HIT: an absent state file seeds TODAY, so warm-up starts at install.
_nostate = os.path.join(tempfile.mkdtemp(), 'nope.json')
check('absent state seeds convention_start to today',
      rm.load_state(_nostate, today='2027-03-01')['convention_start'],
      '2027-03-01')

# MUST-MISS: a state file that HAS the key keeps it. Seeding on every load
# would restart warm-up forever and silence condition 3 permanently.
_haskey = os.path.join(tempfile.mkdtemp(), 's.json')
with open(_haskey, 'w') as _fh:
    json.dump({'convention_start': '2026-09-20'}, _fh)
check('an existing convention_start is preserved',
      rm.load_state(_haskey, today='2027-03-01')['convention_start'],
      '2026-09-20')

# The regression itself: a cold board long after the old literal must stay
# SILENT, because its convention is one day old, not five months.
_COLD = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
_COLD['throughput'] = {'on_plan_share_14d': 0.0}
_cold_state = rm.load_state(_nostate, today='2027-03-01')
check('c3 silent during a freshly seeded warm-up',
      3 in conds(_COLD, _cold_state, today='2027-03-01'), False)

# MUST-HIT control: the SAME board with an elapsed warm-up DOES report it,
# so the silence above is the warm-up working, not condition 3 being dead.
_warm_state = dict(_cold_state, convention_start='2027-01-01')
check('c3 fires once warm-up has elapsed',
      3 in conds(_COLD, _warm_state, today='2027-03-01'), True)

# --- defect (fix round 1): the board's "no on-plan claim yet" note must
# print the PER-INSTALL convention_start threaded through the model, never
# a module literal (github-cnzq7). Before this fix, render_board read the
# now-deleted CONVENTION_START directly, so a fresh install that correctly
# seeded convention_start to its install date (the A1 fix above) still told
# the user warm-up "started 2026-09-20" -- the exact literal A1 removed,
# reintroduced through a second door.
_CS_MODEL = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
_CS_MODEL['throughput'] = {'on_plan_share_14d': None}  # gates the note
_CS_MODEL['convention_start'] = '2027-05-05'
_cs_board = rm.render_board(_CS_MODEL, [])
check('board prints the threaded convention_start',
      '2027-05-05' in _cs_board, True)

# MUST-MISS: the old literal must not survive beside the derived value.
# Without this the fix could add the real date and leave the frozen one
# printed too -- the same trap A2's must-miss covers for condition 1.
check('board no longer prints the old hardcoded convention_start',
      '2026-09-20' in _cs_board, False)

# --- defect (fix round 2): the "no convention_start on the model" fallback
# must NOT substitute today() -- that is a guess wearing the costume of a
# fact, the same error as the literal fix round 1 removed. Two PRE-EXISTING
# fixtures (FUTURE_MODEL, DEFAULT_MODEL further down) exercised this exact
# fallback by omission and asserted nothing about which date came out, so
# the bug shipped in fix round 1 and passed. This pair is the assertion
# that would have caught it: it must genuinely fail against a today()
# fallback (verified against the fix-round-1 commit before the fix below
# was written) and pass only once the line says the start is unknown.
_NOCS_MODEL = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
_NOCS_MODEL['throughput'] = {'on_plan_share_14d': None}  # gates the note
# convention_start deliberately NOT set on this model.
_nocs_board = rm.render_board(_NOCS_MODEL, [])
check('board says the convention start is unknown when the model has none',
      'convention start unknown' in _nocs_board, True)

# MUST-MISS: no guessed date -- specifically not TODAY, which is exactly
# what render_board silently substituted before this fix.
check('board does not guess today() for a missing convention_start',
      datetime.date.today().isoformat() in _nocs_board, False)


# Condition 1: horizon empty. MUST fire when nothing is tagged above the
# in-flight version; MUST NOT fire once something is.
C1_EMPTY = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
C1_FULL = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b')],
                         [], [(0, 15, 0)])
check('c1 fires on empty horizon', 1 in conds(C1_EMPTY, state()), True)
check('c1 silent with a planned version', 1 in conds(C1_FULL, state()), False)
check('c1 bypasses the throttle', conds(C1_EMPTY, state())[1]['bypass'], True)
# c1 lines content: a mutation renaming 'lines' to 'text' must be caught, not
# just a header/footer around nothing. Also covers the hook's property-5
# remediation text: `bd label add`, and the label going LAST.
_c1_lines = conds(C1_EMPTY, state())[1]['lines']
check('c1 lines non-empty', len(_c1_lines) > 0, True)
check('c1 lines mention HORIZON EMPTY', 'HORIZON EMPTY' in '\n'.join(_c1_lines), True)
check('c1 lines carry the bd label add remediation',
      'bd label add' in '\n'.join(_c1_lines), True)
check('c1 lines say the label goes last',
      'LABEL GOES LAST' in '\n'.join(_c1_lines), True)

# --- defect: condition 1 must DERIVE its example version (github-cnzq7) ----
# C1_EMPTY has cut v0.15.0 and in-flight v0.16.0, so the next feature
# version to plan into is v0.17.0 -- a MINOR bump, not the patch bump
# condition 5 uses for hotfixes.
check('c1 names the next MINOR after in-flight',
      'release:acme-app-v0.17.0' in ' '.join(conds(C1_EMPTY, state())[1]['lines']),
      True)

# MUST-MISS: the literal it replaced has to be GONE. Without this the fix
# could add a derived line and leave the wrong one beside it.
check('c1 no longer names a hardcoded v0.18.0',
      'v0.18.0' in ' '.join(conds(C1_EMPTY, state())[1]['lines']),
      False)

# With nothing in flight there is no version to bump, so the message must
# degrade to a placeholder rather than inventing v1.0.0 or crashing.
C1_NO_INFLIGHT = rm.build_model([], [], [(0, 15, 0)])
check('c1 uses a placeholder when nothing is in flight',
      '<version>' in ' '.join(conds(C1_NO_INFLIGHT, state())[1]['lines']),
      True)

# Condition 2: scope creep, measured against a baseline. No baseline -> NO
# creep line, and specifically never "+0", which would assert an absence that
# was not measured.
CREEP = rm.build_model(
    [tagged('v0.16.0', id='a'), tagged('v0.16.0', id='b'), tagged('v0.17.0', id='p')],
    [], [(0, 15, 0)])
check('c2 silent without a baseline', 2 in conds(CREEP, state()), False)
check('c2 fires against a baseline',
      2 in conds(CREEP, state(baselines={'0.16.0': ['a']})), True)
check('c2 silent when set matches baseline',
      2 in conds(CREEP, state(baselines={'0.16.0': ['a', 'b']})), False)

# I7: remediation text names the bare `roadmap` a plugin install puts on
# PATH, not the origin-workspace-relative `bin/roadmap`.
_c2_lines = conds(CREEP, state(baselines={'0.16.0': ['a']}))[2]['lines']
check('c2 remediation uses bare roadmap', 'roadmap pin' in '\n'.join(_c2_lines), True)
check('c2 remediation does not name bin/roadmap (I7)',
      'bin/roadmap' in '\n'.join(_c2_lines), False)

# Condition 2 carve-out: a hotfix member pulled into the in-flight version is
# NEVER creep. Without this the creep detector fights the escalation policy.
CREEP_HOTFIX = rm.build_model(
    [tagged('v0.16.0', id='a'),
     tagged('v0.16.0', id='sec', issue_type='bug', priority=1, title='[SECURITY] x')],
    [], [(0, 15, 0)])
check('c2 exempts a hotfix addition',
      2 in conds(CREEP_HOTFIX, state(baselines={'0.16.0': ['a']})), False)

# Condition 3: off-plan share, SUPPRESSED during warm-up. Suppressed means
# ABSENT, not zero and not hedged -- a number whose true cause is the
# convention's age would train the reader to ignore the hook.
check('c3 suppressed inside warm-up',
      3 in conds(C1_FULL, state(), today='2026-09-25'), False)
check('warmup_active inside window', rm.warmup_active(state(), '2026-09-25'), True)
check('warmup_active outside window', rm.warmup_active(state(), '2026-10-05'), False)

# Condition 3 MUST-HIT / MUST-MISS. Every fixture reaching conds() elsewhere
# in this suite has throughput == {}, so share is always None and this
# branch was previously unreachable -- a mutation deleting condition 3
# outright, or loosening its threshold to `share < 0.0`, left the suite
# green. today='2026-11-01' is well past the warm-up window.
C3_FIRE = dict(C1_FULL)
C3_FIRE['throughput'] = {'on_plan_share_14d': 0.1}
check('c3 fires below the 40% threshold after warm-up',
      3 in conds(C3_FIRE, state(), today='2026-11-01'), True)
check('c3 line reports the percentage',
      conds(C3_FIRE, state(), today='2026-11-01')[3]['lines'][0],
      'OFF-PLAN -- 10% of the last 14 days of human-authored closes were'
      ' in a release set.')
# MUST-MISS: a share above the threshold does not fire.
C3_CLEAN = dict(C1_FULL)
C3_CLEAN['throughput'] = {'on_plan_share_14d': 0.9}
check('c3 silent above the 40% threshold (control)',
      3 in conds(C3_CLEAN, state(), today='2026-11-01'), False)

# Condition 4: unscheduled P0/P1 feature or epic.
C4 = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b'),
                     issue(id='u', issue_type='feature', priority=0, title='P0')],
                    [], [(0, 15, 0)])
check('c4 fires on an unscheduled P0', 4 in conds(C4, state()), True)
check('c4 bypasses the throttle', conds(C4, state())[4]['bypass'], True)
check('c4 silent when none', 4 in conds(C1_FULL, state()), False)
_c4_lines = conds(C4, state())[4]['lines']
check('c4 lines non-empty', len(_c4_lines) > 0, True)
check('c4 lines mention UNSCHEDULED P0/P1', 'UNSCHEDULED P0/P1' in '\n'.join(_c4_lines), True)
# MUST-MISS: a P2 feature with no version is backlog, not a planning bug.
C4_P2 = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b'),
                        issue(id='u2', issue_type='feature', priority=2)],
                       [], [(0, 15, 0)])
check('c4 silent on a P2 feature', 4 in conds(C4_P2, state()), False)

# Condition 5: hotfix queue. P0/P1 bypasses the throttle; a P2-only queue does
# not, because nine lines every session is how a hook gets torn out.
C5_P1 = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b'),
                        issue(id='h', issue_type='bug', priority=1, title='creds exposed')],
                       [], [(0, 15, 0)])
C5_P2 = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b'),
                        issue(id='h2', issue_type='bug', priority=2, title='[SECURITY] x')],
                       [], [(0, 15, 0)])
check('c5 fires on a P1 bug', 5 in conds(C5_P1, state()), True)
check('c5 P1 bypasses throttle', conds(C5_P1, state())[5]['bypass'], True)
check('c5 fires on a P2 security issue', 5 in conds(C5_P2, state()), True)
check('c5 P2 does NOT bypass throttle', conds(C5_P2, state())[5]['bypass'], False)
check('c5 silent on an empty queue', 5 in conds(C1_FULL, state()), False)
_c5_lines = conds(C5_P1, state())[5]['lines']
check('c5 lines non-empty', len(_c5_lines) > 0, True)
check('c5 lines mention HOTFIX QUEUE', 'HOTFIX QUEUE' in '\n'.join(_c5_lines), True)

# TOTAL SILENCE is reachable. If it is not, the hook is a nag and gets removed.
check('all clean -> no conditions', rm.evaluate(C1_FULL, state(), '2026-09-25'), [])

# --- fix round 1: condition 2 must not be silenced by an empty baseline ---
# A version becomes in_flight as soon as ANY issue references it, open or
# closed -- so a version whose only tagged issue is already closed baselines
# to []. `if base:` treated that recorded-empty baseline the same as
# no-baseline-at-all, permanently and silently disabling creep detection for
# that version. The fix distinguishes "key absent" from "key present, value
# []" via `is not None`.

# MUST-HIT: baseline recorded as [] with a non-empty current set -- every
# current member arrived after the baseline, so all of it is reported added.
check('c2 fires when baseline was recorded empty',
      2 in conds(C1_FULL, state(baselines={'0.16.0': []})), True)
check('c2 empty-baseline reports every current member as added',
      conds(C1_FULL, state(baselines={'0.16.0': []}))[2]['lines'][0],
      'SCOPE CREEP -- v0.16.0 was 0 issues at baseline, now 1 (+1 added).')

# MUST-MISS control: with NO '0.16.0' key at all (the original no-baseline
# case), condition 2 must still stay silent -- proves the fix touched only
# the recorded-empty-list case, not the absent-key case.
check('c2 still silent with no baseline key recorded at all (control)',
      2 in conds(C1_FULL, state()), False)

# MUST-MISS: baseline recorded as [] AND the in-flight version's current set
# is also empty (its only tagged issue is closed, none open) -- nothing was
# added, so no creep line. This is the exact scenario the finding named: a
# version becomes in_flight from a CLOSED reference alone.
CREEP_EMPTY_INFLIGHT = rm.build_model(
    [tagged('v0.17.0', id='b')],
    [tagged('v0.16.0', id='closed-a')],
    [(0, 15, 0)])
check('setup: closed-only tag still makes the version in-flight',
      CREEP_EMPTY_INFLIGHT['in_flight'], (0, 16, 0))
check('c2 silent when baseline and current are both empty',
      2 in conds(CREEP_EMPTY_INFLIGHT, state(baselines={'0.16.0': []})), False)

# --- fix round 1: load_state / save_state coverage ------------------------
# Every earlier assertion injects a state() dict directly, so the real
# file read/write path -- and design rule 9 (absent/corrupt state behaves
# like "never reported", never like "just reported") -- was previously
# verified only by reading the code.

with tempfile.TemporaryDirectory() as _d:
    # Missing file -> defaults, not an exception and not "just reported".
    # convention_start seeds to the passed today (github-cnzq7), not the
    # module literal -- pinned here so the assertion stays deterministic.
    _missing = os.path.join(_d, 'nested', 'does-not-exist.json')
    _s = rm.load_state(_missing, today='2027-01-15')
    check('load_state missing file: last_reported_at', _s['last_reported_at'], 0.0)
    check('load_state missing file: convention_start', _s['convention_start'],
          '2027-01-15')
    check('load_state missing file: baselines', _s['baselines'], {})

with tempfile.TemporaryDirectory() as _d:
    # Corrupt file -> same defaults as missing, never "just reported".
    # Same today-seeding as the missing-file case above (github-cnzq7).
    _corrupt = os.path.join(_d, 'state.json')
    with open(_corrupt, 'w') as _fh:
        _fh.write('not json at all')
    _s = rm.load_state(_corrupt, today='2027-01-15')
    check('load_state corrupt file: last_reported_at', _s['last_reported_at'], 0.0)
    check('load_state corrupt file: convention_start', _s['convention_start'],
          '2027-01-15')
    check('load_state corrupt file: baselines', _s['baselines'], {})

with tempfile.TemporaryDirectory() as _d:
    # Round trip through a not-yet-existing nested directory (save_state
    # must create it) -- baselines and last_reported_at survive intact.
    _path = os.path.join(_d, 'nested', 'state.json')
    _to_save = {'last_reported_at': 999.5, 'convention_start': '2026-09-20',
                'baselines': {'0.16.0': ['a', 'b']}}
    rm.save_state(_path, _to_save)
    _loaded = rm.load_state(_path)
    check('save/load round-trip: baselines', _loaded['baselines'],
          {'0.16.0': ['a', 'b']})
    check('save/load round-trip: last_reported_at', _loaded['last_reported_at'], 999.5)

with tempfile.TemporaryDirectory() as _d:
    # MUST-HIT control proving the defaults assertions above actually
    # discriminate: a valid file with a real last_reported_at loads THAT
    # value, not the 0.0 default.
    _valid = os.path.join(_d, 'state.json')
    with open(_valid, 'w') as _fh:
        _fh.write('{"last_reported_at": 12345.0, "convention_start": '
                  '"2026-01-01", "baselines": {}}')
    _s = rm.load_state(_valid)
    check('load_state valid file loads its real last_reported_at (control)',
          _s['last_reported_at'], 12345.0)

# --- I3 (github-kkq4a): one config, one state file ------------------------
# --state defaulted to ~/.claude/roadmap-cadence-state.json for every
# workspace, and NOTHING in the file was keyed by workspace. Five fields
# collided: last_cut, baselines (bare-version keys), convention_start,
# last_reported_at and unconfigured_reported. The reviewer hit it by accident
# -- a run from a scratch repo overwrote the live last_cut.
with tempfile.TemporaryDirectory() as _d:
    _cfg_path = os.path.join(_d, 'roadmap.toml')
    with open(_cfg_path, 'w') as _fh:
        _fh.write('workspace = "."\ntag_repo = "."\n'
                  'release_namespace = "acme-app"\n')
    _loaded = rm.load_config(_cfg_path, today='2026-09-21')
    check('load_config reports where it loaded from',
          _loaded['config_path'], os.path.realpath(_cfg_path))
    check('state defaults beside roadmap.toml',
          rm.default_state_path(_loaded),
          os.path.join(os.path.realpath(_d), '.roadmap-state.json'))

# Two configs in two directories resolve to two DIFFERENT state paths. This is
# the whole point: the same assertion with the old global constant would give
# one path for both.
with tempfile.TemporaryDirectory() as _d1, tempfile.TemporaryDirectory() as _d2:
    _paths = []
    for _d in (_d1, _d2):
        _p = os.path.join(_d, 'roadmap.toml')
        with open(_p, 'w') as _fh:
            _fh.write('workspace = "."\ntag_repo = "."\n'
                      'release_namespace = "acme-app"\n')
        _paths.append(rm.default_state_path(rm.load_config(_p, today='2026-09-21')))
    check('two workspaces get two state files', _paths[0] != _paths[1], True)

# A hand-configured caller (no config_path -- TEST_CFG is exactly this) falls
# back to the legacy global path instead of raising KeyError.
check('a cfg with no config_path falls back to the legacy path',
      rm.default_state_path(TEST_CFG), rm.LEGACY_STATE)

# config_path is NOT a writable TOML key: the unknown-key guard still refuses
# it, so a user cannot set it by hand and desync the two.
with tempfile.TemporaryDirectory() as _d:
    _p = os.path.join(_d, 'roadmap.toml')
    with open(_p, 'w') as _fh:
        _fh.write('workspace = "."\ntag_repo = "."\n'
                  'release_namespace = "acme-app"\nconfig_path = "/tmp/x"\n')
    try:
        rm.load_config(_p, today='2026-09-21')
        check('config_path is rejected as an unknown TOML key', 'no raise', 'raised')
    except rm.RoadmapUnavailable as _exc:
        check('config_path is rejected as an unknown TOML key',
              'config_path' in str(_exc), True)

# --- throughput -----------------------------------------------------------
def closed_at(day, **kw):
    kw['updated_at'] = day + 'T12:00:00Z'
    return issue(**kw)


TP_CLOSED = [
    closed_at('2026-09-20', id='c1', labels=['release:acme-app-v0.15.0']),
    closed_at('2026-09-19', id='c2'),
    closed_at('2026-08-01', id='c3'),                      # outside 28d
    closed_at('2026-09-19', id='c4', labels=['resource-watch']),  # auto-filed
]
TAG_DATES = [((0, 15, 0), '2026-09-20'), ((0, 14, 1), '2026-09-19'),
             ((0, 12, 0), '2026-09-11'), ((0, 5, 0), '2026-03-04')]

TP = rm.compute_throughput([], TP_CLOSED, TAG_DATES, '2026-09-21', (0, 16, 0),
                           convention_start='2026-09-20')
check('closed_7d excludes auto-filed', TP['closed_7d'], 2)
check('closed_28d excludes the old one', TP['closed_28d'], 2)
check('in_release_7d', TP['in_release_7d'], 1)
check('tags_7d', TP['tags_7d'], 2)
check('tags_28d excludes the March tag', TP['tags_28d'], 3)

# MUST-MISS: during warm-up the share is ABSENT, not 0.0. A zero would read as
# a measured finding when its true cause is the convention's age.
check('share is None during warm-up',
      rm.compute_throughput([], TP_CLOSED, [], '2026-09-21', None,
                            convention_start='2026-09-20')['on_plan_share_14d'],
      None)
# 2026-10-04 is exactly CONVENTION_START + WARMUP_DAYS, the first day the
# claim is allowed. The 14-day window then reaches back to 2026-09-20 and
# catches c1 (release-labelled) but not c2, so the share is 1.0.
AFTER = rm.compute_throughput([], TP_CLOSED, [], '2026-10-04', None,
                              convention_start='2026-09-20')
check('share is a float on the unlock day', isinstance(AFTER['on_plan_share_14d'], float), True)
check('share value', AFTER['on_plan_share_14d'], 1.0)

# --- M9 (github-kkq4a): throughput counts THIS product's release sets ------
# compute_throughput used release_labels() (namespace-AGNOSTIC) where every
# version path uses release_versions(i, cfg) (namespace-FILTERED), so in a
# shared bd workspace another product's labels counted toward your on-plan
# share. TP_CLOSED alone cannot detect the fix -- its only labelled row is
# already in acme-app -- so this fixture adds a FOREIGN-namespace row.
TP_FOREIGN = TP_CLOSED + [
    closed_at('2026-09-20', id='c5', labels=['release:other-product-v1.0.0'])]
TP_NS = rm.compute_throughput([], TP_FOREIGN, TAG_DATES, '2026-09-21', (0, 16, 0),
                              convention_start='2026-09-20')
check('in_release_7d ignores a foreign namespace', TP_NS['in_release_7d'], 1)
# MUST-HIT control: the foreign row IS inside the window and IS human-authored,
# so the 1 above is namespace filtering and not the row being dropped for some
# unrelated reason. Without this, deleting c5 entirely would also pass.
check('closed_7d still counts the foreign row (control)', TP_NS['closed_7d'], 3)

# The share, on the same unlock day the AFTER fixture above uses. The 14-day
# window reaches back to 2026-09-20 and catches exactly c1 (acme-app) and c5
# (foreign): 1 of 2 after the fix, 2 of 2 before it.
AFTER_NS = rm.compute_throughput([], TP_FOREIGN, [], '2026-10-04', None,
                                 convention_start='2026-09-20')
check('on_plan_share_14d ignores a foreign namespace',
      AFTER_NS['on_plan_share_14d'], 0.5)

# The curve is the in-flight open count per day, reconstructed from updated_at
# on the version's CURRENT set. Six points, most recent last.
CURVE_OPEN = [tagged('v0.16.0', id='o1'), tagged('v0.16.0', id='o2')]
CURVE_CLOSED = [tagged('v0.16.0', id='c9', updated_at='2026-09-21T09:00:00Z')]
CV = rm.compute_throughput(CURVE_OPEN, CURVE_CLOSED, [], '2026-09-21', (0, 16, 0),
                           convention_start='2026-09-20')
check('curve has six points', len(CV['curve']), 6)
check('curve starts at the full set', CV['curve'][0], 3)
check('curve ends after the close', CV['curve'][-1], 2)
# MUST-MISS: with no in-flight version there is no curve to draw.
check('no curve without an in-flight version',
      rm.compute_throughput(CURVE_OPEN, CURVE_CLOSED, [], '2026-09-21', None,
                            convention_start='2026-09-20')['curve'], [])

# --- github-kkq4a: the convention_start fallback, both arms ---------------
# Every call site passes convention_start explicitly, so `if convention_start
# is None` was structurally unreachable from the suite. Arm 1: cfg supplied,
# parameter omitted -> cfg['convention_start']. TEST_CFG's is 2026-09-20, so
# on 2026-10-04 (the unlock day) the share is a real float, exactly as the
# explicit-parameter AFTER fixture above gets.
_FB = rm.compute_throughput([], TP_CLOSED, [], '2026-10-04', None)
check('convention_start falls back to cfg', _FB['on_plan_share_14d'], 1.0)
# MUST-MISS: the SAME call one day earlier is still inside the warm-up, so the
# share is None. Without this, a fallback returning any constant would pass.
check('the cfg fallback still honours warm-up',
      rm.compute_throughput([], TP_CLOSED, [], '2026-10-03', None)['on_plan_share_14d'],
      None)

# Arm 2: no cfg AND no module CONFIG -> datetime.date.today(). TP_CLOSED
# cannot be reused here: with no cfg AND CONFIG cleared, the resolved cfg is
# None and is_human_authored crashes on TypeError the moment it meets a
# LABELLED closed issue. convention_start's own fallback line runs fine
# first, but the function never reaches the on_plan_share_14d computation
# that would let us observe it. An unlabeled
# fixture sidesteps that unrelated crash -- labels_of() is empty, so the
# `cfg['auto_label_prefixes']` lookup never executes -- without masking the
# thing this arm actually tests.
#
# Asserting None here would NOT pin the fallback: if the fallback were gone,
# convention_start stays None, warmup_active's
# datetime.date.fromisoformat(None) raises, and its own
# `except Exception: return True` fail-open clause yields None too. Two
# causes, one observable. So drive `today` 60 days past the REAL clock --
# the fallback seeds from datetime.date.today(), not from the `today`
# parameter -- and assert a real float instead. A working fallback puts
# warm-up 60 days behind us; a broken one still returns None. (This
# deliberately pins current behaviour: if the fallback ever reads the
# `today` parameter instead of the clock, revisit this arm.)
_FB2_TODAY = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
_FB2_ROW = [closed_at((datetime.date.today() + datetime.timedelta(days=55)).isoformat(), id='fb2')]
_saved_cfg = rm.CONFIG
rm.configure(None)
try:
    _fb2 = rm.compute_throughput([], _FB2_ROW, [], _FB2_TODAY, None, cfg=None)
finally:
    rm.configure(_saved_cfg)
check('no cfg and no CONFIG falls back to today(), not the fail-open path',
      isinstance(_fb2['on_plan_share_14d'], float), True)
check('the unlabelled row gives a 0.0 share', _fb2['on_plan_share_14d'], 0.0)
check('CONFIG restored after the fallback arm (control)',
      rm.CONFIG['release_namespace'], 'acme-app')

# --- github-086tz: an explicit cfg governs the human-authored filter too ---
# compute_throughput resolved `cfg = cfg or CONFIG` and then called
# is_human_authored(i) bare, so the module CONFIG, not the passed cfg, decided
# which closed rows were auto-filed. OTHER_CFG drops 'resource-watch' from the
# prefixes, so c4 is human under it and auto-filed under TEST_CFG -- the one
# row that tells the two configs apart. LABELLED rows are the point: the
# Arm 2 fixture above is unlabelled and cannot see this.
OTHER_CFG = dict(TEST_CFG, auto_label_prefixes=('audit-fp:',))
check('an explicit cfg decides which rows are auto-filed',
      rm.compute_throughput([], TP_CLOSED, TAG_DATES, '2026-09-21', (0, 16, 0),
                            convention_start='2026-09-20',
                            cfg=OTHER_CFG)['closed_7d'], 3)
# MUST-HIT control: the SAME call with no cfg still reads the module CONFIG and
# excludes c4. Without it, a filter that ignored prefixes entirely would pass.
check('with no cfg the module CONFIG still decides (control)',
      rm.compute_throughput([], TP_CLOSED, TAG_DATES, '2026-09-21', (0, 16, 0),
                            convention_start='2026-09-20')['closed_7d'], 2)

# --- fix round 3: convention_start has ONE source, not two ----------------
# compute_throughput used to read the hardcoded module CONVENTION_START while
# evaluate() read state['convention_start'] -- an unparseable or future state
# value suppressed condition 3 permanently while the throughput share (still
# keyed off the module constant) came back as a real number, so the board's
# "no on-plan claim yet" disclosure never printed to explain why. One
# parameter, passed by main() as st['convention_start'], now governs both.
FUTURE_CS = '2027-01-01'
# '2026-10-04' is the unlock day used by the AFTER fixture above -- the one
# date, given TP_CLOSED's fixture dates, where the DEFAULT convention_start
# yields a real (non-None) share. Reused here so the future-vs-default
# comparison below isolates convention_start as the only variable.
TP_FUTURE = rm.compute_throughput([], TP_CLOSED, TAG_DATES, '2026-10-04', (0, 16, 0),
                                  convention_start=FUTURE_CS)
check('future convention_start suppresses the share (post real-warmup date)',
      TP_FUTURE['on_plan_share_14d'], None)

FUTURE_MODEL = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b')],
                              [], [(0, 15, 0)])
FUTURE_MODEL['throughput'] = TP_FUTURE
# convention_start threaded onto the model (fix round 1/2, github-cnzq7):
# without it render_board can't tell this fixture apart from one with no
# convention_start at all, and the date-in-the-board assertion below would
# be checking nothing real.
FUTURE_MODEL['convention_start'] = FUTURE_CS
check('condition 3 stays silent when state convention_start is in the future',
      3 in conds(FUTURE_MODEL, state(convention_start=FUTURE_CS), today='2026-10-04'), False)
future_board = rm.render_board(FUTURE_MODEL, [])
# Strengthened (fix round 2): the phrase alone passed even when render_board
# silently substituted the WRONG date (today(), not FUTURE_CS) for a missing
# model['convention_start'] -- this checks the actual date that was
# substituted, not just that some suppression note printed.
check('board prints the suppression note with the future convention_start',
      'convention started %s' % FUTURE_CS in future_board, True)

# MUST-HIT control: the SAME today, with the DEFAULT convention_start, yields
# a real share and no suppression note -- proving the future state value
# (not the date alone) is what caused the silence above.
TP_DEFAULT = rm.compute_throughput([], TP_CLOSED, TAG_DATES, '2026-10-04', (0, 16, 0),
                                   convention_start='2026-09-20')
check('control — default convention_start yields a real share on the same date',
      isinstance(TP_DEFAULT['on_plan_share_14d'], float), True)
DEFAULT_MODEL = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b')],
                               [], [(0, 15, 0)])
DEFAULT_MODEL['throughput'] = TP_DEFAULT
# Matches the '2026-09-20' passed to TP_DEFAULT's compute_throughput above --
# this fixture's semantic convention_start, not a guess (fix round 2).
DEFAULT_MODEL['convention_start'] = '2026-09-20'
default_board = rm.render_board(DEFAULT_MODEL, [])
check('control — board omits the suppression note once a real share exists',
      'no on-plan claim yet' in default_board, False)

# --- renderers ------------------------------------------------------------
BOARD_MODEL = rm.build_model(OPEN, CLOSED, TAGS)
BOARD_MODEL['throughput'] = TP
BOARD_CONDS = rm.evaluate(BOARD_MODEL, state(), '2026-11-01')

blob = rm.render_json(BOARD_MODEL, BOARD_CONDS)
parsed = json.loads(blob)
check('json has conditions', isinstance(parsed['conditions'], list), True)
check('json in_flight is a string', parsed['in_flight'], 'v0.16.0')
check('json planned is a list of strings', parsed['planned'], ['v0.18.0'])
check('json hotfix count', parsed['hotfix_count'], 2)
# The board distinguishes "no baseline yet" from "baselined, clean" -- the
# JSON surface (the spec's PRIMARY output) must carry the same distinction,
# or a future console page built on it reintroduces the defect.
check('json baseline absent when unmeasured', parsed.get('baseline'), None)
BOARD_MODEL_BASELINED_JSON = dict(BOARD_MODEL)
BOARD_MODEL_BASELINED_JSON['baseline'] = ['f-business', 'b-cred', 't-dns']
parsed_baselined = json.loads(rm.render_json(BOARD_MODEL_BASELINED_JSON, BOARD_CONDS))
check('json baseline present when measured', parsed_baselined.get('baseline'),
      ['f-business', 'b-cred', 't-dns'])

board = rm.render_board(BOARD_MODEL, BOARD_CONDS)
check('board names the cut version', 'cut v0.15.0' in board, True)
check('board shows the hotfix queue', 'HOTFIX QUEUE' in board, True)
check('board says cuttable independently', 'cuttable independently' in board.lower(), True)
# MUST-MISS: with no baseline the board says so rather than claiming +0.
check('board never claims +0 without a baseline', '+0' in board, False)
check('board says no baseline yet', 'no baseline yet' in board, True)
check('board reports tags cut', 'tags cut' in board, True)

# --- READ-ONLY: bin/roadmap must never be able to mutate bd ---------------
# STRUCTURAL, not a grep. `evaluate()` legitimately PRINTS the string
# "bd label add <id> release:..." as remediation text, so a substring search
# would fail on help text while telling you nothing about what actually runs.
# This walks the AST and inspects the argv literal of every subprocess.run.

# Every subcommand this tool can ever run reaches a subprocess as a string
# inside a LIST LITERAL -- `['list', '--status=open', …]` handed to _bd, or
# `['git', '-C', …]` handed straight to subprocess.run. So walking every list
# literal in the module covers both, where walking subprocess.run call sites
# would miss the _bd indirection entirely.
WRITE_VERBS = {'label', 'close', 'create', 'update', 'defer', 'compact',
               'gc', 'prune', 'dep', 'remember', 'edit', 'push', 'commit', 'tag'}
literals = [
    [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    for node in ast.walk(ast.parse(open(MODULE_PATH).read()))
    if isinstance(node, ast.List)
]
tokens = {tok for lit in literals for tok in lit}

# MUST-HIT control: if the walk finds nothing, the assertion below is vacuous
# and would pass against a file that shells out freely. 'list' must be there.
check('control — AST walk found the read verb', 'list' in tokens, True)
check('control — AST walk found the git read', 'for-each-ref' in tokens, True)
check('no write verb reaches any argv literal',
      sorted(tokens & WRITE_VERBS), [])
# Caps: the unscheduled section prints at most three rows plus a pointer.
# The old assertion used a 2-row fixture and `<= 3`, so a version printing
# ZERO rows would also have passed. Rebuild it with a 5-row fixture, assert
# EXACTLY 3 rows, and assert the "…N more" pointer names the hidden count.
UNSCHED_MANY = [issue(id='u%d' % k, issue_type='feature', priority=2, title='item %d' % k)
               for k in range(5)]
UNSCHED_MODEL = rm.build_model(UNSCHED_MANY, [], [])
UNSCHED_MODEL['throughput'] = {}
unsched_board = rm.render_board(UNSCHED_MODEL, [])
unsched_section = unsched_board.split('UNSCHEDULED')[1].split('THROUGHPUT')[0]
check('board caps unscheduled at exactly 3 rows',
      unsched_section.count('\n    P'), 3)
check('board shows the …more pointer for unscheduled overflow',
      '…2 more · /roadmap unscheduled' in unsched_section, True)

# --- creep: three states, not two ------------------------------------------
# A model carrying a baseline must NOT say "no baseline yet" -- that would
# report an absence of measurement where a measurement happened and found
# nothing.
BOARD_BASELINED = dict(BOARD_MODEL)
BOARD_BASELINED['baseline'] = ['f-business', 'b-cred', 't-dns']
board_b = rm.render_board(BOARD_BASELINED, [])
check('baselined board does not claim no baseline', 'no baseline yet' in board_b, False)
check('baselined board reports a clean measurement',
      'none since baseline (3 issues)' in board_b, True)
# Control: without a baseline key the original wording still appears, proving
# the branch is selecting rather than always taking one arm.
check('unbaselined board still says no baseline yet',
      'no baseline yet' in rm.render_board(BOARD_MODEL, []), True)

# Fourth state: NO in-flight version at all. "Nothing is in flight" and "in
# flight but unbaselined" are different facts -- the old code printed
# "no baseline yet" for both, conflating them.
no_inflight_board = rm.render_board(EMPTY, [])
check('creep says n/a when nothing is in flight',
      'creep:   n/a — no version in flight' in no_inflight_board, True)
check('creep n/a board does not say no baseline yet',
      'no baseline yet' in no_inflight_board, False)

# --- fix round 1 of 5: refresh_baselines gates on the cut tag advancing ---
# The spec is explicit, twice: condition 2 CANNOT fire on v0.16.0, because it
# became in-flight before this tool existed and has no plan-at-cut-time to
# measure against. Gating on "first time this key is seen" instead of "the
# cut tag advanced" baselines whatever happens to be in flight on the FIRST
# run -- an arbitrary moment -- which produces exactly the false-clean signal
# `no baseline yet` exists to prevent.

# MUST-MISS: a state file with no prior history (`last_cut` absent) writes NO
# baseline for the in-flight version, and records where the tag train stands.
RB_MODEL = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b')],
                          [], [(0, 15, 0)])
_rb1 = state()
_rb1_out = rm.refresh_baselines(RB_MODEL, _rb1)
check('fresh state (no last_cut) writes no baseline', _rb1_out['baselines'], {})
check('fresh state records the current cut as last_cut', _rb1_out['last_cut'], '0.15.0')

# MUST-MISS: last_cut already equal to the model's current cut -- no tag was
# cut since the previous run, so no baseline is written.
_rb2 = state(last_cut='0.15.0')
_rb2_out = rm.refresh_baselines(RB_MODEL, _rb2)
check('unchanged cut writes no baseline', _rb2_out['baselines'], {})
check('unchanged cut leaves last_cut alone', _rb2_out['last_cut'], '0.15.0')

# MUST-HIT control: last_cut OLDER than the model's current cut -- the tag
# train advanced since the last run, so the in-flight version's CURRENT set
# becomes its baseline. Without this control the fix would be
# indistinguishable from deleting the function outright.
_rb3 = state(last_cut='0.14.0')
_rb3_out = rm.refresh_baselines(RB_MODEL, _rb3)
check('advanced cut updates last_cut', _rb3_out['last_cut'], '0.15.0')
check('advanced cut baselines the in-flight version at its current set',
      _rb3_out['baselines'].get('0.16.0'), ['a'])

# MUST-MISS: same advancing-cut scenario, but a baseline already exists for
# that version -- it must not be overwritten (the pin command, or an earlier
# refresh, already recorded the plan).
_rb4 = state(last_cut='0.14.0', baselines={'0.16.0': ['already']})
_rb4_out = rm.refresh_baselines(RB_MODEL, _rb4)
check('existing baseline is not overwritten', _rb4_out['baselines']['0.16.0'], ['already'])
check('last_cut still advances even when the baseline was not written',
      _rb4_out['last_cut'], '0.15.0')

with tempfile.TemporaryDirectory() as _d:
    # load_state / save_state round-trip the new last_cut field.
    _rb_path = os.path.join(_d, 'state.json')
    rm.save_state(_rb_path, {'last_reported_at': 0.0, 'convention_start': '2026-09-20',
                             'baselines': {}, 'last_cut': '0.15.0'})
    _rb_loaded = rm.load_state(_rb_path)
    check('save/load round-trip: last_cut', _rb_loaded['last_cut'], '0.15.0')

# --- fix round 1: IN FLIGHT lists every item, PLANNED is features-only ----
# Spec: "In-flight lists every item -- it is the working set. Planned lists
# features only, collapsed." The old cap of 6 with no pointer silently hid
# items; live, v0.16.0 has 9 open leaves and the board said nothing about it.

# MUST-HIT: an in-flight version with 9 open leaves renders all 9, untruncated.
NINE_OPEN = [tagged('v0.20.0', id='n%d' % k, issue_type='task', priority=3, title='t%d' % k)
            for k in range(9)]
NINE_MODEL = rm.build_model(NINE_OPEN, [], [(0, 19, 0)])
NINE_MODEL['throughput'] = {}
nine_board = rm.render_board(NINE_MODEL, [])
in_flight_section = nine_board.split('IN FLIGHT')[1].split('PLANNED')[0]
check('in-flight section renders all 9 rows, no cap',
      in_flight_section.count('\n        P'), 9)
check('in-flight section has no …more pointer', '…' in in_flight_section, False)

# MUST-HIT: a planned version mixing features with non-features shows only
# the features, plus a pointer naming the hidden count.
MIX_PLANNED = [
    tagged('v0.16.0', id='a', issue_type='task', priority=3, title='keeps inflight nonempty'),
    tagged('v0.17.0', id='f1', issue_type='feature', priority=2, title='feat one'),
    tagged('v0.17.0', id='t1', issue_type='task', priority=3, title='task one'),
    tagged('v0.17.0', id='c1', issue_type='chore', priority=3, title='chore one'),
]
MIX_MODEL = rm.build_model(MIX_PLANNED, [], [(0, 15, 0)])
MIX_MODEL['throughput'] = {}
mix_board = rm.render_board(MIX_MODEL, [])
planned_section = mix_board.split('PLANNED')[1].split('UNSCHEDULED')[0]
check('planned shows only the feature', 'feat one' in planned_section, True)
check('planned hides the task', 'task one' in planned_section, False)
check('planned hides the chore', 'chore one' in planned_section, False)
check('planned names the hidden count', '…2 more · /roadmap v0.17.0' in planned_section, True)

# MUST-MISS control: a planned version whose rows are all features and all
# fit prints NO …more pointer -- proves the pointer is conditional, not
# always-on.
ALLFIT_PLANNED = [
    tagged('v0.16.0', id='a', issue_type='task', priority=3, title='keeps inflight nonempty'),
    tagged('v0.17.0', id='f1', issue_type='feature', priority=2, title='feat one'),
    tagged('v0.17.0', id='f2', issue_type='feature', priority=2, title='feat two'),
]
ALLFIT_MODEL = rm.build_model(ALLFIT_PLANNED, [], [(0, 15, 0)])
ALLFIT_MODEL['throughput'] = {}
allfit_board = rm.render_board(ALLFIT_MODEL, [])
check('planned with everything shown has no …more pointer (control)',
      '…' in allfit_board.split('PLANNED')[1].split('UNSCHEDULED')[0], False)

# --- fix round 1: the third creep arm, exercised through render_board ------
# When condition 2 fires, its own lines carry the creep report -- the board
# must print NEITHER "no baseline yet" NOR "none since baseline", or the
# reader would see the measurement stated twice, once correctly and once as
# a stale placeholder.
CREEP_COND = [{'id': 2, 'bypass': False,
              'lines': ['SCOPE CREEP -- v0.16.0 was 1 issues at baseline, now 2 (+1 added).']}]
CREEP_FIRING_MODEL = dict(BOARD_MODEL)
CREEP_FIRING_MODEL['baseline'] = ['x']
creep_board = rm.render_board(CREEP_FIRING_MODEL, CREEP_COND)
check('condition-2 board omits "no baseline yet"', 'no baseline yet' in creep_board, False)
check('condition-2 board omits "none since baseline"',
      'none since baseline' in creep_board, False)


# --- fix round 4: main() end to end, via monkeypatched load_issues/tag_dates
# These exercise real CLI-level behaviour (argument parsing, exit codes,
# stdout/stderr, the on-disk state file) without shelling to bd or git.
def _run_main(argv, open_issues=None, closed_issues=None, tag_dates=None,
              raise_unavailable=None, cfg=None):
    orig_li, orig_ltd = rm.load_issues, rm.load_tag_dates
    # main() (Task B3) now calls configure(load_config(...)) before
    # load_issues(). Stub load_config the same way load_issues/load_tag_dates
    # are stubbed below -- a real load_config() would walk up from cwd
    # looking for an actual roadmap.toml on disk, which does not exist in
    # this test environment (by design) and would make every _run_main call
    # take the RoadmapUnavailable branch regardless of what the test asked
    # for. Returning TEST_CFG keeps CONFIG exactly what the suite already
    # configured at import time.
    #
    # `cfg` overrides what that stub returns, for the arms that need a config
    # DIFFERING from TEST_CFG (github-kkq4a, I2: a config with no
    # convention_start at all). main() calls configure() on whatever comes
    # back, so the module global is restored explicitly below -- otherwise an
    # override would leak into every later assertion in the file.
    orig_lc = rm.load_config

    rm.load_config = lambda *a, **kw: dict(cfg if cfg is not None else TEST_CFG)

    def _li(*a, **kw):
        if raise_unavailable is not None:
            raise rm.RoadmapUnavailable(raise_unavailable)
        return (open_issues or [], closed_issues or [])

    rm.load_issues = _li
    rm.load_tag_dates = lambda *a, **kw: (tag_dates or [])
    out_buf, err_buf = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = rm.main(argv)
    finally:
        rm.load_issues = orig_li
        rm.load_tag_dates = orig_ltd
        rm.load_config = orig_lc
        rm.configure(TEST_CFG)
    return rc, out_buf.getvalue(), err_buf.getvalue()


# Finding 1: an unavailable bd/git must not render identically to a clean
# board. load_state is never reached on this path, so no --state is needed.
_rc, _out, _err = _run_main(['--today', '2026-11-01'], raise_unavailable='bd exited 1')
check('unavailable: exits 0 (fail open)', _rc, 0)
check('unavailable: reason reaches stderr', 'bd exited 1' in _err, True)
check('unavailable: stdout carries nothing in text mode', _out.strip(), '')

_rc, _out, _err = _run_main(['--json', '--today', '2026-11-01'],
                            raise_unavailable='bd exited 1')
check('unavailable --json: exits 0', _rc, 0)
_parsed_unavail = json.loads(_out)
check('unavailable --json: carries the reason',
      _parsed_unavail.get('unavailable'), 'bd exited 1')

# MUST-MISS control: a successful run's --json output carries no
# 'unavailable' key at all -- proves the key is conditional, not always-on.
with tempfile.TemporaryDirectory() as _d:
    _ok_state = os.path.join(_d, 'state.json')
    _rc, _out, _err = _run_main(['--json', '--state', _ok_state, '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[])
    check('successful run: exits 0', _rc, 0)
    _parsed_ok = json.loads(_out)
    check('successful run: no unavailable key (control)',
          'unavailable' in _parsed_ok, False)

# I3 (github-kkq4a): main() reports the resolved state path so the
# SessionStart hook can stamp the SAME file instead of computing its own.
with tempfile.TemporaryDirectory() as _d:
    _sp = os.path.join(_d, 'state.json')
    _rc, _out, _err = _run_main(['--json', '--state', _sp, '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[])
    check('--json reports the resolved state path',
          json.loads(_out).get('state_path'), _sp)

# I2 (github-kkq4a): roadmap.toml's convention_start must seed an ABSENT state
# file. load_state alone seeds its `today` argument, so before the fix every
# install that started from an absent state file (i.e. every install, once the
# state file became per-install) silently restarted its 14-day warm-up and
# rendered a convention-start date contradicting its own roadmap.toml.
# MUST-HIT: TEST_CFG's convention_start is 2026-09-20 and --today is
# 2026-11-01, so the two are distinguishable -- the state file must carry the
# CONFIGURED date.
with tempfile.TemporaryDirectory() as _d:
    _cs_state = os.path.join(_d, '.roadmap-state.json')
    _rc, _out, _err = _run_main(['--json', '--state', _cs_state,
                                 '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[])
    # Guarded: a mutation that stops the state file being written at all
    # would otherwise raise here and truncate every later arm instead of
    # failing this one. The fallback is {}, whose .get() is None -- which
    # equals none of the three dates asserted, so no arm passes vacuously.
    _cs = json.load(open(_cs_state)) if os.path.exists(_cs_state) else {}
    check('a configured convention_start seeds an absent state file',
          _cs.get('convention_start'), TEST_CFG['convention_start'])

# MUST-MISS control: a config carrying NO convention_start at all still seeds
# today, so the fix reads the key rather than hardcoding a second source of
# truth. (A config loaded through load_config always HAS the key -- it seeds
# today itself -- so this shape only reaches main() from a hand-built cfg,
# which is exactly what CONFIG.get() has to survive.)
with tempfile.TemporaryDirectory() as _d:
    _cs_state = os.path.join(_d, '.roadmap-state.json')
    _no_cs = {k: v for k, v in TEST_CFG.items() if k != 'convention_start'}
    _rc, _out, _err = _run_main(['--json', '--state', _cs_state,
                                 '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[],
                                cfg=_no_cs)
    _cs = json.load(open(_cs_state)) if os.path.exists(_cs_state) else {}
    check('an absent configured convention_start still seeds today (control)',
          _cs.get('convention_start'), '2026-11-01')

# MUST-MISS control: an EXISTING state file keeps its own convention_start --
# the config seeds an absent file, it does not overwrite a recorded warm-up
# start on every run (which would suppress condition 3 forever).
with tempfile.TemporaryDirectory() as _d:
    _cs_state = os.path.join(_d, '.roadmap-state.json')
    with open(_cs_state, 'w') as _fh:
        json.dump({'convention_start': '2026-05-05'}, _fh)
    _rc, _out, _err = _run_main(['--json', '--state', _cs_state,
                                 '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[])
    _cs = json.load(open(_cs_state)) if os.path.exists(_cs_state) else {}
    check('an existing convention_start survives a configured one (control)',
          _cs.get('convention_start'), '2026-05-05')

# --- C1 / I5 (github-kkq4a): the 0.1.x -> 0.2.0 state-move notice ---------
# There is deliberately no automatic migration -- seeding the new per-install
# file from the old global one would hand EVERY workspace the same baselines.
# The notice is the whole delivery mechanism, and stderr reaches nobody under
# the SessionStart hook (capture_output=True, p.stderr never read), so --json
# carries a flag the hook keys on. rm.LEGACY_STATE is monkeypatched to a temp
# path: the real one exists on a developer's machine and carries live state,
# which would make these arms pass or fail for the wrong reason.
_orig_legacy = rm.LEGACY_STATE
with tempfile.TemporaryDirectory() as _d:
    _legacy = os.path.join(_d, 'roadmap-cadence-state.json')
    with open(_legacy, 'w') as _fh:
        json.dump({'baselines': {'0.16.0': ['x']}, 'last_cut': '0.16.0'}, _fh)
    _new = os.path.join(_d, '.roadmap-state.json')
    rm.LEGACY_STATE = _legacy
    try:
        # MUST-HIT: legacy file present, new file absent.
        _rc, _out, _err = _run_main(['--json', '--state', _new,
                                     '--today', '2026-11-01'],
                                    open_issues=[], closed_issues=[], tag_dates=[])
        check('--json carries legacy_state_available when the legacy file is'
              ' the only one', json.loads(_out).get('legacy_state_available'), True)
        check('the notice names the legacy path', _legacy in _err, True)
        check('the notice names the new path', _new in _err, True)
        check('the notice gives the exact cp',
              'cp %s %s' % (_legacy, _new) in _err, True)
        # I5: the legacy file belongs to whichever workspace last wrote it, so
        # the notice must not claim it holds THIS install's baselines -- in
        # every other workspace that is false, and following it imports another
        # product's numbers. The three must-hits above prove the text is
        # non-empty, so this must-miss is not vacuous.
        check('the notice does not call them this install\'s baselines',
              'this install' in _err.lower(), False)
        check('the notice says the file may be another workspace\'s',
              'another workspace' in _err, True)
        check('the notice names the re-baseline escape hatch',
              'roadmap pin' in _err, True)

        # MUST-MISS control: the run above called save_state, so the new file
        # now exists -- the second run must go quiet in BOTH channels. The flag
        # is keyed on the new file's absence, not merely on the legacy file
        # being there.
        check('the first run created the new state file (control)',
              os.path.exists(_new), True)
        _rc, _out, _err = _run_main(['--json', '--state', _new,
                                     '--today', '2026-11-01'],
                                    open_issues=[], closed_issues=[], tag_dates=[])
        check('legacy_state_available is False once the new file exists',
              json.loads(_out).get('legacy_state_available'), False)
        check('the notice does not reprint once the new file exists',
              _err.strip(), '')
    finally:
        rm.LEGACY_STATE = _orig_legacy

# MUST-MISS control: no legacy file at all -- the overwhelmingly common case
# for a fresh install, where the right action is to say nothing.
with tempfile.TemporaryDirectory() as _d:
    rm.LEGACY_STATE = os.path.join(_d, 'no-such-legacy.json')
    try:
        _rc, _out, _err = _run_main(['--json',
                                     '--state', os.path.join(_d, 'state.json'),
                                     '--today', '2026-11-01'],
                                    open_issues=[], closed_issues=[], tag_dates=[])
        check('legacy_state_available is False with no legacy file',
              json.loads(_out).get('legacy_state_available'), False)
        check('no notice with no legacy file', _err.strip(), '')
    finally:
        rm.LEGACY_STATE = _orig_legacy

# I8: main()'s --json payload must carry `unconfigured` so the SessionStart
# hook can speak exactly once for a fresh install (no roadmap.toml at all)
# while staying silent for every other unavailable reason. This exercises
# the load_config()-raising branch directly (before _run_main's own stub,
# which always succeeds) since raise_unavailable only reaches load_issues.
_orig_load_config = rm.load_config
rm.load_config = lambda *a, **kw: (_ for _ in ()).throw(
    rm.RoadmapUnavailable('no roadmap.toml found; run `roadmap init`', unconfigured=True))
_unc_out, _unc_err = io.StringIO(), io.StringIO()
try:
    with contextlib.redirect_stdout(_unc_out), contextlib.redirect_stderr(_unc_err):
        _unc_rc = rm.main(['--json', '--today', '2026-11-01'])
finally:
    rm.load_config = _orig_load_config
check('unconfigured main() run exits 0', _unc_rc, 0)
_unc_parsed = json.loads(_unc_out.getvalue())
check('unconfigured main() --json carries unconfigured=True',
      _unc_parsed.get('unconfigured'), True)

# MUST-MISS control: an ordinary (non-unconfigured) RoadmapUnavailable at
# the SAME call site -- e.g. a malformed config -- must not set the flag.
rm.load_config = lambda *a, **kw: (_ for _ in ()).throw(
    rm.RoadmapUnavailable('bad.toml: unknown key(s): oops'))
_bad_out, _bad_err = io.StringIO(), io.StringIO()
try:
    with contextlib.redirect_stdout(_bad_out), contextlib.redirect_stderr(_bad_err):
        _bad_rc = rm.main(['--json', '--today', '2026-11-01'])
finally:
    rm.load_config = _orig_load_config
check('malformed-config main() run exits 0', _bad_rc, 0)
_bad_parsed = json.loads(_bad_out.getvalue())
check('malformed-config main() --json does NOT carry unconfigured=True (control)',
      _bad_parsed.get('unconfigured'), False)

# The fail-open contract is THREE claims, not one: exit 0, a NAMED reason on
# stderr, and nothing on stdout in text mode. Only the first was asserted on
# this path -- _unc_err and _bad_err were captured and dropped (github-kkq4a).
check('unconfigured main() names the reason on stderr',
      'roadmap: unavailable:' in _unc_err.getvalue(), True)
check('unconfigured main() stderr carries the specific reason',
      'no roadmap.toml found' in _unc_err.getvalue(), True)
check('malformed-config main() names the reason on stderr',
      'unknown key(s): oops' in _bad_err.getvalue(), True)

# TEXT MODE on the same branch, never exercised: both existing arms pass
# --json. An unavailable install must print NOTHING to stdout here -- a board
# and a silent failure must not be byte-identical.
rm.load_config = lambda *a, **kw: (_ for _ in ()).throw(
    rm.RoadmapUnavailable('no roadmap.toml found; run `roadmap init`', unconfigured=True))
_txt_out, _txt_err = io.StringIO(), io.StringIO()
try:
    with contextlib.redirect_stdout(_txt_out), contextlib.redirect_stderr(_txt_err):
        _txt_rc = rm.main(['--today', '2026-11-01'])
finally:
    rm.load_config = _orig_load_config
check('unconfigured text-mode run exits 0', _txt_rc, 0)
check('unconfigured text-mode run prints nothing to stdout',
      _txt_out.getvalue().strip(), '')
check('unconfigured text-mode run names the reason on stderr',
      'roadmap: unavailable:' in _txt_err.getvalue(), True)

# Finding 5: pin must reject a version that does not exist, BEFORE writing
# anything -- a transposed digit must not read as success.
PIN_OPEN = [tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b')]
PIN_TAG_DATES = [((0, 15, 0), '2026-09-01')]

with tempfile.TemporaryDirectory() as _d:
    _pin_state = os.path.join(_d, 'state.json')
    _rc, _out, _err = _run_main(['pin', 'v0.17.0', '--state', _pin_state,
                                 '--today', '2026-11-01'],
                                open_issues=PIN_OPEN, tag_dates=PIN_TAG_DATES)
    check('pin on a real version exits 0', _rc, 0)
    check('pin on a real version reports pinned', 'pinned v0.17.0' in _out, True)
    with open(_pin_state) as _fh:
        _saved = json.load(_fh)
    check('pin on a real version writes a baseline',
          _saved.get('baselines', {}).get('0.17.0'), ['b'])

with tempfile.TemporaryDirectory() as _d:
    _pin_state2 = os.path.join(_d, 'state.json')
    _rc, _out, _err = _run_main(['pin', 'v9.99.9', '--state', _pin_state2,
                                 '--today', '2026-11-01'],
                                open_issues=PIN_OPEN, tag_dates=PIN_TAG_DATES)
    check('pin on an absent version exits 2', _rc, 2)
    check('pin on an absent version reports no such version',
          'no such version' in _out, True)
    check('pin on an absent version writes nothing to the state file',
          os.path.exists(_pin_state2), False)

# --- I4: `plan` must distinguish "no gating epic, so I cannot tell" from --
# "gating epics exist and nothing unversioned descends from them". Both
# shapes make _candidates() return [], but only the second one is a real
# readiness verdict. A board with no epic hierarchy yet is the DEFAULT state
# for a new install, and the old code printed "ready to cut" for it anyway
# -- directly contradicting the `gates: (none)` line printed just above it.

# MUST-HIT: no gating epic at all. An unrelated unversioned P1 sits on the
# board precisely to prove this isn't a real readiness signal -- and it
# must NOT appear in the candidate list either, since it doesn't descend
# from anything.
PLAN_NO_GATES = [tagged('v0.17.0', id='t1', issue_type='task', priority=3),
                 issue(id='u1', issue_type='feature', priority=1, title='stray P1')]
with tempfile.TemporaryDirectory() as _d:
    _plan_state = os.path.join(_d, 'state.json')
    _rc, _out, _err = _run_main(['plan', 'v0.17.0', '--state', _plan_state,
                                 '--today', '2026-11-01'],
                                open_issues=PLAN_NO_GATES,
                                tag_dates=[((0, 16, 0), '2026-09-01')])
    check('plan with no gating epic exits 0', _rc, 0)
    check('plan with no gating epic does NOT claim ready to cut',
          'ready to cut' in _out, False)
    check('plan with no gating epic says there is nothing to check descent'
          ' against', 'nothing to check' in _out.lower(), True)
    check('plan with no gating epic explicitly disclaims a readiness verdict',
          'not a readiness verdict' in _out.lower(), True)

# MUST-HIT control: a gating epic exists and genuinely has nothing
# unversioned descending from it -- THIS is the real "ready to cut" case,
# and it must still say so after the fix above.
PLAN_WITH_GATE_EMPTY = [tagged('v0.17.0', id='epic1', issue_type='epic', priority=2)]
with tempfile.TemporaryDirectory() as _d:
    _plan_state2 = os.path.join(_d, 'state.json')
    _rc2, _out2, _err2 = _run_main(['plan', 'v0.17.0', '--state', _plan_state2,
                                    '--today', '2026-11-01'],
                                   open_issues=PLAN_WITH_GATE_EMPTY,
                                   tag_dates=[((0, 16, 0), '2026-09-01')])
    check('plan with a real gating epic and no descendants exits 0', _rc2, 0)
    check('plan with a real gating epic DOES claim ready to cut (control)',
          'ready to cut' in _out2, True)
    check('plan with a real gating epic omits the cannot-tell text',
          'nothing to check' in _out2.lower(), False)

# --- planning proposer (github-xs23f) -------------------------------------
# Descent is the UNION of two encodings and NEITHER ALONE IS SUFFICIENT.
# Measured on the live DB 2026-09-21: 3 open issues carry a `parent` whose id
# is not a prefix of theirs (github-xvgt -> github-gaek -> github-c8xl), and 2
# carry a dotted id with NO parent field (launch-1.21, launch-1.22) -- and both
# of THOSE hang off launch-1, the epic gating v0.18.0. Picking either encoding
# alone silently drops real work from the proposal.

def kid(pid, iid, **kw):
    """A child by the PARENT FIELD whose id deliberately shares no prefix."""
    kw.setdefault('parent', pid)
    kw.setdefault('id', iid)
    return issue(**kw)


DESC = [
    issue(id='ep-1', issue_type='epic', priority=2),
    issue(id='ep-1.1', priority=3),                     # dotted, no parent field
    issue(id='ep-1.1.1', priority=3),                   # dotted grandchild
    kid('ep-1', 'other-aaa', priority=3),               # parent field, unrelated id
    kid('other-aaa', 'other-bbb', priority=3),          # two hops via parent field
    issue(id='unrelated', priority=1),
]
BYID = {i['id']: i for i in DESC}

for iid in ('ep-1.1', 'ep-1.1.1', 'other-aaa', 'other-bbb'):
    check('descends_from hits ' + iid, rm.descends_from(BYID[iid], 'ep-1', BYID), True)
for iid in ('unrelated', 'ep-1'):
    check('descends_from skips ' + iid, rm.descends_from(BYID[iid], 'ep-1', BYID), False)

# A parent cycle must terminate rather than hang. Nothing in bd should create
# one, but "should not" is not a termination proof.
CYC = {'a': issue(id='a', parent='b'), 'b': issue(id='b', parent='a')}
check('parent cycle terminates', rm.descends_from(CYC['a'], 'ep-1', CYC), False)

PROPOSE_OPEN = [
    tagged('v0.18.0', id='ep-1', issue_type='epic', priority=2),
    tagged('v0.18.0', id='ep-2', issue_type='epic', priority=2),
    issue(id='ng-1', issue_type='epic', priority=2),          # gates NOTHING
    issue(id='ep-1.1', issue_type='feature', priority=2),
    issue(id='ep-1.2', issue_type='bug', priority=1),
    tagged('v0.16.0', id='ep-1.3', priority=1),               # already versioned
    kid('ep-2', 'zz-aaa', issue_type='task', priority=3),
    issue(id='ng-1.1', priority=0),                           # child of a non-gating epic
    issue(id='noise', priority=1, labels=['resource-watch']),  # auto-filed
]
PM = rm.build_model(PROPOSE_OPEN, [], [(0, 15, 0)])
PROP = [i['id'] for i in rm.propose(PROPOSE_OPEN, PM, (0, 18, 0))]

# Ranked by _rank(): P1 bug, then P2 feature, then P3 task.
check('proposes unversioned descendants of the gating epics, ranked',
      PROP, ['ep-1.2', 'ep-1.1', 'zz-aaa'])
check('must-miss: an already-versioned descendant', 'ep-1.3' in PROP, False)
check('must-miss: a descendant of a NON-gating epic', 'ng-1.1' in PROP, False)
check('must-miss: an auto-filed row', 'noise' in PROP, False)
check('must-miss: the gating epic itself', 'ep-1' in PROP, False)
# MUST-HIT control: the parent-field child with an unrelated id IS proposed.
# Prefix matching alone would drop it.
check('must-hit: parent-field child with an unrelated id', 'zz-aaa' in PROP, True)
# MUST-HIT control: the dotted child with no parent field IS proposed.
# Parent-field matching alone would drop it -- the launch-1.22 case.
check('must-hit: dotted child with no parent field', 'ep-1.1' in PROP, True)

# A version whose gating epics have no unversioned descendants proposes
# nothing -- and that emptiness is a RESULT (ready to cut), handled by the
# caller, not an error here.
check('no gating epics -> no candidates', rm.propose(PROPOSE_OPEN, PM, (0, 16, 0)), [])

# Cap: 7 rows plus a remainder the caller can report.
MANY = list(PROPOSE_OPEN) + [issue(id='ep-1.x%d' % n, priority=3) for n in range(8)]
MANY_M = rm.build_model(MANY, [], [(0, 15, 0)])
check('proposal caps at 7', len(rm.propose(MANY, MANY_M, (0, 18, 0))), 7)
check('proposal reports the true total',
      rm.propose_total(MANY, MANY_M, (0, 18, 0)), 11)

# --- github-aci1y: the open FAMILY is read, and deferred is split by view --
# load_issues read --status=open and --status=closed only, and bd's filter is
# EXACT, so in_progress/blocked/deferred rows reached no bucket -- a versioned
# leaf moved to in_progress left its version's open count as if done. The fake
# bd below mirrors bd 1.2.2's two argv semantics, so the test fails on BOTH
# wrong shapes: `--status` matches exactly, and a REPEATED --status silently
# overwrites the earlier one (last wins) -- the trap a naive fix walks into.
_FAMILY_ROWS = [
    tagged('v0.16.0', id='op-leaf'),
    tagged('v0.16.0', id='ip-leaf', status='in_progress'),
    tagged('v0.16.0', id='bl-leaf', status='blocked'),
    tagged('v0.16.0', id='df-leaf', status='deferred'),
    tagged('v0.16.0', id='cl-leaf', status='closed'),
    issue(id='op-bug', issue_type='bug', priority=1),
    issue(id='df-bug', issue_type='bug', priority=1, status='deferred'),
    issue(id='op-feat', issue_type='feature', priority=2),
    issue(id='df-feat', issue_type='feature', priority=2, status='deferred'),
    tagged('v0.18.0', id='g-ep', issue_type='epic', priority=2),
    issue(id='g-ep.1', priority=2, status='deferred'),
    issue(id='mid', priority=2, parent='g-ep', status='deferred'),
    issue(id='under-mid', priority=2, parent='mid'),
]
_fam_dir = tempfile.mkdtemp()
_fake_bd = os.path.join(_fam_dir, 'bd')
with open(_fake_bd, 'w', encoding='utf-8') as _fh:
    _fh.write('#!%s\nimport json, sys\nROWS = json.loads(%r)\nwant = None\n'
              'for a in sys.argv[1:]:\n'
              '    if a.startswith("--status="):\n'
              '        want = a.split("=", 1)[1].split(",")\n'
              'print(json.dumps([r for r in ROWS if want is None or r["status"] in want]))\n'
              % (sys.executable, json.dumps(_FAMILY_ROWS)))
os.chmod(_fake_bd, 0o755)
_fam_open, _fam_closed = rm.load_issues(bd_bin=_fake_bd, cfg={'workspace': _fam_dir})
_FM = rm.build_model(_fam_open, _fam_closed, [(0, 15, 0)])
_fam_v16 = [i['id'] for i in _FM['versions'][(0, 16, 0)]['leaves_open']]

# MUST-HIT: the in_progress leaf counts as NOT DONE in its version.
check('an in_progress leaf is in its version\'s open count', 'ip-leaf' in _fam_v16, True)
check('a blocked leaf is in its version\'s open count', 'bl-leaf' in _fam_v16, True)
# Deferred, view 1: a deferred VERSIONED leaf is still undone work in that
# release -- it blocks the cut until it is slipped, so it counts as open.
check('a deferred leaf is in its version\'s open count', 'df-leaf' in _fam_v16, True)
check('the open leaf is still counted (control)', 'op-leaf' in _fam_v16, True)
# Control, opposite direction: closed rows land in leaves_closed and never in
# the open read, so widening the open family did not swallow the closed one.
check('closed rows still count as closed', _FM['versions'][(0, 16, 0)]['leaves_closed'], 1)
check('no closed row is read as open',
      [i['id'] for i in _fam_open if i['status'] == 'closed'], [])

# Deferred, view 2: the hotfix queue means "cut this now", which a deferral
# explicitly says not to do. The open P1 bug beside it proves the arm fires.
_fam_hot = [i['id'] for i in _FM['hotfix']]
check('a deferred P1 bug is not in the hotfix queue', 'df-bug' in _fam_hot, False)
check('an open P1 bug is in the hotfix queue (control)', 'op-bug' in _fam_hot, True)
_fam_uns = [i['id'] for i in _FM['unscheduled']]
check('a deferred feature is not unscheduled work', 'df-feat' in _fam_uns, False)
check('an open feature is unscheduled work (control)', 'op-feat' in _fam_uns, True)

# Deferred, view 3: plan candidates exclude deferred rows -- but ancestry must
# still walk THROUGH one, or an open child of a deferred sub-epic would lose
# its path to the gating epic and silently drop out of the plan.
_fam_cand = [i['id'] for i in rm.propose(_fam_open, _FM, (0, 18, 0))]
check('a deferred descendant is not a plan candidate', 'g-ep.1' in _fam_cand, False)
check('a deferred intermediate is not a plan candidate', 'mid' in _fam_cand, False)
check('an open child under a deferred parent is still a candidate',
      'under-mid' in _fam_cand, True)

# --- condition 6: a tag was cut since the last run ------------------------
C6 = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.17.0', id='b')],
                    [], [(0, 15, 0)])
C6_ADVANCED = dict(C6)
C6_ADVANCED['cut_advanced'] = True
check('c6 fires when the cut advanced', 6 in conds(C6_ADVANCED, state()), True)
check('c6 names the version to plan',
      'v0.17.0' in ' '.join(conds(C6_ADVANCED, state())[6]['lines']), True)
check('c6 points at the plan verb',
      'roadmap plan' in ' '.join(conds(C6_ADVANCED, state())[6]['lines']), True)
# I7: the OLD assertion above ('roadmap plan' in lines) is a substring of
# 'bin/roadmap plan' too, so it never discriminated the fix. This does.
check('c6 remediation does not name bin/roadmap (I7)',
      'bin/roadmap' in ' '.join(conds(C6_ADVANCED, state())[6]['lines']), False)
# MUST-MISS control: without the flag it stays silent, so the condition is
# keyed on the cut rather than firing on every run.
check('c6 silent when the cut did not advance', 6 in conds(C6, state()), False)

# refresh_baselines must REPORT the advance, not just act on it -- it mutates
# last_cut, so by the time evaluate() runs the advance is otherwise invisible.
_rb_fresh = state()
_m1 = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
rm.refresh_baselines(_m1, _rb_fresh)
check('first run does not report an advance', _m1.get('cut_advanced'), False)

_rb_stale = state(last_cut='0.14.1')
_m2 = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
rm.refresh_baselines(_m2, _rb_stale)
check('an advanced cut reports it', _m2.get('cut_advanced'), True)

_rb_same = state(last_cut='0.15.0')
_m3 = rm.build_model([tagged('v0.16.0', id='a')], [], [(0, 15, 0)])
rm.refresh_baselines(_m3, _rb_same)
check('an unchanged cut does not report an advance', _m3.get('cut_advanced'), False)

# --- C1, render-time half: RELEASE NAMESPACE MISMATCH (condition 7) -------
# The detector is computable from labels alone: an issue with
# release_labels(i) non-empty but release_versions(i) empty carries a
# release label in some OTHER namespace than TEST_CFG['release_namespace']
# ('acme-app'). If EVERY labelled issue is like that, the config is almost
# certainly wrong -- not the roadmap genuinely empty -- regardless of how
# release_namespace came to be wrong (a bad `init` guess, a hand edit, a
# rename that drifted). This must fire LOUDLY (bypass) rather than let the
# board render as a normal, clean, empty roadmap.

# MUST-HIT: every release label on the board is in a namespace OTHER than
# the configured one.
MISMATCH_OPEN = [issue(id='m1', labels=['release:other-product-v1.0.0']),
                 issue(id='m2', labels=['release:other-product-v1.1.0'])]
MM_MODEL = rm.build_model(MISMATCH_OPEN, [], [])
check('build_model computes namespace_mismatch',
      MM_MODEL['namespace_mismatch'], ['other-product'])
check('c7 fires on a full namespace mismatch', 7 in conds(MM_MODEL, state()), True)
check('c7 bypasses the throttle', conds(MM_MODEL, state())[7]['bypass'], True)
_c7_lines = conds(MM_MODEL, state())[7]['lines']
check('c7 names the configured namespace',
      'acme-app' in '\n'.join(_c7_lines), True)
check('c7 names the namespace actually found',
      'other-product' in '\n'.join(_c7_lines), True)
check('c7 says MISMATCH loudly', 'MISMATCH' in '\n'.join(_c7_lines), True)

# MUST-HIT variant: SEVERAL other namespaces present -- both must be named,
# not just one.
MISMATCH_MULTI = [issue(id='m3', labels=['release:ns-a-v1.0.0']),
                  issue(id='m4', labels=['release:ns-b-v1.0.0'])]
check('namespace_mismatch names every namespace found, not just one',
      rm._namespace_mismatch(MISMATCH_MULTI, []), ['ns-a', 'ns-b'])

# MUST-MISS: a board where labels DO match the configured namespace must
# NOT trigger this, even if OTHER namespaces are also present (a mixed,
# multi-product workspace is normal, not a misconfiguration). Without this
# control the fix would just replace a silent-wrong-board with a false
# alarm on every legitimate multi-product install.
MIXED_OK = [tagged('v0.16.0', id='ok1'),  # 'acme-app', the configured ns
           issue(id='ok2', labels=['release:other-product-v1.0.0'])]
MIXED_MODEL = rm.build_model(MIXED_OK, [], [])
check('a board with SOME matching labels is not a mismatch (control)',
      MIXED_MODEL['namespace_mismatch'], None)
check('c7 silent when the configured namespace has real matches',
      7 in conds(MIXED_MODEL, state()), False)

# MUST-MISS: a genuinely fresh board with NO release labels at all is not a
# mismatch either -- that is condition 1's job (HORIZON EMPTY), not this
# one's. Reusing BOARD_MODEL-shape fixtures already used elsewhere: EMPTY
# (defined earlier) has zero release labels anywhere.
check('a label-free board is not a mismatch (control)',
      EMPTY['namespace_mismatch'], None)
check('c7 silent on a genuinely empty board', 7 in conds(EMPTY, state()), False)

# A REAL install's namespace must never be mistaken for a mismatch just
# because it differs from the suite's synthetic 'acme-app' -- prove the
# detector is keyed on cfg['release_namespace'], not a hardcoded literal, by
# swapping the configured namespace and re-checking a matching board.
_OTHER_INSTALL_CFG = dict(TEST_CFG, release_namespace='some-other-product')
_other_install_open = [issue(id='k1', labels=['release:some-other-product-v0.16.0'])]
check('a matching board under a DIFFERENT configured namespace is clean',
      rm._namespace_mismatch(_other_install_open, [], cfg=_OTHER_INSTALL_CFG), None)

# --- I5b (github-kkq4a): condition 8 -- no version tags at all -------------
# Runtime half of the same finding init's warning covers (I5a): the board
# above renders every version as PLANNED, which is honest but needs
# explaining, so condition 8 names the state. NT/WT are the no-tags/with-tag
# model fixtures defined earlier alongside build_model's own I5 coverage.
NT_CONDS = rm.evaluate(NT, state(), '2026-09-21')
_c8 = [c for c in NT_CONDS if c['id'] == 8]
check('condition 8 fires with no tags', len(_c8), 1)
# Both reads below are GUARDED by `bool(_c8) and ...` (github-kkq4a): _c8[0]
# is indexed right after a check() that RECORDS a failure without aborting,
# so an empty _c8 would raise IndexError here and truncate the rest of the
# run -- turning one failing assertion into a suite that never reaches its
# remaining arms. The guard makes the failure land in FAILURES instead.
check('condition 8 is bypass', bool(_c8) and _c8[0]['bypass'], True)
check('condition 8 names the tag_repo',
      bool(_c8) and any(TEST_CFG['tag_repo'] in l for l in _c8[0]['lines']), True)
# MUST-MISS: with a tag cut, condition 8 is silent.
check('condition 8 is silent with a tag (control)',
      [c for c in rm.evaluate(WT, state(), '2026-09-21') if c['id'] == 8], [])

# Condition 1 (HORIZON EMPTY) must NOT double-fire on a tagless board that
# carries labels -- planned is non-empty, so there IS a horizon. On a board
# with neither tags nor labels both fire, which is correct: an empty horizon
# and an untagged repo are two different things a cold install needs told.
check('condition 1 stays quiet on a tagless board WITH labels',
      [c for c in NT_CONDS if c['id'] == 1], [])
_cold = rm.evaluate(rm.build_model([], [], []), state(), '2026-09-21')
check('a wholly cold board hears both 1 and 8',
      sorted(c['id'] for c in _cold if c['id'] in (1, 8)), [1, 8])

# github-kkq4a, I3: conditions 6 and 8 must not contradict each other.
#
# The assertion here used to be `state(last_cut=None)` -> `cut_advanced is
# False`, which could not fail: with last_cut None, refresh_baselines takes
# its first-run branch and sets cut_advanced False unconditionally, before
# no_tags is consulted by anything. It duplicated 'first run does not report
# an advance' above and said nothing about tags -- and the property it named
# was false. With a PRIOR last_cut and no tags, cut_key is None, the values
# differ, and cut_advanced really is True.
#
# A fresh model, not NT: refresh_baselines mutates the model it is handed, and
# NT is the shared fixture the condition-8 arms above read.
_nt_adv = rm.build_model(NT_OPEN, [], [])
_nt_adv_state = state(last_cut='0.15.0')
rm.refresh_baselines(_nt_adv, _nt_adv_state)
check('no tags with a prior last_cut: the change IS flagged',
      _nt_adv['cut_advanced'], True)
_nt_adv_conds = conds(_nt_adv, _nt_adv_state)
# MUST-MISS: the flag is set, and condition 6 still stays quiet -- a cut that
# went AWAY is not a cut that advanced. Deleting the `not model['no_tags']`
# guard in evaluate() fails this line.
check('c6 is suppressed on a tagless board', 6 in _nt_adv_conds, False)
# MUST-HIT on the same board: condition 8 is the one that describes it, so
# the suppression above is condition 6 being wrong here, not the board being
# silent.
check('c8 still names the tagless board (control)', 8 in _nt_adv_conds, True)

# MUST-HIT control, same fixture shape but WITH a tag cut: the suppression is
# keyed on no_tags, not on refresh_baselines' flag, so a real advance still
# reports. Without this pair, deleting condition 6 outright would pass.
_wt_adv = rm.build_model(NT_OPEN, [], [(0, 15, 0)])
_wt_adv_state = state(last_cut='0.14.0')
rm.refresh_baselines(_wt_adv, _wt_adv_state)
check('with tags, a prior last_cut still flags the change (control)',
      _wt_adv['cut_advanced'], True)
check('c6 still fires when a real tag advanced (control)',
      6 in conds(_wt_adv, _wt_adv_state), True)

# --- config layer ---------------------------------------------------------
def write_cfg(text, name='roadmap.toml'):
    """-> (dir, path). Each call gets its own tempdir so walk-up tests do
    not see each other's files."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, 'w') as fh:
        fh.write(text)
    return d, p


GOOD = '''
workspace = "."
tag_repo = "."
release_namespace = "acme-app"
convention_start = "2026-10-15"
auto_label_prefixes = ["noise:"]
'''

_d, _p = write_cfg(GOOD)
_cfg = rm.load_config(_p)
check('namespace loads', _cfg['release_namespace'], 'acme-app')
check('convention_start loads', _cfg['convention_start'], '2026-10-15')
check('prefixes load as a tuple', _cfg['auto_label_prefixes'], ('noise:',))
# Relative paths resolve against the CONFIG FILE, not the cwd -- otherwise
# the hook (which runs from an arbitrary cwd) and the CLI disagree.
check('workspace resolves against the config file',
      _cfg['workspace'], os.path.realpath(_d))

# Discovery: walk UP from a nested dir.
#
# Compare against the REALPATH form. find_config resolves symlinks, and on
# macOS tempfile.mkdtemp() hands back /var/... while /var is a symlink to
# /private/var -- so a naive `== _p` fails here for a reason that has nothing
# to do with the code under test.
_nested = os.path.join(_d, 'a', 'b')
os.makedirs(_nested, exist_ok=True)
_p_real = os.path.join(os.path.realpath(_d), 'roadmap.toml')
check('walk-up finds the config', rm.find_config(start=_nested), _p_real)

# Discovery: $ROADMAP_CONFIG wins over the walk-up. No realpath here --
# the override is returned verbatim, by design, so a caller can point at a
# config through a symlink deliberately.
_d2, _p2 = write_cfg(GOOD)
check('env override wins',
      rm.find_config(start=_nested, env={'ROADMAP_CONFIG': _p2}), _p2)

# MUST-MISS: no config anywhere is RoadmapUnavailable, not a crash and not
# an empty board. An unconfigured install has to render as "unavailable".
_empty = tempfile.mkdtemp()
check('no config found', rm.find_config(start=_empty), None)
try:
    rm.load_config(start=_empty, env={})
    check('missing config raises', 'no raise', 'RoadmapUnavailable')
except rm.RoadmapUnavailable as exc:
    check('missing config names the remedy', 'roadmap init' in str(exc), True)
    # I8: this is the ONE unavailable reason that unambiguously means setup
    # was never run at all, and the hook keys on this flag to speak once.
    check('missing config is marked unconfigured (I8)',
          exc.unconfigured, True)

# A typo must be REJECTED BY NAME. Silently ignoring it yields an empty
# board -- the exact silent-wrong-answer this design rejected.
_d3, _p3 = write_cfg(GOOD + '\nrelease_namespc = "oops"\n')
try:
    rm.load_config(_p3)
    check('unknown key raises', 'no raise', 'RoadmapUnavailable')
except rm.RoadmapUnavailable as exc:
    check('unknown key is named', 'release_namespc' in str(exc), True)
    # MUST-MISS control (I8): a config file that EXISTS but is broken is a
    # different failure than no file at all -- it must NOT be marked
    # unconfigured, or the hook would nudge "run roadmap init" at a user
    # whose real problem is a typo in an existing file.
    check('a broken (but present) config is NOT marked unconfigured (I8)',
          exc.unconfigured, False)

# A missing REQUIRED key is likewise named.
_d4, _p4 = write_cfg('workspace = "."\ntag_repo = "."\n')
try:
    rm.load_config(_p4)
    check('missing required key raises', 'no raise', 'RoadmapUnavailable')
except rm.RoadmapUnavailable as exc:
    check('missing key is named', 'release_namespace' in str(exc), True)

# An absent convention_start seeds today -- same rule as load_state.
_d5, _p5 = write_cfg('workspace = "."\ntag_repo = "."\n'
                     'release_namespace = "acme-app"\n')
check('absent convention_start seeds today',
      rm.load_config(_p5, today='2027-03-01')['convention_start'], '2027-03-01')

# A non-date convention_start is rejected rather than silently disabling
# warm-up (warmup_active swallows a parse error and returns True forever).
_d6, _p6 = write_cfg(GOOD.replace('"2026-10-15"', '"last tuesday"'))
try:
    rm.load_config(_p6)
    check('bad date raises', 'no raise', 'RoadmapUnavailable')
except rm.RoadmapUnavailable as exc:
    check('bad date is named', 'convention_start' in str(exc), True)

# --- config layer: TYPES, not just names -----------------------------------
# Names alone are not enough: `workspace = 42` or `auto_label_prefixes = 5`
# must not escape as a raw TypeError. main() catches only RoadmapUnavailable
# (bin/roadmap:~694), so any other exception type here would crash the
# SessionStart hook instead of failing open silently -- the exact thing this
# layer exists to prevent. check_type_rejected asserts BOTH that the raised
# exception is specifically RoadmapUnavailable (not merely "something") and
# that its message names the offending key.
def check_type_rejected(label, toml_text, key):
    _d, _p = write_cfg(toml_text)
    try:
        rm.load_config(_p)
        check(label + ' raises', 'no raise', 'RoadmapUnavailable')
        return
    except Exception as exc:
        # A bare `except RoadmapUnavailable` here would not prove a
        # TypeError is gone -- it would just not catch it, and the test
        # would blow up with the same traceback Step 2 showed for a missing
        # attribute. Catching Exception and checking the type is what
        # actually proves no TypeError (or anything else) escapes.
        check(label + ' is RoadmapUnavailable', isinstance(exc, rm.RoadmapUnavailable), True)
        check(label + ' names the key', key in str(exc), True)


check_type_rejected('workspace wrong type',
                     GOOD.replace('workspace = "."', 'workspace = 42'),
                     'workspace')
check_type_rejected('tag_repo wrong type',
                     GOOD.replace('tag_repo = "."', 'tag_repo = ["a", "b"]'),
                     'tag_repo')
check_type_rejected('release_namespace wrong type',
                     GOOD.replace('release_namespace = "acme-app"', 'release_namespace = 42'),
                     'release_namespace')
check_type_rejected('auto_label_prefixes non-iterable',
                     GOOD.replace('auto_label_prefixes = ["noise:"]', 'auto_label_prefixes = 5'),
                     'auto_label_prefixes')
check_type_rejected('auto_label_prefixes list of non-strings',
                     GOOD.replace('auto_label_prefixes = ["noise:"]', 'auto_label_prefixes = [1, 2, 3]'),
                     'auto_label_prefixes')

# I1, upgraded to critical: a bare string must be rejected BY NAME, not
# coerced. str.startswith() accepts a tuple, so tuple("noise:") silently
# becomes ('n','o','i','s','e',':') -- a valid one-character-prefix filter
# that drops most real labels ("security", "open-graph", "infra", "epic",
# "needs-triage" all start with one of those six characters) with no error
# at all. That is the precise silent-wrong-answer this whole config layer
# exists to prevent, arriving through lenient parsing instead of a typo.
check_type_rejected('auto_label_prefixes bare string',
                     GOOD.replace('auto_label_prefixes = ["noise:"]', 'auto_label_prefixes = "noise:"'),
                     'auto_label_prefixes')

# MUST-MISS: a validator that rejects everything would pass every check
# above. Confirm the valid fixture still loads, and that a real list of
# prefixes still yields the tuple it always did.
_dT7, _pT7 = write_cfg(GOOD)
check('valid config still loads after type validation',
      rm.load_config(_pT7)['release_namespace'], 'acme-app')
_dT8, _pT8 = write_cfg(GOOD.replace('auto_label_prefixes = ["noise:"]',
                                     'auto_label_prefixes = ["a:", "b:"]'))
check('valid list of prefixes still loads as a tuple',
      rm.load_config(_pT8)['auto_label_prefixes'], ('a:', 'b:'))

# --- roadmap init -----------------------------------------------------------
# A single-repo layout is the common case and must be UNAMBIGUOUS: the root
# is a git repo with v* tags, so all three knobs collapse to one value.
def fake_git(tags):
    """A stand-in for subprocess.run over `git for-each-ref`."""
    def run(argv, **kw):
        class R:
            returncode = 0
            stdout = '\n'.join('2026-01-01 %s' % t for t in tags)
        return R()
    return run


def fake_bd(namespaces=(), closed_namespaces=(), raise_unavailable=None):
    """A stand-in for load_issues(cfg=...) -- probe_layout's C1 fix reads
    release labels off the board via this exact call shape
    (load_issues_fn(cfg={'workspace': root})) rather than the directory
    name. Yields one labelled issue per namespace given, so the suite can
    drive "exactly one namespace", "several", and "none" without a real bd
    workspace anywhere (matches the CI comment: no bd, synthetic rows only).
    """
    def _load(cfg=None, **kw):
        if raise_unavailable is not None:
            raise rm.RoadmapUnavailable(raise_unavailable)

        def mk(ns, n):
            return issue(id='probe-%s-%d' % (ns, n),
                        labels=['release:%s-v1.0.0' % ns])
        opened = [mk(ns, n) for n, ns in enumerate(namespaces)]
        closed = [mk(ns, n) for n, ns in enumerate(closed_namespaces)]
        return opened, closed
    return _load


_root = tempfile.mkdtemp()
# A REAL repo, not just an empty .git dir: cmd_init's own probe_layout call
# below is never given the fake_git injection (cmd_init's signature takes no
# `run` -- only probe_layout does), so it shells out to the real git binary.
# An empty .git directory is not a repository at all -- `git for-each-ref`
# exits 128 with empty stdout, which is indistinguishable from "found no
# tags" and made this fixture silently exercise the ambiguous path instead
# of the happy path it is named for. Verified directly: returncode 128,
# stdout ''.
_git_env = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.com',
                GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.com')
subprocess.run(['git', 'init', '-q', _root], check=True, env=_git_env)
subprocess.run(['git', '-C', _root, 'commit', '-q', '--allow-empty', '-m', 'init'],
               check=True, env=_git_env)
subprocess.run(['git', '-C', _root, 'tag', 'v1.2.0'], check=True, env=_git_env)

# C1 (init-time): namespace comes from the BOARD, never the directory. This
# fixture's board carries release labels in exactly one namespace,
# 'probe-ns-real', which is deliberately NOT os.path.basename(_root) -- if
# the fix regressed to reading the directory name, this assertion would
# catch it even though tempfile.mkdtemp() names are already unlikely to
# collide with a chosen literal.
_probe = rm.probe_layout(_root, run=fake_git(['v1.2.0']),
                         load_issues_fn=fake_bd(['probe-ns-real']))
check('single-repo workspace is the root', _probe['workspace'], '.')
check('single-repo tag_repo is the root', _probe['tag_repo'], '.')
check('namespace is derived from the BOARD, not the directory',
      _probe['release_namespace'], 'probe-ns-real')
check('single-repo layout is unambiguous', _probe['ambiguous'], [])
# MUST-MISS: the OLD behaviour (directory basename) must be gone entirely --
# proves the fix changed the SOURCE, not just the fixture's happy coincidence.
check('namespace is NOT the directory basename (control)',
      _probe['release_namespace'] == os.path.basename(os.path.realpath(_root)),
      False)

# MUST-HIT: several namespaces on the board -- roadmap cannot guess between
# them, so this must refuse and NAME both.
_probe_multi_ns = rm.probe_layout(
    _root, run=fake_git(['v1.2.0']),
    load_issues_fn=fake_bd(['probe-ns-a', 'probe-ns-b']))
_multi_ns_reasons = ' '.join(_probe_multi_ns['ambiguous'])
check('multiple board namespaces are ambiguous',
      _probe_multi_ns['ambiguous'] != [], True)
check('multiple board namespaces names BOTH in the refusal',
      'probe-ns-a' in _multi_ns_reasons and 'probe-ns-b' in _multi_ns_reasons,
      True)
check('multiple board namespaces: release_namespace stays unset',
      _probe_multi_ns['release_namespace'], None)

# MUST-HIT: no release labels on the board at all -- roadmap has no evidence
# and must refuse rather than fall back to the directory name.
_probe_no_ns = rm.probe_layout(_root, run=fake_git(['v1.2.0']),
                               load_issues_fn=fake_bd([]))
check('no board namespaces is ambiguous',
      _probe_no_ns['ambiguous'] != [], True)
check('no board namespaces: release_namespace stays unset',
      _probe_no_ns['release_namespace'], None)
check('no board namespaces names the reason, not just "no tags"',
      any('release:<namespace>' in r for r in _probe_no_ns['ambiguous']), True)

# MUST-HIT: bd itself unavailable during the probe (not installed, no
# workspace, whatever) is ALSO ambiguous, naming the underlying reason --
# not silently treated as "no namespaces found".
_probe_bd_down = rm.probe_layout(
    _root, run=fake_git(['v1.2.0']),
    load_issues_fn=fake_bd(raise_unavailable='bd exited 1'))
check('bd unavailable during probe is ambiguous',
      _probe_bd_down['ambiguous'] != [], True)
check('bd unavailable during probe names the underlying reason',
      any('bd exited 1' in r for r in _probe_bd_down['ambiguous']), True)

# MUST-MISS control: a namespace also present on the CLOSED side alone
# (no open issue carries it) is still found -- probe_release_namespace reads
# both, the same as load_issues does everywhere else in this tool.
_probe_closed_only = rm.probe_layout(
    _root, run=fake_git(['v1.2.0']),
    load_issues_fn=fake_bd([], closed_namespaces=['probe-ns-closed']))
check('a namespace seen only on closed issues still resolves',
      _probe_closed_only['release_namespace'], 'probe-ns-closed')
check('closed-only resolution is unambiguous',
      _probe_closed_only['ambiguous'], [])

# --- probe_layout: git RAN but FAILED must not collapse into "no tags" ----
# A repo that exists but is unreadable (corrupt .git, permissions, whatever)
# fails DIFFERENTLY from a repo that legitimately has no v* tags yet -- the
# first is fixed by repairing the repo, the second by adding a tag, and
# telling a user with a broken repo to add a tag sends them chasing the
# wrong fix. Both directions, per the fake_git stub idiom above.
def rc_stub(returncode, stdout='', stderr=''):
    def run(argv, **kw):
        class R:
            pass
        R.returncode = returncode
        R.stdout = stdout
        R.stderr = stderr
        return R()
    return run


# MUST-HIT: nonzero returncode with empty stdout -- exactly what a corrupt
# or unreadable .git produces against the real git binary (confirmed while
# fixing the _root fixture above: exit 128, stdout ''). The reason must name
# the failure, not say "no semver v* tags".
_probe_failed = rm.probe_layout(
    _root, run=rc_stub(128, stdout='', stderr='fatal: bad object HEAD\n'))
check('git-failed layout is ambiguous', _probe_failed['ambiguous'] != [], True)
check('git failure is NOT reported as merely no-tags',
      any('no semver v* tags' in r for r in _probe_failed['ambiguous']), False)
check('git failure names the exit status',
      any('128' in r for r in _probe_failed['ambiguous']), True)
check('git failure surfaces stderr',
      any('bad object HEAD' in r for r in _probe_failed['ambiguous']), True)

# MUST-MISS: a clean run (returncode 0) with empty stdout is a REAL "no
# tags yet" and must keep saying so -- a fix that reports failure for every
# empty result would pass the must-hit above too, so this has to hold
# separately.
# No tags is NOT an early return (unlike the failures above) -- it falls
# through to namespace probing too, so a fake bd is injected here purely to
# keep this fixture off the real `bd` binary (no workspace exists at
# `_root`); the namespace side is irrelevant to what this assertion checks.
#
# UPDATED for I5 (github-kkq4a): no-tags moved from `ambiguous` to
# `warnings` -- it is no longer a refusal reason, so this now reads
# `warnings` instead of `ambiguous`. This assertion used to pin the OLD
# refuse-on-no-tags contract; the behaviour it checks (the reason is still
# reported somewhere) is unchanged, only which list carries it.
_probe_clean_empty = rm.probe_layout(_root, run=rc_stub(0, stdout=''),
                                     load_issues_fn=fake_bd(['probe-ns-real']))
check('a clean git run with genuinely no tags still says so',
      any('no semver v* tags' in w for w in _probe_clean_empty['warnings']), True)
check('a clean git run with genuinely no tags is not ambiguous',
      _probe_clean_empty['ambiguous'], [])

# A hanging git (subprocess.TimeoutExpired) must land in the same
# could-not-read branch as a missing binary, not the no-tags branch either.
def _timeout_run(argv, **kw):
    raise subprocess.TimeoutExpired(cmd=argv, timeout=20)


_probe_timeout = rm.probe_layout(_root, run=_timeout_run)
check('a hanging git is reported as unreadable, not no-tags',
      any('could not read git tags' in r for r in _probe_timeout['ambiguous']), True)
check('the timeout report is not the no-tags message',
      any('no semver v* tags' in r for r in _probe_timeout['ambiguous']), False)

# MUST-HIT: a root that is NOT a git repo and has no tagged subdir cannot be
# resolved, and init must REFUSE. Guessing here is approach B, which this
# design rejected because a wrong guess renders a clean, empty board.
_bare = tempfile.mkdtemp()
_probe_bare = rm.probe_layout(_bare, run=fake_git([]))
check('a bare directory is ambiguous', _probe_bare['ambiguous'] != [], True)

_buf = io.StringIO()
check('init refuses an ambiguous layout',
      rm.cmd_init(_bare, '2027-03-01', _buf), 2)
check('the refusal explains why', 'ambiguous' in _buf.getvalue().lower(), True)
check('init wrote nothing on refusal',
      os.path.exists(os.path.join(_bare, 'roadmap.toml')), False)

# The happy path writes a file that load_config accepts -- a round trip,
# not just "a file appeared". `run` is left real (git shells out for real,
# per the fixture comment above); `load_issues_fn` is faked so this stays
# off a real `bd` binary while still exercising cmd_init's own threading of
# the injection through to probe_layout (C1).
_buf2 = io.StringIO()
check('init succeeds on a clear layout',
      rm.cmd_init(_root, '2027-03-01', _buf2,
                 load_issues_fn=fake_bd(['probe-ns-real'])), 0)
_written = rm.load_config(os.path.join(_root, 'roadmap.toml'))
check('init seeds convention_start to today',
      _written['convention_start'], '2027-03-01')
check('the written config round-trips the BOARD-derived namespace',
      _written['release_namespace'], 'probe-ns-real')
# MUST-MISS: the directory name must not have leaked in anywhere -- the
# exact defect (C1) this whole fix removes.
check('the written config is NOT the directory basename (control)',
      _written['release_namespace'] == os.path.basename(os.path.realpath(_root)),
      False)
check('init PRINTS what it found',
      'probe-ns-real' in _buf2.getvalue(), True)

# MUST-MISS: a second init must not silently clobber a config someone
# hand-edited.
_buf3 = io.StringIO()
check('init refuses to overwrite', rm.cmd_init(_root, '2027-03-01', _buf3), 2)
check('the overwrite refusal names --force', '--force' in _buf3.getvalue(), True)

# --- cmd_init: ambiguous namespace refusal names a last-resort suggestion -
# The directory basename may appear ONLY as a last-resort suggestion in the
# refusal text, never silently written (C1). A fresh, never-inited dir with
# tags but NO board evidence exercises this.
_root2 = tempfile.mkdtemp()
subprocess.run(['git', 'init', '-q', _root2], check=True, env=_git_env)
subprocess.run(['git', '-C', _root2, 'commit', '-q', '--allow-empty', '-m', 'init'],
               check=True, env=_git_env)
subprocess.run(['git', '-C', _root2, 'tag', 'v1.0.0'], check=True, env=_git_env)
_buf4 = io.StringIO()
check('init refuses when the board has no release labels',
      rm.cmd_init(_root2, '2027-03-01', _buf4, run=fake_git(['v1.0.0']),
                 load_issues_fn=fake_bd([])), 2)
check('the refusal suggests the directory name as a LAST RESORT, not a fact',
      os.path.basename(os.path.realpath(_root2)) in _buf4.getvalue(), True)
check('the last-resort suggestion is hedged, not a silent write',
      'last resort' in _buf4.getvalue().lower(), True)
check('nothing was written on this refusal either',
      os.path.exists(os.path.join(_root2, 'roadmap.toml')), False)

# --- I5 (github-kkq4a): init accepts what the runtime accepts --------------
# init used to REFUSE a repo with no semver v* tags and tell the user to
# write roadmap.toml by hand -- which routes them past the namespace probe,
# the one guard that genuinely cannot be replaced by a guess. A new repo
# with labels and no tag yet is a legitimate state. It is now a WARNING that
# still writes. fake_git([]) above already produces exactly the fake-run
# shape this needs (returncode 0, empty stdout -- git ran, found no tags),
# so no new fake-run helper is added here.
_root3 = tempfile.mkdtemp()
os.makedirs(os.path.join(_root3, '.git'))
_probe_no_tags = rm.probe_layout(
    _root3, run=fake_git([]),
    load_issues_fn=lambda cfg=None: ([tagged('v0.16.0', id='a')], []))
check('no-tags is a warning, not ambiguous', _probe_no_tags['ambiguous'], [])
check('no-tags warning is recorded',
      any('no semver v* tags' in w for w in _probe_no_tags['warnings']), True)
check('the namespace still came off the board',
      _probe_no_tags['release_namespace'], 'acme-app')

_buf5 = io.StringIO()
_rc5 = rm.cmd_init(_root3, '2026-09-21', _buf5,
                   run=fake_git([]),
                   load_issues_fn=lambda cfg=None: ([tagged('v0.16.0', id='a')], []))
check('init WRITES despite no tags', _rc5, 0)
check('init created roadmap.toml',
      os.path.exists(os.path.join(_root3, 'roadmap.toml')), True)
check('init printed the no-tags warning',
      'no semver v* tags' in _buf5.getvalue(), True)

# MUST-MISS control: an AMBIGUOUS namespace is still a hard refusal that
# writes nothing. Without this, dropping every refusal would pass the arms
# above. The board here carries TWO namespaces, which cannot be resolved.
_root4 = tempfile.mkdtemp()
os.makedirs(os.path.join(_root4, '.git'))
_buf6 = io.StringIO()
_rc6 = rm.cmd_init(
    _root4, '2026-09-21', _buf6, run=fake_git([]),
    load_issues_fn=lambda cfg=None: (
        [issue(id='a', labels=['release:ns-a-v1.0.0']),
         issue(id='b', labels=['release:ns-b-v1.0.0'])], []))
check('ambiguous namespace is still refused (control)', _rc6, 2)
check('a refused init writes nothing (control)',
      os.path.exists(os.path.join(_root4, 'roadmap.toml')), False)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- manifest agreement ---------------------------------------------------
# The two manifests carry the version independently, and every release so far
# has been a hand-checked two-place edit (github-kkq4a). Both are indexed, not
# .get()-ed: a renamed or missing key raises here instead of letting two Nones
# compare equal and pass vacuously, and the shape assertion below means a
# version that is present but not a version cannot satisfy it either.
_PLUGIN_VERSION = json.load(
    open(os.path.join(_ROOT, '.claude-plugin', 'plugin.json')))['version']
_MARKET_VERSION = json.load(
    open(os.path.join(_ROOT, '.claude-plugin', 'marketplace.json')))['plugins'][0]['version']
check('the plugin version is three dotted integers',
      [p.isdigit() for p in _PLUGIN_VERSION.split('.')], [True, True, True])
check('plugin.json and marketplace.json agree on the version',
      _PLUGIN_VERSION, _MARKET_VERSION)

# --- payload-key agreement across the two suites --------------------------
# render_json (tested here) and the hook (tested in hooks/test_roadmap_cadence
# .py) are a producer and a consumer that never meet: each suite hand-writes
# the other side's payload, so renaming a key in one file would leave BOTH
# suites green while the flag silently stopped arriving -- the same shape as
# the C1 defect this branch fixes, where a message had a sender and no
# receiver. Pin the names to each other (github-kkq4a).
_HOOK_SRC = open(os.path.join(_ROOT, 'hooks', 'roadmap-cadence.py')).read()
_RENDERED_KEYS = rm.render_json({'versions': {}, 'unscheduled': [], 'hotfix': []}, [])
for _key in ('state_path', 'legacy_state_available', 'conditions'):
    check('the hook reads %r by the name render_json emits it' % _key,
          _key in _HOOK_SRC and ('"%s"' % _key) in _RENDERED_KEYS, True)
# `unconfigured` is emitted by main()'s unavailable branch, NOT by
# render_json -- the I8 arms further up assert the producing half. Only the
# consumer's half is pinned here, which is what this check can see.
check('the hook reads `unconfigured` by that name',
      'unconfigured' in _HOOK_SRC, True)
# MUST-MISS control: a plausible-but-wrong name is in neither, so the loop
# above is a real search over real content rather than a pair of substrings
# any file would satisfy.
check('a key neither side uses is found in neither (control)',
      'legacy_state_migrated' in _HOOK_SRC, False)

# --- github-zv9qt: roadmap --version ---------------------------------------
# The version is read from the plugin's own .claude-plugin/plugin.json at run
# time -- no third copy to bump. An unreadable manifest is a reason, never a
# crash: --version must fail open like everything else here.
def _manifest_root(body):
    root = tempfile.mkdtemp()
    if body is not None:
        os.makedirs(os.path.join(root, '.claude-plugin'))
        with open(os.path.join(root, '.claude-plugin', 'plugin.json'), 'w',
                  encoding='utf-8') as _fh:
            _fh.write(body)
    return root


check('--version reads plugin.json',
      rm.plugin_version(_manifest_root('{"name": "roadmap", "version": "9.8.7"}')),
      ('9.8.7', None))
for _label, _body in (('a missing manifest', None),
                      ('an unparseable manifest', '{not json'),
                      ('a manifest with no version', '{"name": "roadmap"}')):
    _v, _why = rm.plugin_version(_manifest_root(_body))
    check('--version: %s gives no version' % _label, _v, None)
    check('--version: %s gives a reason' % _label, bool(_why), True)

# MUST-HIT against the REAL tree: the default root is this repo, and it must
# report exactly what the shipped manifest says.
_REPO_ROOT = os.path.dirname(os.path.dirname(MODULE_PATH))
with open(os.path.join(_REPO_ROOT, '.claude-plugin', 'plugin.json')) as _fh:
    _SHIPPED_VERSION = json.load(_fh)['version']
check('--version default root reports the shipped manifest',
      rm.plugin_version(), (_SHIPPED_VERSION, None))


def _run_main(argv):
    """-> (rc, stdout, raised). load_config is booby-trapped, so a --version
    that touched configuration surfaces as `raised`, not as a pass."""
    _orig_lc = rm.load_config

    def _trap(*a, **kw):
        raise AssertionError('load_config reached')
    rm.load_config = _trap
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = rm.main(argv)
        return rc, buf.getvalue(), None
    except AssertionError as exc:
        return None, buf.getvalue(), str(exc)
    finally:
        rm.load_config = _orig_lc


_rc, _out, _raised = _run_main(['--version'])
check('--version needs no roadmap.toml', _raised, None)
check('--version exits 0', _rc, 0)
check('--version prints the version', _out.startswith('roadmap %s' % _SHIPPED_VERSION), True)
check('--version names the binary that answered', MODULE_PATH in _out, True)
# MUST-HIT control: WITHOUT --version the same harness does reach load_config,
# so the None above means --version skipped it, not that the trap is dead.
check('the load_config trap fires on a normal run (control)',
      _run_main([])[2], 'load_config reached')
# An unreadable manifest still answers, exit 0, with the reason.
_orig_pv = rm.plugin_version
rm.plugin_version = lambda root=None: (None, 'no manifest at /x')
try:
    _rc, _out, _raised = _run_main(['--version'])
finally:
    rm.plugin_version = _orig_pv
check('--version with no manifest still exits 0', _rc, 0)
check('--version with no manifest says unknown and why',
      'version unknown' in _out and 'no manifest at /x' in _out, True)

# --- decoupling scan ------------------------------------------------------
# A property test, not an example test: no shipped file may name the
# workspace this tool came from. The fixture rename above makes a surviving
# literal fail a behavioural check; this catches one hiding in a comment,
# a docstring or a default that no behavioural test happens to reach.

# Built by concatenation, not spelled out whole: this very file is itself a
# shipped file the walk below visits, so a needle written out in full would
# make the scan trip over its own detector list -- a false hit indistinguish-
# able from a real one. The runtime string value is identical either way.
_COUPLED = ('ku' + 'ju', 'mac' + 'ole', 'shao' + 'lynx')


def scan_tree(root, needles=_COUPLED):
    """Scan `root`'s shipped files (see _shipped_files) and return a sorted
    list of 'relpath: needle' entries -- the exact list -> filter -> read -> match
    -> append pipeline the real gate runs, factored out so the must-hit and
    must-miss fixtures below exercise the SAME code the real check uses,
    not a decoupled reimplementation of its pieces (fix round 1: the old
    must-hit checks tested the walk and the substring predicate separately,
    and neither exercised `_hits.append` or the encoding path, so a broken
    append or a swallowed read error would have passed both).

    Filter: extension-based (.py/.md/.json/.toml/.yml) plus the exact
    filename 'roadmap'. Known gap, not a live bug (both are clean today):
    an extensionless future file -- a Makefile, a shell script with no
    suffix -- is OUTSIDE this filter, same as LICENSE and .gitignore are
    now.
    """
    hits = []
    for path in _shipped_files(root):
        fn = os.path.basename(path)
        if not (fn.endswith(('.py', '.md', '.json', '.toml', '.yml'))
                or fn == 'roadmap'):
            continue
        # A read failure must never read as "no hits" -- that is the
        # exact false negative the old `except Exception: continue`
        # produced for a file containing a coupled string plus one
        # invalid UTF-8 byte (fix round 1). Read bytes and decode with
        # errors='replace' so the scan still inspects the file's
        # content instead of skipping it; a REPLACEMENT byte cannot
        # hide a needle, because every needle is pure ASCII and
        # Python never folds a byte < 0x80 into a replacement's maximal
        # subpart -- verified by the fixtures below, which plant a needle
        # flush against an invalid byte and against a truncated \xf0\x90\x80
        # lead. This property is NOT free: it follows from the needles
        # being ASCII. Adding a non-ASCII needle to _COUPLED voids it, and
        # the reasoning here must be redone rather than assumed to carry.
        # A file that cannot even be opened (permissions, vanished mid-walk)
        # is left to raise -- a crashed suite is a loud failure, which
        # is the point, where a silent skip would not be.
        with open(path, 'rb') as fh:
            text = fh.read().decode('utf-8', errors='replace').lower()
        for needle in needles:
            if needle in text:
                hits.append('%s: %s' % (os.path.relpath(path, root), needle))
    return sorted(hits)


def _shipped_files(root):
    """Every file under `root` that could ship, as absolute paths.

    Inside a git work tree that is what git would publish: tracked files
    plus untracked ones NOT ignored (they ship on the next `git add -A`).
    Walking the disk instead made an ignored local file -- a developer's
    .claude/settings.local.json, a nested .claude/worktrees/ checkout --
    fail the gate, a verdict about local debris rather than the tree
    (github-9rwrl). Outside a work tree (the tempdir fixtures, an unpacked
    tarball) nothing is ignored, so every file on disk is what ships.
    """
    probe = subprocess.run(['git', '-C', root, 'rev-parse', '--is-inside-work-tree'],
                           capture_output=True, text=True)
    if probe.returncode == 0 and probe.stdout.strip() == 'true':
        # check=True: a git tree whose listing FAILS must crash the suite,
        # never fall through to an empty list that reads as "clean".
        out = subprocess.run(['git', '-C', root, 'ls-files', '-z', '--cached',
                              '--others', '--exclude-standard'],
                             check=True, capture_output=True).stdout
        paths = sorted({os.path.join(root, p) for p in
                        out.decode('utf-8', errors='surrogateescape').split('\0') if p})
        # A tracked file deleted from the work tree (or a submodule entry) is
        # listed by --cached but has no content to scan and will not ship.
        return [p for p in paths if os.path.isfile(p)]
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        # .git is the real object store -- enormous, and its contents are
        # handled by B7's orphan-branch squash, not this scan.
        #
        # .github was ALSO excluded here once (fix round 0, per the
        # original brief) -- that was WRONG and has been reverted. .github
        # is exactly where a CI workflow lands, task B7 adds
        # .github/workflows/test.yml to this repo before publication, and
        # a gate that cannot see into the one directory holding the CI
        # config is not a gate. Do not restore this exclusion.
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__')]
        paths.extend(os.path.join(dirpath, fn) for fn in filenames)
    return paths


check('no shipped file names the origin workspace', scan_tree(_ROOT), [])

# --- scan_tree: end-to-end fixtures, planted OUTSIDE this repo ------------
# Every fixture below lives in its own tempfile.mkdtemp(), never inside
# _ROOT -- a test that writes into the tree it scans could leave a planted
# file behind that fails the NEXT run for the wrong reason.

# MUST-MISS: a tree of only clean files scans empty. Without this, a
# scan_tree that returned every file it walked (or one hardcoded to always
# find something) would pass the must-hit fixture below for the wrong
# reason.
_clean_root = tempfile.mkdtemp()
with open(os.path.join(_clean_root, 'clean.py'), 'w', encoding='utf-8') as _fh:
    _fh.write('# nothing coupled in this file\n')
check('scan_tree: a clean tree scans empty (control)', scan_tree(_clean_root), [])

# MUST-HIT, end to end: the planted hit sits under .github/workflows/ --
# exactly where B7's CI workflow lands, and exactly the directory fix
# round 0 excluded from the walk. This single assertion is what would have
# caught that defect. Mixed case exercises the same lowercasing the real
# scan relies on.
_hit_root = tempfile.mkdtemp()
_gh_dir = os.path.join(_hit_root, '.github', 'workflows')
os.makedirs(_gh_dir)
with open(os.path.join(_gh_dir, 'probe.yml'), 'w', encoding='utf-8') as _fh:
    _fh.write('name: %s-MAIL\n' % _COUPLED[0].upper())
_hit_result = scan_tree(_hit_root)
check('scan_tree: a planted .github/workflows hit is found', len(_hit_result) > 0, True)
check('scan_tree: the hit names the planted .github/workflows path',
      any('.github' in h and 'workflows' in h for h in _hit_result), True)

# Encoding case: a coupled string sitting beside one invalid UTF-8 byte
# must still be reported -- the exact case the old bare
# `except Exception: continue` swallowed into a false negative.
_enc_root = tempfile.mkdtemp()
with open(os.path.join(_enc_root, 'bad_encoding.py'), 'wb') as _fh:
    _fh.write(('# %s-mail ' % _COUPLED[0]).encode('utf-8') + b'\xff\xfe')
check('scan_tree: a coupled string beside an invalid byte is still caught',
      len(scan_tree(_enc_root)) > 0, True)

# github-kkq4a: the ASCII precondition the comment above now states. A needle
# flush against an invalid byte, and against a truncated 4-byte lead, must
# still be REPORTED -- the decoder emits U+FFFD for the bad bytes without
# consuming the ASCII that follows.
for _label, _prefix in (('an invalid byte', b'\xff'),
                        ('a truncated f0 lead', b'\xf0'),
                        ('a truncated f0 90 80 lead', b'\xf0\x90\x80')):
    _adj_root = tempfile.mkdtemp()
    with open(os.path.join(_adj_root, 'adjacent.py'), 'wb') as _fh:
        _fh.write(b'# ' + _prefix + _COUPLED[0].encode('utf-8') + b'-mail\n')
    check('scan_tree: a needle survives %s flush against it' % _label,
          len(scan_tree(_adj_root)) > 0, True)

# MUST-MISS: a needle with one of its OWN bytes corrupted is NOT reported --
# and must not be. The needle is genuinely absent from those bytes; reporting
# it would mean the scan matches things that are not there.
_split_root = tempfile.mkdtemp()
with open(os.path.join(_split_root, 'split.py'), 'wb') as _fh:
    _fh.write(b'# ' + _COUPLED[0][:2].encode() + b'\xff'
              + _COUPLED[0][3:].encode() + b'-mail\n')
check('scan_tree: a needle with a corrupted interior byte is not reported',
      scan_tree(_split_root), [])

# --- github-9rwrl: inside a git work tree, "shipped" means what git ships ---
# The walk used to read every file on disk, so an untracked, git-IGNORED
# .claude/settings.local.json in a developer's checkout failed the real gate
# above -- a verdict about local debris, not about the tree. Each fixture is
# its own `git init` repo, and the ignore rule lives in the fixture's own
# .gitignore so the result never depends on the runner's global ignore file.
def _git_fixture(files, ignore='', stage=()):
    root = tempfile.mkdtemp()
    subprocess.run(['git', 'init', '-q', root], check=True, capture_output=True)
    if ignore:
        files = dict(files, **{'.gitignore': ignore})
    for rel, body in files.items():
        os.makedirs(os.path.join(root, os.path.dirname(rel)), exist_ok=True)
        with open(os.path.join(root, rel), 'w', encoding='utf-8') as _fh:
            _fh.write(body)
    if stage:
        subprocess.run(['git', '-C', root, 'add', '--'] + list(stage),
                       check=True, capture_output=True)
    return root


_NEEDLE_LINE = '# %s-mail\n' % _COUPLED[0]
_git_root = _git_fixture(
    {'tracked.py': _NEEDLE_LINE,
     '.github/workflows/new.yml': _NEEDLE_LINE,
     'local/settings.local.json': _NEEDLE_LINE},
    ignore='local/\n', stage=('tracked.py',))
_git_hits = scan_tree(_git_root)
# MUST-MISS: the ignored file never ships, so it is not a finding.
check('scan_tree: a git-ignored file is not scanned',
      any(h.startswith('local') for h in _git_hits), False)
# MUST-HIT: a TRACKED file is still scanned -- without this, a git mode that
# returned nothing at all would pass the must-miss above.
check('scan_tree: a tracked file in a git tree is still scanned',
      'tracked.py: %s' % _COUPLED[0] in _git_hits, True)
# MUST-HIT: an untracked but NOT ignored file ships on the next `git add -A`,
# so it counts -- and it sits under .github/workflows, the directory fix
# round 0 wrongly excluded. A git mode using --cached alone would miss it.
check('scan_tree: an untracked, unignored .github file is still scanned',
      any('.github' in h and 'new.yml' in h for h in _git_hits), True)

if FAILURES:
    print('FAIL (%d)' % len(FAILURES))
    for f in FAILURES:
        print('  ' + f)
    sys.exit(1)
print('ok')
