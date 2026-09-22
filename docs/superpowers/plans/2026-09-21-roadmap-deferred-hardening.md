# Roadmap Deferred Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the eight deferred findings from beads-roadmap's cold-start review — a globally-shared state file, two entry points that disagree about untagged repos, namespace-agnostic throughput counts, three test/comment gaps, and two documentation holes.

**Architecture:** Three behavioural changes to `bin/roadmap` (state path resolved from the config rather than a global constant; `no_tags` model semantics plus a new drift condition; namespace-filtered throughput), one contract change to `hooks/roadmap-cadence.py` (it reads the resolved state path back out of the `--json` payload instead of computing it), and documentation. No new dependencies — both suites stay standard-library-only and feed synthetic rows.

**Tech Stack:** Python 3.11 (stdlib only: `tomllib`, `argparse`, `json`, `subprocess`, `ast`). Tests are two hand-rolled assertion suites, not pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-roadmap-deferred-hardening-design.md`

## Global Constraints

- **Python 3.11.16**, pinned in `.mise.toml`. Standard library only — no new imports outside it. CI runs both suites on 3.11, 3.12 and 3.13.
- **Two suites, run both, every task:** `python3 bin/roadmap-selftest.py` and `python3 hooks/test_roadmap_cadence.py`. Each prints `ok` on success and `FAIL (n)` plus the failing labels on failure, exiting 1.
- **Assertion helpers differ between the suites — do not mix them up.** `bin/roadmap-selftest.py` has `check(label, got, want)`; `hooks/test_roadmap_cadence.py` has `check(label, cond)`.
- **Every new assertion needs both directions.** A detector that fires on everything and one that fires on nothing are indistinguishable from a single passing assertion. Pair each must-hit with a must-miss control.
- **No shipped file may name the origin workspace.** A decoupling scan at the end of `bin/roadmap-selftest.py` walks the tree for three coupled strings. Fixtures use the namespace `acme-app`; keep it that way.
- **`github-*` ids in comments are deliberate provenance.** Cite `github-kkq4a` in comments explaining code added by this plan, matching the existing style.
- The test module is loaded as `rm` (`rm.compute_throughput`, `rm.build_model`, …).
- Fixture helpers already exist: `issue(**kw)`, `tagged(v, **kw)` (appends `release:acme-app-<v>`), `closed_at(day, **kw)`.

---

### Task 1: M9 — namespace-filter the throughput counts

**Files:**
- Modify: `bin/roadmap:749`, `bin/roadmap:760` (inside `compute_throughput`)
- Test: `bin/roadmap-selftest.py` (throughput section, after the `check('share value', ...)` block near line 662)

**Interfaces:**
- Consumes: `release_versions(issue, cfg=None)` — already defined at `bin/roadmap:229`, returns the ascending list of versions on this issue **belonging to `cfg['release_namespace']`**.
- Produces: no signature change. `compute_throughput`'s `in_release_7d`, `in_release_28d` and `on_plan_share_14d` change meaning from "in any release set" to "in **this product's** release set".

**Why the existing tests cannot detect this change:** `TP_CLOSED`'s only labelled row is `release:acme-app-v0.15.0`, and `TEST_CFG['release_namespace']` is `acme-app`. That row counts identically under both helpers. A new fixture carrying a **foreign** namespace is what makes the fix falsifiable.

- [ ] **Step 1: Write the failing tests**

Add after the `check('share value', AFTER['on_plan_share_14d'], 1.0)` line:

```python
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
```

- [ ] **Step 2: Run the suite to verify the new assertions fail**

Run: `python3 bin/roadmap-selftest.py`
Expected: `FAIL (2)` naming `in_release_7d ignores a foreign namespace: got 2, want 1` and `on_plan_share_14d ignores a foreign namespace: got 1.0, want 0.5`. The control must **pass** — if `closed_7d still counts the foreign row (control)` also fails, the fixture is wrong, not the code.

- [ ] **Step 3: Apply the fix**

`bin/roadmap:749`, inside the `for days in (7, 28)` loop:

```python
        out['in_release_%dd' % days] = sum(1 for i in rows if release_versions(i, cfg))
```

`bin/roadmap:760`:

```python
        out['on_plan_share_14d'] = float(
            sum(1 for i in rows14 if release_versions(i, cfg))) / len(rows14)
```

Then amend `compute_throughput`'s docstring, adding after the existing first paragraph:

```python
    Every count here is NAMESPACE-FILTERED via release_versions(i, cfg), not
    release_labels() (github-kkq4a, M9). In a shared bd workspace the agnostic
    helper let another product's release labels count toward this product's
    on-plan share, and it produced an unsurfaced tell -- ">0 in a release set"
    printed beside `versions: {}`. Filtering drives those counts to 0 in the
    mismatch case, where condition 7 then fires with a named diagnosis instead
    of a number the reader has to interpret.
```

- [ ] **Step 4: Run both suites to verify they pass**

Run: `python3 bin/roadmap-selftest.py` then `python3 hooks/test_roadmap_cadence.py`
Expected: `ok` from both.

- [ ] **Step 5: Commit — BEFORE the mutation drill below**

The drill in Step 6 ends in `git checkout -- bin/roadmap`, which discards
**every** uncommitted change in that file, not just the mutation. An
implementer on this project lost a real fix exactly that way. Commit first;
amend afterwards if the drill changes your mind about anything.

```bash
git add bin/roadmap bin/roadmap-selftest.py
git commit -m "fix(roadmap): throughput counts this product's release sets, not every namespace (github-kkq4a)

compute_throughput used release_labels() where every version path uses
release_versions(i, cfg), so in a shared bd workspace another product's
release labels counted toward this product's on-plan share.

The existing fixtures could not detect the change -- TP_CLOSED's only
labelled row is already acme-app -- so the new assertions add a
foreign-namespace row, with a closed_7d control proving that row is in the
window and human-authored.

_namespace_mismatch deliberately KEEPS the agnostic helper; mutation-checked
that selftest:1245 fails if it is switched.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verify `_namespace_mismatch` is still pinned to the agnostic helper — do NOT add a test**

`_namespace_mismatch` (`bin/roadmap:247`) **must keep `release_labels`** — finding labels in some *other* namespace is its entire job, and `release_versions` would make it structurally unable to fire. This is already pinned: `bin/roadmap-selftest.py:1245` asserts `rm._namespace_mismatch(MISMATCH_MULTI, []) == ['ns-a', 'ns-b']`, and under `release_versions` the `labelled` list would be empty and it would return `None`.

Confirm the guard is real rather than assuming it:

```bash
python3 - <<'PY'
import re, pathlib
p = pathlib.Path('bin/roadmap')
s = p.read_text()
orig = s
s = s.replace("labelled = [i for i in open_issues + closed_issues if release_labels(i)]",
              "labelled = [i for i in open_issues + closed_issues if release_versions(i, cfg)]")
assert s != orig, "mutation did not apply -- line text drifted, re-check by hand"
p.write_text(s)
PY
python3 bin/roadmap-selftest.py; echo "EXIT=$?"
git checkout -- bin/roadmap
```

Expected: the mutated run **fails**, `EXIT=1`. Measured signature: not a named
`FAIL (n)` line but an **uncaught `KeyError: 7`** from
`check('c7 bypasses the throttle', conds(MM_MODEL, state())[7]['bypass'], True)`
— the detector returns `None`, condition 7 never fires, and the `conds(...)[7]`
index raises before the suite prints anything. (The earlier
`c7 fires on a full namespace mismatch` failure is recorded but never printed,
because the traceback aborts the run; that truncation is the deferred
`conds(...)[N]` class, `github-086tz`.) Either way the guard is real. If the
run passes, it is not — stop and report that, do not proceed. `git checkout`
restores the file; re-run `python3 bin/roadmap-selftest.py` afterwards and
confirm `ok`.

---

### Task 2: I5a — `init` accepts a repo with no `v*` tags

**Files:**
- Modify: `bin/roadmap` — `probe_layout` (~line 940) and `cmd_init` (~line 1002)
- Test: `bin/roadmap-selftest.py` (the `probe_layout` / `cmd_init` section — locate it with `grep -n 'probe_layout\|cmd_init' bin/roadmap-selftest.py`)

**Interfaces:**
- Produces: `probe_layout(root, run=None, load_issues_fn=None)` returns a dict that now carries **`'warnings': []`** alongside the existing `'workspace'`, `'tag_repo'`, `'release_namespace'`, `'ambiguous'`. `cmd_init` still returns `0` written / `2` refused.

**Why:** `init` refuses a tagless repo and tells the user to write `roadmap.toml` by hand — which routes them straight past the namespace probe, the one guard that genuinely cannot be replaced by a guess. A new repo with labels and no tag yet is legitimate. The namespace probe stays the only hard refusal.

- [ ] **Step 1: Write the failing tests**

Add to the `probe_layout` / `cmd_init` section. `_FakeRun` below mimics a `git for-each-ref` that succeeds and returns no tags; match the surrounding fixtures' existing style if they already define such a helper (check first — reuse it rather than duplicating).

```python
# --- I5 (github-kkq4a): init accepts what the runtime accepts --------------
# init used to REFUSE a repo with no semver v* tags and tell the user to write
# roadmap.toml by hand -- which routes them past the namespace probe, the one
# guard that genuinely cannot be replaced by a guess. A new repo with labels
# and no tag yet is a legitimate state. It is now a WARNING that still writes.
class _NoTagRun:
    """git for-each-ref that SUCCEEDS and finds no tags."""
    def __init__(self):
        self.returncode, self.stdout, self.stderr = 0, '', ''

    def __call__(self, *a, **kw):
        return self


with tempfile.TemporaryDirectory() as _d:
    os.makedirs(os.path.join(_d, '.git'))
    _probe = rm.probe_layout(
        _d, run=_NoTagRun(),
        load_issues_fn=lambda cfg=None: ([tagged('v0.16.0', id='a')], []))
    check('no-tags is a warning, not ambiguous', _probe['ambiguous'], [])
    check('no-tags warning is recorded',
          any('no semver v* tags' in w for w in _probe['warnings']), True)
    check('the namespace still came off the board',
          _probe['release_namespace'], 'acme-app')

    _buf = io.StringIO()
    _rc = rm.cmd_init(_d, '2026-09-21', _buf,
                      run=_NoTagRun(),
                      load_issues_fn=lambda cfg=None: ([tagged('v0.16.0', id='a')], []))
    check('init WRITES despite no tags', _rc, 0)
    check('init created roadmap.toml',
          os.path.exists(os.path.join(_d, 'roadmap.toml')), True)
    check('init printed the no-tags warning',
          'no semver v* tags' in _buf.getvalue(), True)

# MUST-MISS control: an AMBIGUOUS namespace is still a hard refusal that
# writes nothing. Without this, dropping every refusal would pass the arms
# above. The board here carries TWO namespaces, which cannot be resolved.
with tempfile.TemporaryDirectory() as _d:
    os.makedirs(os.path.join(_d, '.git'))
    _buf = io.StringIO()
    _rc = rm.cmd_init(
        _d, '2026-09-21', _buf, run=_NoTagRun(),
        load_issues_fn=lambda cfg=None: (
            [issue(id='a', labels=['release:ns-a-v1.0.0']),
             issue(id='b', labels=['release:ns-b-v1.0.0'])], []))
    check('ambiguous namespace is still refused (control)', _rc, 2)
    check('a refused init writes nothing (control)',
          os.path.exists(os.path.join(_d, 'roadmap.toml')), False)
```

- [ ] **Step 2: Run the suite to verify the new assertions fail**

Run: `python3 bin/roadmap-selftest.py`
Expected: failures on `no-tags is a warning, not ambiguous`, `no-tags warning is recorded`, `init WRITES despite no tags`, `init created roadmap.toml`, `init printed the no-tags warning`. The two `(control)` arms must **pass** already.

- [ ] **Step 3: Move the no-tags reason from `ambiguous` to `warnings`**

In `probe_layout`, change the initial dict:

```python
    out = {'workspace': '.', 'tag_repo': '.',
           'release_namespace': None, 'ambiguous': [], 'warnings': []}
```

and change the tag check from `ambiguous` to `warnings` (github-kkq4a, I5):

```python
    tags = [t for t in (p.stdout or '').split() if parse_version(t)]
    if not tags:
        # A WARNING, not a refusal (github-kkq4a, I5). Refusing here told the
        # user to write roadmap.toml by hand, which routes them past the
        # namespace probe below -- the one thing here that genuinely cannot be
        # guessed. A repo with release labels and no tag cut yet is a real,
        # expected state; the runtime now says so too (condition 8).
        out['warnings'].append(
            'no semver v* tags in %s yet -- nothing has been cut, so no '
            'version will show as in flight until you tag one' % root)
```

Leave the two genuine `ambiguous` arms (not a git repo; `git` exited non-zero) exactly as they are, and leave the namespace probe in `ambiguous`.

- [ ] **Step 4: Print warnings from `cmd_init`**

In `cmd_init`, after the `out.write('  convention_start  = %s ...')` line and **before** the `with open(path, 'w')` block:

```python
    for warning in probe['warnings']:
        out.write('\nWARNING: %s\n' % warning)
```

- [ ] **Step 5: Run both suites to verify they pass**

Run: `python3 bin/roadmap-selftest.py` then `python3 hooks/test_roadmap_cadence.py`
Expected: `ok` from both. If an existing assertion expecting a no-tags refusal now fails, that assertion is pinning the old contract — update it to the new one and say so in the commit message rather than deleting it.

- [ ] **Step 6: Commit**

```bash
git add bin/roadmap bin/roadmap-selftest.py
git commit -m "fix(roadmap): init accepts a tagless repo with a warning, not a refusal (github-kkq4a)

init refused 'no semver v* tags' and told the user to write roadmap.toml by
hand -- which routes them straight past the namespace probe, the one guard
here that genuinely cannot be replaced by a guess. A repo carrying release
labels with no tag cut yet is a legitimate state.

probe_layout grows a warnings list; the no-tags reason moves there and init
prints it and still writes. An ambiguous namespace remains a hard refusal,
with a control proving a refused init still writes nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: I5b — the runtime stops calling the lowest version "in flight"

**Files:**
- Modify: `bin/roadmap` — `build_model` (~line 366), `evaluate` (~line 583, new condition 8)
- Test: `bin/roadmap-selftest.py` (model section near the existing `build_model` fixtures, and the conditions section)

**Interfaces:**
- Consumes: nothing from Task 2.
- Produces: `build_model(open_issues, closed_issues, tags)` now sets `model['no_tags']` (bool). With `no_tags` true, `model['in_flight']` is `None` and `model['planned']` holds **every** non-patch version. `evaluate()` emits a condition with `'id': 8, 'bypass': True`.

**Why:** with `tags == []`, `cut` is `None`, so `above` admits every version and `in_flight = above[0]` is the **lowest** — an already-shipped release renders as in progress.

- [ ] **Step 1: Write the failing tests**

```python
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

# Condition 8 names the state, and is bypass so a cold install always hears it.
NT_CONDS = rm.evaluate(NT, FRESH, '2026-09-21')
_c8 = [c for c in NT_CONDS if c['id'] == 8]
check('condition 8 fires with no tags', len(_c8), 1)
check('condition 8 is bypass', _c8[0]['bypass'], True)
check('condition 8 names the tag_repo',
      any(TEST_CFG['tag_repo'] in l for l in _c8[0]['lines']), True)
# MUST-MISS: with a tag cut, condition 8 is silent.
check('condition 8 is silent with a tag (control)',
      [c for c in rm.evaluate(WT, FRESH, '2026-09-21') if c['id'] == 8], [])

# Condition 1 (HORIZON EMPTY) must NOT double-fire on a tagless board that
# carries labels -- planned is non-empty, so there IS a horizon. On a board
# with neither tags nor labels both fire, which is correct: an empty horizon
# and an untagged repo are two different things a cold install needs told.
check('condition 1 stays quiet on a tagless board WITH labels',
      [c for c in NT_CONDS if c['id'] == 1], [])
_cold = rm.evaluate(rm.build_model([], [], []), FRESH, '2026-09-21')
check('a wholly cold board hears both 1 and 8',
      sorted(c['id'] for c in _cold if c['id'] in (1, 8)), [1, 8])

# refresh_baselines must never claim a cut advanced when there are no tags.
_nt_state = dict(FRESH, last_cut=None, baselines={})
rm.refresh_baselines(NT, _nt_state)
check('no tags: cut_advanced is never True', NT['cut_advanced'], False)
```

- [ ] **Step 2: Run the suite to verify the new assertions fail**

Run: `python3 bin/roadmap-selftest.py`
Expected: failures including `no tags: nothing is in flight: got (0, 16, 0), want None` and a `KeyError`-free failure on `no_tags`. All `(control)` arms must pass. If `with a tag: in_flight is the lowest above the cut (control)` fails, stop — the change is about to alter tagged behaviour, which it must not.

- [ ] **Step 3: Implement the model change**

In `build_model`, replace the `above` / `in_flight` / `planned` block:

```python
    # No tags at all is a DIFFERENT state from "no tag above the cut"
    # (github-kkq4a, I5). With cut None, `above` admits every version, and
    # taking above[0] as in_flight made the LOWEST -- often an already-shipped
    # release -- render as in progress. Nothing has been cut, so nothing is in
    # flight and every labelled version is still ahead. Condition 8 says so.
    no_tags = not tags
    above = sorted(v for v in all_versions if cut is None or v > cut)
    # A PATCH is never "planned": SemVer already marks it unplanned, and the
    # whole hotfix design depends on a dot release being something you cut
    # without having roadmapped it. A patch CAN be in flight -- that is a
    # hotfix shipping -- so only the planned list filters them out.
    if no_tags:
        in_flight = None
        planned = [v for v in above if not is_patch(v)]
    else:
        in_flight = above[0] if above else None
        planned = [v for v in above[1:] if not is_patch(v)]
```

and add `'no_tags': no_tags,` to the returned dict, next to `'cut'`.

- [ ] **Step 4: Implement condition 8**

In `evaluate()`, after the condition 7 block and **before** `return sorted(out, key=lambda c: c['id'])`:

```python
    # 8 -- the tag_repo carries no semver v* tags at all (github-kkq4a, I5).
    # Always bypass, same reasoning as conditions 1 and 7: the board above
    # renders every version as planned, which is honest but needs explaining,
    # and a cold install that never hears this cannot tell why nothing is ever
    # in flight. init now WARNS on the same state instead of refusing, so this
    # is the runtime half of one finding, not a second one.
    if model.get('no_tags'):
        lines = ['NO VERSION TAGS -- %s carries no semver v* tags, so nothing'
                 ' has been cut.' % cfg['tag_repo']]
        lines.append('  No version is in flight, and every version above is'
                     ' shown as PLANNED.')
        lines.append('  Cut a tag (e.g. `git tag v0.1.0`) for roadmap to tell'
                     ' shipped from planned.')
        out.append({'id': 8, 'bypass': True, 'lines': lines})
```

- [ ] **Step 5: Run both suites to verify they pass**

Run: `python3 bin/roadmap-selftest.py` then `python3 hooks/test_roadmap_cadence.py`
Expected: `ok` from both.

- [ ] **Step 6: Confirm the board renders sanely with no tags**

The spec traced these knock-ons as already handled; confirm rather than assume:

```bash
python3 - <<'PY'
import importlib.machinery, importlib.util
spec = importlib.util.spec_from_loader('rm', importlib.machinery.SourceFileLoader('rm', 'bin/roadmap'))
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)
rm.configure({'workspace': '/nonexistent', 'tag_repo': '/nonexistent/acme-app',
              'release_namespace': 'acme-app', 'convention_start': '2026-09-20',
              'auto_label_prefixes': ()})
def tagged(v, **kw):
    row = {'id': 'x', 'title': 't', 'labels': ['release:acme-app-' + v], 'priority': 3,
           'issue_type': 'feature', 'status': 'open', 'updated_at': '2026-09-21T00:00:00Z'}
    row.update(kw); row['labels'] = ['release:acme-app-' + v]; return row
m = rm.build_model([tagged('v0.16.0', id='a'), tagged('v0.18.0', id='b')], [], [])
m['throughput'] = {}
st = {'last_reported_at': 0.0, 'convention_start': '2026-09-20', 'baselines': {}, 'last_cut': None}
print(rm.render_board(m, rm.evaluate(m, st, '2026-09-21')))
PY
```

Expected, and check each by eye: no `IN FLIGHT` block; both versions under `PLANNED`; `creep:   n/a — no version in flight`; the `NO VERSION TAGS` lines present. Paste the output into the commit message. If a traceback appears instead, a knock-on was missed — fix it before committing.

- [ ] **Step 7: Commit**

```bash
git add bin/roadmap bin/roadmap-selftest.py
git commit -m "fix(roadmap): no tags means nothing is in flight, not the lowest version (github-kkq4a)

With tags == [], cut is None, so `above` admitted every version and
in_flight = above[0] made the LOWEST one -- often an already-shipped
release -- render as in progress. Nothing has been cut, so nothing is in
flight and every labelled version is still ahead.

Adds model['no_tags'] and condition 8 (bypass), the runtime half of the same
finding init's warning covers. Controls pin the tagged path unchanged, pin
condition 8 silent with a tag, and pin that condition 1 does not double-fire
on a tagless board that carries labels.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: I3a — the state file moves next to `roadmap.toml`

**Files:**
- Modify: `bin/roadmap` — `load_config` (return dict, ~line 196), `DEFAULT_STATE` (~line 425), `render_json` (~line 799), `main` (~lines 1062, 1106, 1137, 1141)
- Test: `bin/roadmap-selftest.py` — **two separate insertion points.** The `load_config` / `default_state_path` assertions go after the `load_state` / `save_state` section (~line 625). The final `--json reports the resolved state path` assertion uses `_run_main`, which is not defined until ~line 941, so **it must go into the `_run_main` section instead** (after the existing `successful run: no unavailable key (control)` block). Putting it at ~625 raises `NameError` at import.

**Interfaces:**
- Produces:
  - `LEGACY_STATE` — module constant, the old `~/.claude/roadmap-cadence-state.json` path (renamed from `DEFAULT_STATE`).
  - `default_state_path(cfg)` → `str`. Returns `<dirname(cfg['config_path'])>/.roadmap-state.json`, or `LEGACY_STATE` when `config_path` is absent.
  - `load_config(...)` return dict gains `'config_path'` (absolute, realpath'd).
  - `render_json` emits `"state_path"`, read from `model.get('state_path')`.

**Why:** the collision surface is five fields (`last_cut`, `baselines`, `convention_start`, `last_reported_at`, `unconfigured_reported`), not just `baselines`. One config, one state file fixes all five.

**Do not add `config_path` to `CONFIG_KEYS`.** That tuple validates the *raw TOML*; leaving it out means a user who writes `config_path` in their file still gets the unknown-key refusal.

- [ ] **Step 1: Write the failing tests**

```python
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

# main() reports the resolved path so the SessionStart hook can stamp the SAME
# file instead of computing its own.
# >>> THIS BLOCK GOES IN THE _run_main SECTION (~line 941+), NOT at ~625.
# _run_main is not defined yet at 625 and the suite asserts at import time,
# so placing it there raises NameError before any check runs.
with tempfile.TemporaryDirectory() as _d:
    _sp = os.path.join(_d, 'state.json')
    _rc, _out, _err = _run_main(['--json', '--state', _sp, '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[])
    check('--json reports the resolved state path',
          json.loads(_out).get('state_path'), _sp)
```

- [ ] **Step 2: Run the suite to verify the new assertions fail**

Run: `python3 bin/roadmap-selftest.py`
Expected: `AttributeError: module 'roadmap_under_test' has no attribute 'default_state_path'` — a crash, not a `FAIL` line, because the suite asserts at import time. That is the expected starting state.

- [ ] **Step 3: Add `config_path`, `LEGACY_STATE` and `default_state_path`**

In `load_config`, add to the returned dict (the raw-key validation above it is untouched):

```python
    return {'workspace': _resolve(raw['workspace']),
            'tag_repo': _resolve(raw['tag_repo']),
            'release_namespace': raw['release_namespace'],
            'convention_start': started,
            'auto_label_prefixes': tuple(raw.get('auto_label_prefixes') or ()),
            # Where this config was loaded FROM, so the state file can default
            # beside it (github-kkq4a, I3). Deliberately NOT in CONFIG_KEYS:
            # that tuple validates the raw TOML, so a user who writes
            # config_path by hand still gets the unknown-key refusal.
            'config_path': os.path.realpath(path)}
```

Replace the `DEFAULT_STATE` constant (~line 425):

```python
# The pre-github-kkq4a location: ONE file for every workspace on the machine.
# Kept only as the fallback for a caller that configured by hand (no
# config_path) and as the path the migration notice names.
LEGACY_STATE = os.path.expanduser('~/.claude/roadmap-cadence-state.json')


def default_state_path(cfg=None):
    """-> where this install's state file lives: beside its roadmap.toml.

    One global file (I3) collided on FIVE fields, not one -- last_cut,
    baselines (keyed by bare version), convention_start, last_reported_at and
    unconfigured_reported. Keying baselines by namespace would have fixed one
    row and left the observed symptom (a scratch repo overwriting the live
    last_cut) in place.

    A cfg with no config_path -- a caller that configured by hand rather than
    through load_config -- falls back to LEGACY_STATE rather than raising, so
    no call site can KeyError on a dict it built itself.
    """
    cfg = cfg or CONFIG
    path = (cfg or {}).get('config_path')
    if not path:
        return LEGACY_STATE
    return os.path.join(os.path.dirname(path), '.roadmap-state.json')
```

Update `load_state`'s default argument to `path=LEGACY_STATE` (it is always called with an explicit path; this only keeps the signature valid).

- [ ] **Step 4: Resolve the path in `main()` and report it**

Change the argparse default (~line 1062) to `ap.add_argument('--state', default=None)`.

After `configure(load_config(today=args.today))` succeeds and before `st = load_state(...)` (~line 1106):

```python
    # Resolved AFTER the config loads, because it depends on it (github-kkq4a,
    # I3). An explicit --state still wins -- that is the testing seam and the
    # escape hatch for a deliberately shared file.
    state_path = args.state or default_state_path(CONFIG)

    # One-time notice, never an automatic copy. Auto-seeding the new file from
    # the legacy global one would hand EVERY workspace the same baselines, so
    # two products would each inherit the other's. `no baseline yet` is an
    # honest state this design deliberately keeps (refresh_baselines refuses to
    # invent a plan-at-cut-time); a WRONG baseline is the false-clean signal it
    # exists to prevent. This prints once in practice: save_state creates the
    # file before the next run.
    if not os.path.exists(state_path) and os.path.exists(LEGACY_STATE):
        sys.stderr.write(
            'roadmap: state now lives beside roadmap.toml. To keep this '
            'install\'s scope-creep baselines, copy it once:\n'
            '    cp %s %s\n' % (LEGACY_STATE, state_path))
```

Replace the three `args.state` uses with `state_path` (`load_state`, and both `save_state` calls).

Thread the path onto the model, next to the existing `model['baseline']` / `model['convention_start']` lines — the established pattern for giving a renderer something it has no other access to:

```python
    # Same pattern as 'baseline' and 'convention_start' above: render_json has
    # no access to args, and the SessionStart hook needs the resolved path to
    # stamp the SAME file rather than computing its own (github-kkq4a, I3).
    model['state_path'] = state_path
```

In `render_json`, add to the emitted dict:

```python
        'state_path': model.get('state_path'),
```

- [ ] **Step 5: Run both suites to verify they pass**

Run: `python3 bin/roadmap-selftest.py` then `python3 hooks/test_roadmap_cadence.py`
Expected: `ok` from both. `hooks/test_roadmap_cadence.py` still passes here because every existing hook test sets `ROADMAP_CADENCE_STATE`; the hook itself changes in Task 5.

- [ ] **Step 6: Commit**

```bash
git add bin/roadmap bin/roadmap-selftest.py
git commit -m "fix(roadmap): state lives beside roadmap.toml, not one file per machine (github-kkq4a)

--state defaulted to ~/.claude/roadmap-cadence-state.json for every workspace
and nothing in it was keyed by workspace, so FIVE fields collided: last_cut,
baselines (bare-version keys), convention_start, last_reported_at and
unconfigured_reported. Keying baselines by namespace would have fixed one row
and left the observed symptom -- a scratch repo overwriting the live
last_cut -- in place.

load_config now reports config_path (deliberately not a writable TOML key, so
the unknown-key guard still refuses it by hand), default_state_path resolves
beside it, and --json reports the resolved path for the hook to stamp.

No automatic migration: seeding the new file from the global one would hand
every workspace the same baselines. A one-time notice names the copy instead.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: I3b — the hook stamps the file the binary actually used

**Files:**
- Modify: `hooks/roadmap-cadence.py` — `DEFAULT_STATE` (~line 47), `main()` (~line 112)
- Test: `hooks/test_roadmap_cadence.py` — the AST control block (~lines 183-199), plus new arms

**Interfaces:**
- Consumes: `payload['state_path']` from Task 4's `render_json`.
- Produces: no new functions. The hook's subprocess argv becomes `[binary, '--json']`.

**The AST control trap — read this before editing the test file.** `hooks/test_roadmap_cadence.py:198` asserts `'--state' in _tokens` as a control proving the AST walk actually found the hook's argv list. **Do not delete the line** — deleting it halves the guard that keeps `no write verb reaches any hook argv literal` from passing vacuously.

**Corrected after implementation.** An earlier draft of this step told you to turn that line into a must-miss, `check('the hook does not pass --state (it reads state_path back)', '--state' not in _tokens)`. That is **incompatible with Step 3 below**, which deliberately keeps a conditional `argv += ['--state', forced_state]` for the testing seam and the deliberate-override escape hatch: the literal is still in the source, so the must-miss fails against the correct hook. The implementer deviated here and was right to. What replaced it — pinning the contract at **runtime**, with a stub that records its own `sys.argv` — is strictly better anyway: an AST literal proves only that a string exists somewhere in the file, never that it reaches the subprocess.

- [ ] **Step 1: Write the failing tests**

Keep line 198 as a control, re-commented to say what it does and does not prove:

```python
# A second witness that the AST walk found the (conditional) override literal
# `['--state', forced_state]` (github-kkq4a, I3). This proves the walk saw
# that branch -- nothing more. It does NOT prove the DEFAULT path omits
# --state, or that the override's value reaches argv at runtime. The real
# behavioural contract is pinned at runtime below.
check('control — AST walk found the override argv literal', '--state' in _tokens)
```

Then pin the contract behaviourally, both directions, with a stub that writes its own `sys.argv` to a capture file: with `ROADMAP_CADENCE_STATE` unset the recorded argv carries `--json` and **no** `--state`; with it set, `--state` is present and followed by the exact forced path. Guard each read of the capture file with `os.path.exists`, and use `None` — never `[]` — as the fallback: an empty container satisfies every `not in`, so the must-miss would pass vacuously against a falsified run that never captured anything. Gate both directions on a dedicated `captured the argv at all` must-hit.

Then add new behavioural arms. `run_hook` always sets `ROADMAP_CADENCE_STATE`, so these call the hook directly with a controlled environment:

```python
# --- I3 (github-kkq4a): the hook stamps the path the BINARY resolved -------
# The hook used to compute ~/.claude/roadmap-cadence-state.json itself and
# pass it with --state, so every workspace on the machine shared one throttle
# stamp. It now runs --json with no --state and stamps payload['state_path'].
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
```

- [ ] **Step 2: Run the hook suite to verify the new assertions fail**

Run: `python3 hooks/test_roadmap_cadence.py`
Expected, corrected to match what was actually built: `hook stamped the path the payload named` and `the stamp it wrote is a real timestamp` fail — the pre-Step-3 hook computes its own path, so the payload's file is never created — along with `argv omits --state when ROADMAP_CADENCE_STATE is unset`, since the old hook passes `--state` on every run. Both AST controls (`found the hook argv`, `found the override argv literal`) must still pass. There is **no** `the hook does not pass --state` arm: that assertion cannot fail against the correct hook, which keeps the conditional literal, and it is not written.

- [ ] **Step 3: Change the hook**

Rename the constant and add a comment:

```python
# The pre-github-kkq4a location: ONE file for every workspace on the machine.
# Still the fallback when the payload carries no state_path -- the unavailable
# and unconfigured shapes, where there is no roadmap.toml to sit beside.
LEGACY_STATE = os.path.expanduser('~/.claude/roadmap-cadence-state.json')
```

In `main()`, replace the state handling:

```python
    forced_state = os.environ.get('ROADMAP_CADENCE_STATE')
```

Change the subprocess call to drop `--state` — when `ROADMAP_CADENCE_STATE` is set it is still forced, because that is the testing seam and the deliberate-override escape hatch:

```python
    argv = [binary, '--json']
    if forced_state:
        argv += ['--state', forced_state]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return 0  # fail open
```

After the payload parses, resolve the stamp path from it:

```python
    # The binary resolves the state path from ITS config; the hook must stamp
    # the SAME file rather than computing its own (github-kkq4a, I3). A
    # missing state_path -- the unavailable/unconfigured payload shape, or an
    # older binary -- falls back to the legacy global path, which is also
    # where unconfigured_reported has to live: an install with no roadmap.toml
    # has no config directory for state to sit beside. The known consequence
    # is that a SECOND never-configured workspace is not nudged again.
    state = forced_state or payload.get('state_path') or LEGACY_STATE
```

Delete the old `state = os.environ.get('ROADMAP_CADENCE_STATE', DEFAULT_STATE)` line at the top of `main()`. Every later `read_stamp(state)` / `write_stamp(state)` / `already_nudged(state)` / `mark_nudged(state)` call is unchanged.

- [ ] **Step 4: Run both suites to verify they pass**

Run: `python3 hooks/test_roadmap_cadence.py` then `python3 bin/roadmap-selftest.py`
Expected: `ok` from both.

- [ ] **Step 5: Falsify the hook suite, as its own docstring prescribes**

The suite's stated falsifiability check — a stub that always speaks must fail the SILENT arms:

```bash
printf '#!/usr/bin/env python3\nimport json\nprint(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"always"}}))\n' > /tmp/always_speaks.py
chmod +x /tmp/always_speaks.py
python3 hooks/test_roadmap_cadence.py /tmp/always_speaks.py; echo "EXIT=$?"
```

Expected: **non-zero** exit with `FAIL (n)`. If it exits 0, the suite no longer discriminates — stop and report it rather than committing.

- [ ] **Step 6: Commit**

```bash
git add hooks/roadmap-cadence.py hooks/test_roadmap_cadence.py
git commit -m "fix(roadmap): the hook stamps the state file the binary resolved (github-kkq4a)

The hook computed ~/.claude/roadmap-cadence-state.json itself and passed it
with --state, so every workspace on the machine shared one throttle stamp. It
now runs --json with no --state and stamps payload['state_path'].

A payload with no state_path -- the unavailable/unconfigured shape, or an
older binary -- falls back to the legacy path, which is also where
unconfigured_reported must stay: an install with no roadmap.toml has no config
directory for state to sit beside.

The AST control on '--state' became a MUST-MISS pinning the new contract
rather than being deleted; deleting it would have halved the guard keeping
'no write verb reaches any hook argv literal' from passing vacuously.
Re-falsified the suite against /tmp/always_speaks.py.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: the three deferred test/comment items, as corrected

**Files:**
- Modify: `bin/roadmap-selftest.py` only — three test sections plus one comment inside `scan_tree`. **Do not touch `bin/roadmap` in this task**; `compute_throughput`'s docstring belongs to Task 1.

**Interfaces:** no production code changes at all. This task is tests and one test-file comment.

**Two of the three premises were corrected during spec review — build what is actually missing, not what the ticket said.**

- [ ] **Step 1: Cover the two genuinely-uncovered arms of the `load_config` fail-open branch**

The ticket says this branch "has no automated test". Stale — `bin/roadmap-selftest.py:1002-1034` already drives it past `_run_main`'s stub on both arms. What is missing: `_unc_err` and `_bad_err` are captured and **never asserted**, and both runs pass `--json` so the text-mode branch never executes.

Add assertions immediately after the existing `check('unconfigured main() --json carries unconfigured=True', ...)` and after the malformed-config control, then add the text-mode arm:

```python
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
```

- [ ] **Step 2: Cover `compute_throughput`'s `convention_start` fallback, both arms**

Never exercised because every call site passes it explicitly. Add to the throughput section:

```python
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

# Arm 2: no cfg AND no module CONFIG -> today(). With today == '2026-10-04'
# the warm-up has not started, so the share is suppressed.
_saved_cfg = rm.CONFIG
rm.configure(None)
try:
    check('no cfg and no CONFIG falls back to today (warm-up active)',
          rm.compute_throughput([], TP_CLOSED, [], '2026-10-04', None,
                                cfg=None)['on_plan_share_14d'], None)
finally:
    rm.configure(_saved_cfg)
check('CONFIG restored after the fallback arm (control)',
      rm.CONFIG['release_namespace'], 'acme-app')
```

- [ ] **Step 3: Pin the ASCII precondition on `scan_tree` and amend the comment**

The ticket claims the `errors=replace` comment overclaims: *"'hide' is FALSE — a replacement byte inside a needle's span splits it."* **That was probed and disproved.** Python never folds a byte `< 0x80` into a replacement's maximal subpart, so an all-ASCII needle survives an adjacent invalid byte. Every apparent "hide" is a case where the needle was never in the bytes.

The real defect is that the claim depends on the needles being ASCII and does not say so. Amend the comment in `bin/roadmap-selftest.py`'s `scan_tree` — replace the sentence `a REPLACEMENT byte cannot hide a needle since none of the needles contain one.` with:

```python
            # cannot hide a needle, because every needle is pure ASCII and
            # Python never folds a byte < 0x80 into a replacement's maximal
            # subpart -- verified by the fixtures below, which plant a needle
            # flush against an invalid byte and against a truncated \xf0\x90\x80
            # lead. This property is NOT free: it follows from the needles
            # being ASCII. Adding a non-ASCII needle to _COUPLED voids it, and
            # the reasoning here must be redone rather than assumed to carry.
```

Then add fixtures beside the existing encoding case at the end of the file:

```python
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
```

- [ ] **Step 4: Run both suites to verify they pass**

Run: `python3 bin/roadmap-selftest.py` then `python3 hooks/test_roadmap_cadence.py`
Expected: `ok` from both.

- [ ] **Step 5: Commit**

```bash
git add bin/roadmap-selftest.py
git commit -m "test(roadmap): close the three deferred coverage gaps, two of them corrected (github-kkq4a)

Two premises did not survive verification and the work follows what is
actually missing:

- 'the fail-open wrapper has no automated test' is stale; selftest:1002-1034
  already drives that branch past _run_main's stub on both arms. The real gap
  was that _unc_err/_bad_err were captured and never asserted, and both runs
  pass --json so text mode never executed. Both are now covered.
- 'the errors=replace comment overclaims about hiding' is WRONG. Probed:
  Python never folds a byte < 0x80 into a replacement's maximal subpart, so an
  all-ASCII needle survives an invalid byte and a truncated f0 90 80 lead
  flush against it. Every apparent hide is a case where the needle was never
  in the bytes. The comment now states the ASCII precondition it depends on,
  with fixtures pinning it and a must-miss for a corrupted interior byte.

compute_throughput's convention_start fallback is covered on both arms, each
with a control.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: M10 / M11 — README, CHANGELOG, gitignore, version

**Files:**
- Modify: `README.md`, `.gitignore`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Fix the README's two documentation holes**

In the **First run** section, replace the opening sentence `Before anything else, run `roadmap init` once per workspace.` with:

````markdown
Before anything else, run `init` once per workspace. **Inside a Claude Code
session** — where the plugin's `bin/` is on your `PATH` — that is:

```
/roadmap init
```

Outside a session, bare `roadmap` will not resolve: `PATH` only carries the
plugin's `bin/` because Claude Code injects it. Call it by path instead:

```
~/.claude/plugins/cache/beads-roadmap/roadmap/<version>/bin/roadmap init
```

**It writes `roadmap.toml` into the current working directory**, so run it
from the directory you want to be the root of this install — normally the
workspace `bd` runs in. Relative paths inside the file resolve against the
file, never against your shell's cwd. The state file (`.roadmap-state.json`,
the scope-creep baseline plus the hook's throttle stamp) lands next to it; add
it to your `.gitignore`.
````

In the **Requirements** section, after the Python paragraphs, add:

````markdown
**`bd` (beads).** The tool shells out to exactly one read, twice:

```
bd list --status=open   -n 0 --json
bd list --status=closed -n 0 --json
```

and reads these fields off each row: `id`, `title`, `labels`, `issue_type`,
`priority`, `parent`, `updated_at`. `-n 0` is mandatory — `bd list` silently
truncates otherwise.

**Verified against `bd` 1.2.2. No lower bound has been tested**, so no minimum
is claimed here: an older `bd` may well work, and stating a floor that was
never exercised would be a guess wearing the costume of a fact. If yours is
older, check it emits those flags and fields. A `bd` that rejects the flags
exits non-zero and `roadmap` fails open with a named reason; one that omits
`labels` would render an empty board instead, which is why the check is worth
doing by hand.
````

In the paragraph about state ("The only local state it keeps…"), replace `a small state file` with `a small state file next to your `roadmap.toml``.

- [ ] **Step 2: Add the state file to `.gitignore`**

Append:

```
# roadmap's per-install state (scope-creep baseline + hook throttle stamp).
# It lives beside roadmap.toml and is per-checkout, never shared.
.roadmap-state.json
```

- [ ] **Step 3: Create `CHANGELOG.md`**

Reconstruct the earlier entries from `git log --oneline` — do not invent them.

```markdown
# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-09-22

Deferred hardening from the cold-start review.

### Changed

- **The state file now lives beside `roadmap.toml`** (`.roadmap-state.json`)
  instead of one `~/.claude/roadmap-cadence-state.json` shared by every
  workspace on the machine. Five fields collided there — `last_cut`,
  `baselines` (keyed by bare version), `convention_start`, `last_reported_at`
  and `unconfigured_reported` — so two products at the same version, or a
  throwaway run from a scratch repo, silently overwrote each other.
  **There is no automatic migration**, on purpose: seeding the new file from
  the old one would hand every workspace the same baselines. `roadmap` names
  both paths and the `cp`, and the SessionStart hook says the same thing once
  in-session — the old file was shared, so it may hold *another* workspace's
  baselines, and copying it is right only in the workspace that was using it.
  Ignoring it costs a re-baseline with `roadmap pin`. See
  [Upgrading from 0.1.x](README.md#upgrading-from-01x).
- **A repo with no semver `v*` tags no longer shows its lowest version as "in
  flight".** Nothing has been cut, so nothing is in flight and every labelled
  version is reported as planned, with a new drift condition naming the state.
- **`roadmap init` accepts a repo with no `v*` tags**, printing a warning
  instead of refusing. The old refusal told users to write `roadmap.toml` by
  hand, which routed them past the release-namespace probe — the one thing
  `init` checks that cannot be replaced by a guess. An ambiguous namespace is
  still a hard refusal.
- **Throughput counts only your own release namespace.** `in_release_7d`,
  `in_release_28d` and the on-plan share used a namespace-agnostic label test,
  so in a shared `bd` workspace another product's labels counted toward your
  on-plan share.

### Added

- `state_path` in the `--json` payload, so the SessionStart hook stamps the
  file the binary actually resolved rather than computing its own.
- `legacy_state_available` in the `--json` payload, and a one-time
  `additionalContext` message in the SessionStart hook keyed on it. The
  binary's own notice goes to stderr, which the hook discards, so on the
  default install path the state move reached nobody.
- `CHANGELOG.md` (this file).

### Documentation

- The README now says **where `roadmap.toml` is written** (the current
  working directory), that bare `roadmap` resolves only inside a Claude Code
  session — with `/roadmap init` and the explicit-path form both shown — and
  what `bd` surface the tool consumes, verified against `bd` 1.2.2 with no
  lower bound claimed.

## [0.1.2] — 2026-09-21

### Fixed

- `SKILL.md` and `commands/roadmap.md` call bare `roadmap` rather than an
  expanded `${CLAUDE_PLUGIN_ROOT}` path, which the harness expanded into a
  60-character absolute path into the plugin cache.

## [0.1.1] — 2026-09-21

0.1.0 shipped with two Critical defects found by a cold-start review, both on
the default install path and both silent rather than loud, plus four related
fixes bundled into the same release.

### Fixed

- `init` refuses to guess `release_namespace` from the directory name;
  it now reads the namespace off the board itself and refuses when it's
  ambiguous or absent, naming what it found instead of silently rendering
  an empty roadmap under the wrong namespace.
- An ambient `BEADS_DIR` no longer overrides the configured `workspace` —
  it was silently redirecting `bd` to an unrelated board while `roadmap.toml`
  still claimed the right one.
- `roadmap plan` distinguishes "nothing descends from the gating epics"
  (ready to cut) from "there is no gating epic to check against" (no verdict
  available); both used to print as the same false "ready to cut" claim.
- The unenforced Python 3.11 floor now fails open with a named reason
  (`roadmap: unavailable: ...`) instead of an uncaught traceback on an older
  interpreter — the traceback's exit 1 read as permanent, undiagnosable
  silence through the SessionStart hook's fail-open handling.
- A fresh install with no `roadmap.toml` now tells the user once, via the
  hook, to run `roadmap init`; every other "unavailable" reason stays
  silent, unchanged. Previously this state was indistinguishable from every
  other silent failure.
- Remediation text named `bin/roadmap`, which doesn't exist for an installed
  plugin (Claude Code puts a bare `roadmap` on `PATH`) — fixed in the text
  the binary itself emits. (Two more instances, in `SKILL.md` and
  `commands/roadmap.md`, were missed here and fixed in 0.1.2.)
- The user-facing surfaces (README, `SKILL.md`, `commands/roadmap.md`) match
  the honest plan verdict above, and the README's drift-condition count was
  corrected for the namespace-mismatch condition this release added.

## [0.1.0] — 2026-09-21

Initial release: a derived product roadmap over beads.
```

- [ ] **Step 4: Bump the version in both manifests**

`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`: `"version": "0.1.2"` → `"version": "0.2.0"`. **Both files** — they carry the version independently and 0.1.2 shipped with exactly this two-place edit.

- [ ] **Step 5: Verify the docs against the code rather than against the plan**

```bash
grep -n 'roadmap-state\|state_path\|0\.2\.0' README.md CHANGELOG.md .gitignore .claude-plugin/*.json
python3 -c "import json;print(json.load(open('.claude-plugin/plugin.json'))['version'], json.load(open('.claude-plugin/marketplace.json'))['plugins'][0]['version'])"
python3 bin/roadmap-selftest.py && python3 hooks/test_roadmap_cadence.py
```

Expected: both manifests print `0.2.0 0.2.0`; both suites print `ok`. The decoupling scan inside the selftest is what proves the new prose names no coupled workspace string, so a passing selftest covers the README and CHANGELOG too.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md .gitignore .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs(roadmap): where roadmap.toml goes, how roadmap resolves, what bd it needs (github-kkq4a)

M10: the README said 'run roadmap init' without saying that bare roadmap
resolves only inside a Claude Code session (PATH carries the plugin's bin
because the harness injects it), without showing /roadmap init, and without
saying WHERE roadmap.toml is written -- only roadmap.example.toml's first
comment did. All three are now stated, with the explicit-path form for a
shell outside a session.

M11: no bd minimum was stated anywhere. The README now names the exact
surface consumed -- two bd list reads and seven row fields -- and states
'verified against bd 1.2.2, no lower bound tested' rather than inventing a
floor that was never exercised.

Adds CHANGELOG.md (the repo had none) with 0.1.0-0.1.2 reconstructed from the
git log, .gitignore for .roadmap-state.json, and the 0.2.0 bump in both
manifests.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Deferred, filed, not in this plan

- **`github-aci1y`** — `load_issues()` reads only `--status=open` and
  `--status=closed`; `bd`'s filter is exact, so `in_progress`, `blocked` and
  `deferred` rows are invisible to the board (57 on the reference workspace).
  Found while verifying this issue's premises. Do not fix it here.
