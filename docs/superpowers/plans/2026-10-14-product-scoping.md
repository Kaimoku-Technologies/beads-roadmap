# Product Scoping on a Shared bd Board — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a `bd` database shared by several products, a board that opts in with `scoped = true` lists only the hotfix and unscheduled rows it owns and counts only its own closes in throughput; a board that does not opt in renders byte-identically to today and acts as the catch-all for unowned rows.

**Architecture:** One new predicate, `is_owned(issue, byid, cfg)` — own release/backlog label, else nearest labelled ancestor (via `parent` or dotted id, through open and closed rows), else a configured title or id prefix — consulted by `build_model` (unscheduled, hotfix) and `compute_throughput` (the `human` denominator) only when the config says `scoped`. Three optional config keys, one header suffix, one JSON key. No hook change.

**Tech Stack:** Python 3.11 (stdlib only). Tests are the hand-rolled assertion suite `bin/roadmap-selftest.py`; `hooks/test_roadmap_cadence.py` is run as a regression gate but not edited.

**Spec:** `docs/superpowers/specs/2026-10-14-product-scoping-design.md` — read its *Premise verification*, *Decision* and *Catch-all* sections before Task 1.

## Global Constraints

- **Python 3.11.16**, pinned in `.mise.toml`. Standard library only. CI runs both suites on 3.11, 3.12 and 3.13.
- **Two suites, run both, every task:** `python3 bin/roadmap-selftest.py` and `python3 hooks/test_roadmap_cadence.py`. Each prints `ok` or `FAIL (n)` plus the failing labels, exiting 1.
- **Assertion helpers differ between the suites:** `bin/roadmap-selftest.py` has `check(label, got, want)`; the hook suite has `check(label, cond)`. Only the first is touched here.
- **Every new assertion needs both directions.** Pair each must-hit with a must-miss control; where a test proves a row is *dropped*, prove the same row is *present* on the unscoped path, or the whole feature could be a no-op filter that drops everything.
- **No shipped file may name the origin workspace.** The decoupling scan at the end of the selftest walks `.py/.md/.json/.toml/.yml` files, lowercased, for three coupled strings. Fixtures use `acme-app` (own) and `other-app` (foreign). Commit messages are not scanned, but keep product names generic there too.
- **`github-*` ids in comments are deliberate provenance.** Cite `github-bjxle` in comments explaining code added by this plan.
- The test module is loaded as `rm`. Fixture helpers exist: `issue(**kw)` (defaults: id `github-test`, type `task`, P3, open, `updated_at` 2026-09-21), `tagged(v, **kw)` (appends `release:acme-app-<v>`), `closed_at(day, **kw)`, `write_cfg(text)` → `(dir, path)`, `GOOD` (a valid TOML body), `check_type_rejected(label, toml_text, key)`.
- **Config swapping pattern** (from the horizon tests at the end of the suite): `_saved_cfg = rm.CONFIG; rm.configure(dict(_saved_cfg, …)); …; rm.configure(_saved_cfg)`. Always restore; a leaked config fails unrelated assertions later in the file with misleading labels.
- **`TEST_CFG` has no `scoped` key, on purpose.** Every read in `bin/roadmap` must be `cfg.get('scoped')` and `cfg.get('claim_…') or ()`. A `cfg['scoped']` anywhere breaks the existing suite and `probe_layout`'s hand-built config.
- **`str.startswith` takes a tuple, never a str** — the `auto_label_prefixes` trap. The loader returns tuples; helpers default with `or ()`.
- **Commit before every mutation drill.** The drill ends in `git checkout -- bin/roadmap`, which discards every uncommitted change in that file.
- **Live runs never touch a real state file or a real config.** Use `--state <scratch path>` and `ROADMAP_CONFIG=<scratch toml>` (absolute `workspace` and `tag_repo` inside it — relative paths resolve against the scratch file's directory). Fix `--today 2026-10-14` on every run so windows do not move between the two binaries being compared.
- Work in the worktree on branch `feat/product-scoping`. `bd` commands run from the workspace root (the directory holding the shared `.beads/`), never from the worktree.

---

### Task 1: Config layer — `scoped`, `claim_title_prefixes`, `claim_id_prefixes`

**Files:**
- Modify: `bin/roadmap` — `CONFIG_KEYS` (`:85-86`); `load_config` after the `horizon` block (`:186`) and its return dict (`:208-218`)
- Test: `bin/roadmap-selftest.py` — after the `check_type_rejected('horizon negative', …)` line near the end, before `if FAILURES:`

**Interfaces:**
- Produces: `load_config(...)` returns three new keys — `'scoped': bool` (default `False`), `'claim_title_prefixes': tuple` and `'claim_id_prefixes': tuple` (default `()`). Nothing else in the dict changes.

- [ ] **Step 1: Write the failing tests**

```python
# --- github-bjxle: scoped boards -- the config surface ---------------------
# Three OPTIONAL keys. Absent, a board is the CATCH-ALL and renders exactly as
# before; present, each is validated by name and type like horizon. The empty
# string is refused because '' is a prefix of EVERY title and id -- one stray
# "" would claim the whole board and silently un-scope it.
_sd, _sp = write_cfg(GOOD)
_scfg = rm.load_config(_sp)
check('scoped defaults to False', _scfg['scoped'], False)
check('claim_title_prefixes defaults to an empty tuple', _scfg['claim_title_prefixes'], ())
check('claim_id_prefixes defaults to an empty tuple', _scfg['claim_id_prefixes'], ())
_sd, _sp = write_cfg(GOOD + 'scoped = true\n')
check('scoped alone loads (labels-and-ancestry-only scope)', rm.load_config(_sp)['scoped'], True)
_sd, _sp = write_cfg(GOOD + 'scoped = true\nclaim_title_prefixes = ["acme-app:"]\n'
                     'claim_id_prefixes = ["acme-"]\n')
_scfg = rm.load_config(_sp)
check('claim_title_prefixes loads as a tuple', _scfg['claim_title_prefixes'], ('acme-app:',))
check('claim_id_prefixes loads as a tuple', _scfg['claim_id_prefixes'], ('acme-',))
check_type_rejected('scoped wrong type (string)', GOOD + 'scoped = "true"\n', 'scoped')
check_type_rejected('scoped wrong type (int)', GOOD + 'scoped = 1\n', 'scoped')
check_type_rejected('claim_title_prefixes bare string',
                    GOOD + 'scoped = true\nclaim_title_prefixes = "acme-app:"\n',
                    'claim_title_prefixes')
check_type_rejected('claim_id_prefixes non-string element',
                    GOOD + 'scoped = true\nclaim_id_prefixes = [1]\n', 'claim_id_prefixes')
check_type_rejected('an empty claim prefix is refused (it would claim every row)',
                    GOOD + 'scoped = true\nclaim_title_prefixes = [""]\n',
                    'claim_title_prefixes')
check_type_rejected('claims without scoped = true are refused',
                    GOOD + 'claim_title_prefixes = ["acme-app:"]\n', 'scoped')
check_type_rejected('claims with scoped = false are refused',
                    GOOD + 'scoped = false\nclaim_id_prefixes = ["acme-"]\n', 'scoped')
```

- [ ] **Step 2: Run the suite; the new assertions must fail**

Run: `python3 bin/roadmap-selftest.py`
Expected: `FAIL (n)` — the three defaults fail with `KeyError`-shaped or `got None` results and the valid-config loads fail; the `check_type_rejected` arms fail because `load_config` currently raises `unknown key(s): scoped` (the message names the key, so some of those may pass by accident — note which, so Step 4 proves the *right* refusal fires). If the whole suite aborts with a traceback before printing, the `KeyError` on `_scfg['scoped']` is the cause; that is still RED.

- [ ] **Step 3: Implement**

`CONFIG_KEYS`:

```python
CONFIG_KEYS = ('workspace', 'tag_repo', 'release_namespace',
               'convention_start', 'auto_label_prefixes', 'horizon',
               'scoped', 'claim_title_prefixes', 'claim_id_prefixes')
```

After the `horizon` validation block in `load_config`:

```python
    # scoped (github-bjxle): opt-in. Absent or false, this board is the
    # CATCH-ALL on a shared bd database and renders exactly as before. bool
    # only -- `scoped = 1` or `"true"` is refused by name, like horizon.
    scoped = raw.get('scoped', False)
    if not isinstance(scoped, bool):
        raise RoadmapUnavailable('%s: scoped must be true or false, got %r'
                                 % (path, scoped))
    claims = {}
    for k in ('claim_title_prefixes', 'claim_id_prefixes'):
        val = raw.get(k, [])
        # Same trap as auto_label_prefixes: str.startswith() accepts a tuple,
        # so a bare string would decompose into one-character prefixes.
        if (isinstance(val, str) or not isinstance(val, list)
                or not all(isinstance(x, str) for x in val)):
            raise RoadmapUnavailable('%s: %s must be a list of strings, got %r'
                                     % (path, k, val))
        # '' is a prefix of EVERY title and id. One stray "" would claim the
        # whole board and silently un-scope it -- the clean-wrong signal.
        if any(x == '' for x in val):
            raise RoadmapUnavailable('%s: %s contains an empty string, which '
                                     'would claim every row' % (path, k))
        # A rule with no switch is a likely mistake; refuse rather than infer.
        if val and not scoped:
            raise RoadmapUnavailable('%s: %s is set but scoped is not true -- '
                                     'set scoped = true or remove it' % (path, k))
        claims[k] = tuple(val)
```

Return dict, after `'horizon': horizon,`:

```python
            'scoped': scoped,
            'claim_title_prefixes': claims['claim_title_prefixes'],
            'claim_id_prefixes': claims['claim_id_prefixes'],
```

- [ ] **Step 4: Run both suites — `ok` from both**

Also confirm the refusal messages are the *new* ones, not the unknown-key one: `python3 - <<'PY'` loading the module and calling `load_config` on `GOOD + 'claim_title_prefixes = ["x"]\n'` must raise a message containing `scoped is not true`.

- [ ] **Step 5: Commit**

`git add bin/roadmap bin/roadmap-selftest.py` · message: `feat(roadmap): scoped, claim_title_prefixes and claim_id_prefixes config keys (github-bjxle)` — body: the keys are optional and validated by name; absent means catch-all; end with the attribution line from your session's system reminder.

---

### Task 2: Ownership helpers — `ownership_index`, `_parent_id`, `owner_namespaces`, `is_owned`

**Files:**
- Modify: `bin/roadmap` — new functions after `is_deferred` (`:411-423`), before `build_model`
- Test: `bin/roadmap-selftest.py` — a new section after the backlog/horizon section (before `if FAILURES:`), which also defines the two-namespace fixture Tasks 3–5 reuse

**Interfaces:**
- `ownership_index(open_issues, closed_issues) -> dict` id → row over both reads.
- `_parent_id(iid, row) -> str | None` — `row['parent']`, else the dotted parent of `iid`, else `None`. Must work with `row=None`.
- `owner_namespaces(issue, byid) -> set` — the row's own release/backlog namespaces, else those of the **nearest** ancestor carrying any, else `set()`.
- `is_owned(issue, byid, cfg=None) -> bool`.

**Why nearest, and why closed rows are in the index:** a sub-epic relabelled to another product takes its subtree with it; a shipped (closed) epic's unlabelled children are still its product's. Measured 2026-10-14 over 7,976 rows: 3,178 dotted ids, 3,204 `parent` fields, 0 disagreements, 4 dotted ids with no `parent` — the same two encodings `descends_from()` unions.

- [ ] **Step 1: Write the failing tests**

```python
# --- github-bjxle: who OWNS an unlabelled row -------------------------------
# bd rows carry no repo field. On a shared database an unlabelled row is owned
# by this namespace when (1) it carries this namespace's release/backlog label,
# (2) its NEAREST labelled ancestor does, or (3) a configured title/id prefix
# claims it. Two namespaces: acme-app (ours) and other-app (foreign).
OWN_OPEN = [
    tagged('v0.18.0', id='own-epic', issue_type='epic', priority=2, title='acme epic'),
    issue(id='own-child', issue_type='feature', parent='own-epic', title='child of acme epic'),
    issue(id='own-epic.7', issue_type='feature', title='dotted child, no parent field'),
    issue(id='mid', issue_type='task', parent='own-epic', title='unlabelled middle row'),
    issue(id='grand', issue_type='feature', parent='mid', title='two hops to acme epic'),
    issue(id='old-child', issue_type='feature', parent='old-epic', title='child of a CLOSED acme epic'),
    issue(id='by-title', issue_type='feature', title='acme-app: claimed by title'),
    issue(id='acme-77', issue_type='feature', title='claimed by id prefix'),
    issue(id='own-bl', issue_type='feature', priority=2,
          labels=['security', 'release:acme-app-backlog'], title='own backlog security row'),
    issue(id='own-p1', issue_type='bug', priority=1, parent='own-epic', title='P1 bug under acme epic'),
    issue(id='other-epic', issue_type='epic', labels=['release:other-app-v1.0.0'], title='foreign epic'),
    issue(id='other-child', issue_type='feature', parent='other-epic', title='child of foreign epic'),
    issue(id='sub-foreign', issue_type='epic', parent='own-epic',
          labels=['release:other-app-backlog'], title='foreign sub-epic under acme epic'),
    issue(id='sub-foreign-child', issue_type='feature', parent='sub-foreign',
          title='nearest labelled ancestor is foreign'),
    issue(id='orphan', issue_type='feature', title='bin/tool: nobody claims this'),
    issue(id='orphan-p1', issue_type='bug', priority=1, title='unlabelled P1 bug, no parent'),
    # the github-5yqbl shape: P2 security FEATURE, foreign backlog label, no parent
    issue(id='foreign-bl', issue_type='feature', priority=2,
          labels=['security', 'release:other-app-backlog'], title='foreign backlog security row'),
]
OWN_CLOSED = [tagged('v0.15.0', id='old-epic', issue_type='epic', status='closed',
                     title='closed acme epic')]
OWN_IDX = rm.ownership_index(OWN_OPEN, OWN_CLOSED)
SCOPED_CFG = dict(TEST_CFG, scoped=True, claim_title_prefixes=('acme-app:',),
                  claim_id_prefixes=('acme-',))
ANCESTRY_ONLY_CFG = dict(TEST_CFG, scoped=True)


def _owned(iid, cfg=SCOPED_CFG):
    return rm.is_owned(OWN_IDX[iid], OWN_IDX, cfg)


check('_parent_id: parent field wins', rm._parent_id('x.1', {'parent': 'p'}), 'p')
check('_parent_id: dotted fallback when parent absent', rm._parent_id('own-epic.7', {}), 'own-epic')
check('_parent_id: works on a bare id with no row', rm._parent_id('a.b.c', None), 'a.b')
check('_parent_id: a flat id has no parent', rm._parent_id('github-abc', None), None)

check('owned: child via parent (must-hit)', _owned('own-child'), True)
check('owned: dotted child with no parent field (must-hit)', _owned('own-epic.7'), True)
check('owned: two hops through an unlabelled middle row (must-hit)', _owned('grand'), True)
check('owned: child of a CLOSED labelled epic (must-hit)', _owned('old-child'), True)
check('owned: own-namespace backlog label, zero hops (must-hit)', _owned('own-bl'), True)
check('owned: title claim (must-hit)', _owned('by-title'), True)
check('owned: id-prefix claim (must-hit)', _owned('acme-77'), True)
check('not owned: child of a foreign epic (must-miss)', _owned('other-child'), False)
check('not owned: NEAREST labelled ancestor is foreign, even under an own epic (must-miss)',
      _owned('sub-foreign-child'), False)
check('not owned: orphan (must-miss)', _owned('orphan'), False)
check('not owned: foreign backlog security row -- the github-5yqbl shape (must-miss)',
      _owned('foreign-bl'), False)
check('owner_namespaces: nearest foreign ancestor reported',
      rm.owner_namespaces(OWN_IDX['sub-foreign-child'], OWN_IDX), {'other-app'})
check('owner_namespaces: orphan has none', rm.owner_namespaces(OWN_IDX['orphan'], OWN_IDX), set())
# Which ARM matched: with no claims configured the title/id rows become misses
# while ancestry still hits. Without this, a bug that owned everything would
# pass every must-hit above.
check('claims off: title row is no longer owned', _owned('by-title', ANCESTRY_ONLY_CFG), False)
check('claims off: id-prefix row is no longer owned', _owned('acme-77', ANCESTRY_ONLY_CFG), False)
check('claims off: ancestry row still owned (control)', _owned('own-child', ANCESTRY_ONLY_CFG), True)
```

- [ ] **Step 2: Run the suite; expected: `AttributeError` on `rm.ownership_index` (RED)**

- [ ] **Step 3: Implement** (after `is_deferred`)

```python
def ownership_index(open_issues, closed_issues):
    """id -> row over BOTH reads (github-bjxle). Ownership walks through
    CLOSED epics: a shipped epic's unlabelled children are still its
    product's, and a closed child's ancestor may itself be closed."""
    return {i['id']: i for i in open_issues + closed_issues if i.get('id')}


def _parent_id(iid, row):
    """bd's `parent`, else the dotted parent of the id itself -- the two
    encodings descends_from() unions (0 disagreements, 4 dotted-without-parent
    rows measured 2026-10-14). Works on a bare id when the row is missing, so
    a gap in the chain does not end the walk."""
    p = (row or {}).get('parent')
    if p:
        return p
    return iid.rsplit('.', 1)[0] if '.' in iid else None


def _label_namespaces(issue):
    """Namespaces of every release AND backlog label on the row."""
    out = set()
    for l in labels_of(issue):
        parsed = version_of_label(l)
        if parsed:
            out.add(parsed[0])
    out.update(backlog_namespaces(issue))
    return out


def owner_namespaces(issue, byid):
    """The row's own label namespaces, else those of the NEAREST ancestor
    carrying any, else an empty set (github-bjxle). Nearest wins so a
    sub-epic relabelled to another product takes its subtree with it."""
    own = _label_namespaces(issue)
    if own:
        return own
    seen = set()
    cur = _parent_id(issue.get('id') or '', issue)
    while cur and cur not in seen:
        seen.add(cur)
        row = byid.get(cur)
        if row:
            ns = _label_namespaces(row)
            if ns:
                return ns
        cur = _parent_id(cur, row)
    return set()


def is_owned(issue, byid, cfg=None):
    """Does THIS board own an unlabelled row? Own/ancestor label in the
    configured namespace, or a configured title/id prefix (github-bjxle).
    Consulted only when cfg['scoped'] -- see build_model. Tuples, never a
    str: str.startswith() decomposes a str into one-character prefixes."""
    cfg = cfg or CONFIG
    if cfg['release_namespace'] in owner_namespaces(issue, byid):
        return True
    title_prefixes = tuple(cfg.get('claim_title_prefixes') or ())
    if title_prefixes and (issue.get('title') or '').startswith(title_prefixes):
        return True
    id_prefixes = tuple(cfg.get('claim_id_prefixes') or ())
    return bool(id_prefixes) and (issue.get('id') or '').startswith(id_prefixes)
```

- [ ] **Step 4: Run both suites — `ok`**

- [ ] **Step 5: Commit** — `feat(roadmap): is_owned -- own label, nearest labelled ancestor, configured claims (github-bjxle)`.

---

### Task 3: `build_model` — scope the unscheduled list and the hotfix queue

**Files:**
- Modify: `bin/roadmap` — `build_model` (`:426-507`): unscheduled (`:474-481`), hotfix (`:498-501`), return dict (`:503-507`)
- Test: `bin/roadmap-selftest.py` — continue the Task 2 section

**Interfaces:**
- `build_model` signature unchanged. Return dict gains `'scoped': bool`. When scoped, `unscheduled` and `hotfix` contain only owned rows. `versions`, `backlog`, `planned`, `in_flight` are unaffected.

- [ ] **Step 1: Write the failing tests**

```python
# build_model under a scoped config vs the SAME fixture under TEST_CFG. The
# unscoped arm is today's behaviour and is the catch-all's job: it must keep
# listing exactly the rows the scoped arm drops.
_saved_cfg = rm.CONFIG
rm.configure(SCOPED_CFG)
SC_M = rm.build_model(OWN_OPEN, OWN_CLOSED, [(0, 15, 0)])
rm.configure(_saved_cfg)
UN_M = rm.build_model(OWN_OPEN, OWN_CLOSED, [(0, 15, 0)])
_sc_uns = [i['id'] for i in SC_M['unscheduled']]
_un_uns = [i['id'] for i in UN_M['unscheduled']]
_sc_hot = [i['id'] for i in SC_M['hotfix']]
_un_hot = [i['id'] for i in UN_M['hotfix']]

check('scoped unscheduled keeps every owned row (must-hit)',
      sorted(set(_sc_uns) & {'own-child', 'own-epic.7', 'grand', 'old-child', 'by-title', 'acme-77'}),
      ['acme-77', 'by-title', 'grand', 'old-child', 'own-child', 'own-epic.7'])
check('scoped unscheduled drops the orphan (must-miss)', 'orphan' in _sc_uns, False)
check('scoped unscheduled drops a foreign epic\'s child', 'other-child' in _sc_uns, False)
check('scoped unscheduled drops a row whose nearest labelled ancestor is foreign',
      'sub-foreign-child' in _sc_uns, False)
check('unscoped unscheduled still lists the orphan (control: today\'s behaviour)',
      'orphan' in _un_uns, True)
check('unscoped unscheduled still lists the foreign epic\'s child (control)',
      'other-child' in _un_uns, True)

check('scoped hotfix keeps an owned P1 bug (must-hit)', 'own-p1' in _sc_hot, True)
check('scoped hotfix keeps an own-namespace backlogged security row (must-hit)',
      'own-bl' in _sc_hot, True)
check('scoped hotfix drops a foreign backlogged security row (the github-5yqbl shape)',
      'foreign-bl' in _sc_hot, False)
check('scoped hotfix drops an UNOWNED P1 bug -- the catch-all board shows it',
      'orphan-p1' in _sc_hot, False)
check('unscoped hotfix lists the unowned P1 bug (control)', 'orphan-p1' in _un_hot, True)
check('unscoped hotfix lists the foreign backlogged row (control)', 'foreign-bl' in _un_hot, True)

check('model records scoped = True', SC_M['scoped'], True)
check('model records scoped = False under a config with no key', UN_M['scoped'], False)
check('scoping leaves the versions map alone',
      sorted(SC_M['versions']), sorted(UN_M['versions']))
check('scoping leaves the backlog alone',
      [i['id'] for i in SC_M['backlog']], [i['id'] for i in UN_M['backlog']])
```

- [ ] **Step 2: Run the suite; expected failures:** the four `drops …` checks (`got True, want False`) and the two `model records …` checks (`KeyError: 'scoped'` — if the run aborts there, move those two checks last within this block so the drop/keep failures print). Every `(control)` and `(must-hit)` arm must already pass.

- [ ] **Step 3: Implement**

At the top of `build_model`, after `cut = …`:

```python
    # Ownership (github-bjxle). Only a board that opted in with `scoped`
    # filters anything; a board without the key is the CATCH-ALL on a shared
    # database and renders exactly as before, so an unowned P0 bug is always
    # visible on at least one board. Counts, backlog and plan are untouched --
    # they are already namespace-filtered or ancestry-walked.
    scoped = bool((CONFIG or {}).get('scoped'))
    byid = ownership_index(open_issues, closed_issues) if scoped else None

    def owned(i):
        return (not scoped) or is_owned(i, byid)
```

Add `and owned(i)` as the last predicate of the `unscheduled` and `hotfix` comprehensions. Add `'scoped': scoped,` to the return dict. Amend the comment above `hotfix` so it reads, after the existing sentence: `On a scoped board the queue holds only OWNED rows; the unscoped (catch-all) board still holds every unversioned one.`

- [ ] **Step 4: Run both suites — `ok`**

- [ ] **Step 5: Commit** — `fix(roadmap): scoped boards list only owned hotfix and unscheduled rows (github-bjxle)`.

- [ ] **Step 6: Mutation drill** (after the commit)

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path('bin/roadmap'); s = p.read_text(); orig = s
s = s.replace("if is_hotfix(i) and not release_labels(i) and not is_deferred(i) and owned(i)),",
              "if is_hotfix(i) and not release_labels(i) and not is_deferred(i)),")
assert s != orig, "mutation did not apply -- re-check the hotfix comprehension text by hand"
p.write_text(s)
PY
python3 bin/roadmap-selftest.py > /tmp/mut.out 2>&1; echo "EXIT=$?"
grep -c 'scoped hotfix drops' /tmp/mut.out
git checkout -- bin/roadmap
python3 bin/roadmap-selftest.py
```

Expected: `EXIT=1` and the two `scoped hotfix drops …` labels in the output; then `ok` after the checkout. If the mutated run passes, the guard is not real — stop and report.

---

### Task 4: `compute_throughput` — scope the denominator

**Files:**
- Modify: `bin/roadmap` — `compute_throughput` (`:925-988`): the `human` list at `:949`, the docstring
- Test: `bin/roadmap-selftest.py` — continue the section

**Interfaces:**
- Signature unchanged. When `(cfg or {}).get('scoped')`, `closed_*d`, `rows14` and `on_plan_share_14d` count only owned closes. `in_release_*d`, `tags_*d`, `curve` unchanged.

**Why the existing M9 tests cannot detect this:** `TP_FOREIGN` proves the numerator ignores a foreign label; nothing in the suite has ever made the *denominator* ignore anything but auto-filed rows, because under `TEST_CFG` it must not.

- [ ] **Step 1: Write the failing tests**

```python
# Throughput: the DENOMINATOR follows ownership on a scoped board. The
# numerator was scoped by github-kkq4a M9; leaving the denominator unscoped
# collapsed the on-plan share on every shared-database board (measured 5%, 7%
# and 8% false OFF-PLAN on three boards, 2026-10-14).
TP_SC_CLOSED = OWN_CLOSED + [            # old-epic: own label, closed 2026-09-21
    closed_at('2026-09-20', id='c-own', labels=['release:acme-app-v0.15.0']),
    closed_at('2026-09-20', id='c-anc', parent='old-epic'),           # unlabelled child of a CLOSED own epic
    closed_at('2026-09-20', id='c-title', title='acme-app: closed by title'),
    closed_at('2026-09-20', id='c-foreign', labels=['release:other-app-v1.0.0']),
    closed_at('2026-09-20', id='c-orphan', title='nobody\'s close'),
]
TP_SC = rm.compute_throughput([], TP_SC_CLOSED, [], '2026-09-21', None,
                              convention_start='2026-09-01', cfg=SCOPED_CFG)
TP_UN = rm.compute_throughput([], TP_SC_CLOSED, [], '2026-09-21', None,
                              convention_start='2026-09-01', cfg=TEST_CFG)
check('scoped closed_7d counts only owned closes (must-miss on foreign and orphan)',
      TP_SC['closed_7d'], 4)
check('unscoped closed_7d counts every human close (control)', TP_UN['closed_7d'], 6)
check('in_release_7d is unchanged by scoping', (TP_SC['in_release_7d'], TP_UN['in_release_7d']), (2, 2))
check('scoped on-plan share is 2 of 4', TP_SC['on_plan_share_14d'], 0.5)
check('unscoped on-plan share is 2 of 6 (control)', round(TP_UN['on_plan_share_14d'], 3), 0.333)
```

If `closed_at` sets a `status` or `updated_at` that conflicts with `tagged(..., status='closed')` for `old-epic`, check its definition (`grep -n 'def closed_at' bin/roadmap-selftest.py`) and adjust the expected counts rather than the fixture semantics — the point is that an **own-labelled closed epic** and an **unlabelled child of it** are both owned.

- [ ] **Step 2: Run the suite; expected:** `scoped closed_7d …: got 6, want 4` and `scoped on-plan share …: got 0.333…, want 0.5`. The three controls must pass.

- [ ] **Step 3: Implement**

Replace `:949`:

```python
    # On a scoped board the denominator follows ownership (github-bjxle):
    # M9 scoped the numerator, and a scoped numerator over an unscoped
    # denominator collapsed the on-plan share on every shared-database board.
    scoped = bool((cfg or {}).get('scoped'))
    byid = ownership_index(open_issues, closed_issues) if scoped else None
    human = [i for i in closed_issues
             if is_human_authored(i, cfg) and (not scoped or is_owned(i, byid, cfg))]
```

Append to the docstring, after the M9 paragraph:

```
    On a scoped board (github-bjxle) `human` is further limited to closes this
    board OWNS -- is_owned(): own label, nearest labelled ancestor, configured
    claim -- so closed_*d and on_plan_share_14d measure this product. The
    unscoped board is the catch-all and keeps counting every human close.
```

- [ ] **Step 4: Run both suites — `ok`**

- [ ] **Step 5: Commit** — `fix(roadmap): scoped boards count only owned closes in throughput (github-bjxle)`.

- [ ] **Step 6: Mutation drill** — replace `and (not scoped or is_owned(i, byid, cfg))]` with `]` using the same pattern as Task 3 Step 6; expected `EXIT=1` with `scoped closed_7d …` and `scoped on-plan share …` failing; `git checkout -- bin/roadmap`; re-run to `ok`.

---

### Task 5: Render — header suffix and JSON key

**Files:**
- Modify: `bin/roadmap` — `render_board` header (`:1048-1049`), `render_json` (`:1016-1042`)
- Test: `bin/roadmap-selftest.py` — continue the section

- [ ] **Step 1: Write the failing tests**

```python
# A scoped board SAYS so: a reader of its hotfix queue must know it is partial
# and that the catch-all board has the rest. An unscoped header is unchanged
# -- byte-identical output for every single-product install.
check('scoped board header carries the marker',
      rm.render_board(SC_M, []).splitlines()[0], 'ROADMAP · acme-app · cut v0.15.0 · scoped')
check('unscoped header is unchanged (must-miss)',
      rm.render_board(UN_M, []).splitlines()[0], 'ROADMAP · acme-app · cut v0.15.0')
check('the original fixture\'s header is byte-identical',
      rm.render_board(M, []).splitlines()[0], 'ROADMAP · acme-app · cut v0.15.0')
check('json: scoped true', json.loads(rm.render_json(SC_M, []))['scoped'], True)
check('json: scoped false on a board with no key', json.loads(rm.render_json(UN_M, []))['scoped'], False)
```

- [ ] **Step 2: Run the suite; expected:** the first and the two `json:` checks fail.

- [ ] **Step 3: Implement**

`render_board`:

```python
    lines = ['ROADMAP · %s · cut %s%s'
             % (cfg['release_namespace'],
                _fmt_v(model['cut']) if model['cut'] else '(none)',
                ' · scoped' if model.get('scoped') else '')]
```

`render_json`: add `'scoped': bool(model.get('scoped')),` after `'horizon': …`.

- [ ] **Step 4: Run both suites — `ok`**

- [ ] **Step 5: Commit** — `feat(roadmap): scoped boards are marked in the header and in --json (github-bjxle)`.

---

### Task 6: Documentation

**Files:**
- Modify: `README.md`, `roadmap.example.toml`, `docs/DESIGN.md`, `CHANGELOG.md`
- Optional: `commands/roadmap.md`, `skills/roadmap/SKILL.md`

No code; run the selftest anyway at the end — the decoupling scan walks every `.md` and `.toml`.

- [ ] **Step 1: `README.md`**

1. **"Before you start"** — add item 8 after the `horizon` item:
   > 8. **Optional: `scoped = true` in `roadmap.toml`, when several products share one `bd` board.** The board then lists only the hotfix and unscheduled rows this product *owns* and counts only its own closes. Leave exactly one board per shared `bd` database unscoped: it is the catch-all that shows every unlabelled row. See [Several products, one `bd` board](#several-products-one-bd-board).
2. **Glossary** — three rows:
   `| **owned** | An unlabelled row this board claims: it carries this namespace's release or backlog label, its nearest labelled ancestor epic does, or a configured title/id prefix matches. |`
   `| **scoped board** | A board with `scoped = true`: hotfix queue, unscheduled list and throughput cover owned rows only. Its header ends in `· scoped`. |`
   `| **catch-all board** | A board without `scoped`: shows every unlabelled row, as a single-product board always has. Keep exactly one per shared `bd` database. |`
3. **"Reading the board"** — append to the HOTFIX QUEUE bullet: *On a scoped board, only rows this product owns; the catch-all board has the rest.* Same clause on UNSCHEDULED. THROUGHPUT: *On a scoped board `closed` counts only this product's closes.*
4. **New H3 "Several products, one `bd` board"** after "Common tasks", before "The SessionStart hook". Content, in this order: the symptom (every board shows every other product's untriaged rows; the on-plan share collapses); the config block from the spec's *Config surface*; the three ownership arms as a short list; the rule *leave exactly one board unscoped — the product the database was created for — so an unowned P0 bug is always on that board*; the caveat *if every board is scoped an unowned row is on no board, and the tool cannot detect that from one `roadmap.toml`*; the version note *a `roadmap` older than 0.7.0 refuses these keys by name and prints `roadmap: unavailable: … unknown key(s): scoped`; update the install before adding them*.
5. **"Script against it"** — one sentence: `--json` carries `"scoped"`, true when the board is scoped.

- [ ] **Step 2: `roadmap.example.toml`** — append after the `# horizon = 3` block the commented block from the spec's *Config surface* (keys commented out, as `horizon` is).

- [ ] **Step 3: `docs/DESIGN.md`** — new H2 **"Several products, one board"** after "Fail-open, always": ownership is derived at render time like everything else (nothing is written to `bd`); the three arms and why nearest-ancestor and closed rows; why it is opt-in (a derived "scoped" would change every mixed workspace on upgrade and the single-product render would stop being identical; a derived title prefix is wrong on the one board where it matters most) and why `init` never writes it; the catch-all and the reason one config cannot detect all-scoped (a scoped board cannot tell "unowned by anyone" from "owned by the catch-all by convention", so a count of "not mine" would reintroduce the leak in count form); where detection belongs (`github-7jn0v`).

- [ ] **Step 4: `CHANGELOG.md`** — under `## [Unreleased]`:

```markdown
### Added

- **Scoped boards for a shared `bd` database: `scoped = true`, `claim_title_prefixes`,
  `claim_id_prefixes` in `roadmap.toml`.** A scoped board lists only the hotfix and
  unscheduled rows it owns — rows labelled for its namespace, rows whose nearest
  labelled ancestor epic is, and rows matched by the claim prefixes — and counts
  only its own closes in THROUGHPUT. Its header ends in `· scoped` and `--json`
  carries `scoped`. A board without the key is unchanged and acts as the catch-all,
  so an unowned severe row is always visible on one board. Keys are validated by
  name; an older `roadmap` refuses them.

### Fixed

- **On a shared `bd` database, every board showed every other product's unlabelled
  work and a false OFF-PLAN.** The hotfix queue and unscheduled list had no
  ownership test, and throughput's denominator counted every close in the database
  while its numerator counted only this product's (0.2.0, M9), so three boards
  reported 5–8% on-plan shares that were really 59–100%. Fixed for boards that opt
  in with `scoped = true`; single-product boards render exactly as before.
```

- [ ] **Step 5 (optional):** `commands/roadmap.md` and `skills/roadmap/SKILL.md` — add "(on a scoped board, this product's rows)" to the `hotfix` / `unscheduled` lines.

- [ ] **Step 6: Run both suites — `ok`** (the decoupling scan must stay clean). **Commit** — `docs: scoped boards on a shared bd database (github-bjxle)`.

---

### Task 7: Live verification on the reference workspace — no real config touched

**Preconditions:** `bd` and `git` reachable; the worktree binary at `bin/roadmap`; the pre-change binary extracted from the merge base. Set `WS` to the directory holding the shared `.beads/` (the root `roadmap.toml` lives there) and `S` to the session scratchpad. Brace every `${var}` that is followed by a colon — zsh reads `$rev:x` as a modifier.

- [ ] **Step 1: Binaries and scratch configs**

```bash
WT=<absolute path of this worktree>; NEW="$WT/bin/roadmap"
BASE=$(git -C "$WT" merge-base HEAD main); OLD="$S/roadmap-old"
git -C "$WT" show "${BASE}:bin/roadmap" > "$OLD"
```

`$S/site.toml` (absolute paths, copied from `$WS/kaimoku-website/roadmap.toml` plus the two new keys):

```toml
workspace = "<WS>"
tag_repo = "<WS>/kaimoku-website"
release_namespace = "kaimoku-website"
convention_start = "2026-09-23"
auto_label_prefixes = []
scoped = true
claim_title_prefixes = ["kaimoku-website:"]
```

`$S/br.toml`: same shape for `beads-roadmap` (`tag_repo = "<WS>/beads-roadmap"`, `convention_start = "2026-10-14"`, `horizon = 3`, `claim_title_prefixes = ["beads-roadmap:"]`). `$S/infra.toml`: `kaimoku-infra` (`tag_repo = "<WS>/kaimoku-infra"`, its `auto_label_prefixes`, `horizon = 3`, `claim_title_prefixes = ["kaimoku-infra:"]`, `claim_id_prefixes = ["homelab-"]`).

- [ ] **Step 2: Must-miss — the two acceptance boards**

```bash
ROADMAP_CONFIG="$S/site.toml" python3 "$NEW" --today 2026-10-14 --state "$S/st-site.json" > "$S/site.txt" 2>"$S/site.err"
ROADMAP_CONFIG="$S/br.toml"   python3 "$NEW" --today 2026-10-14 --state "$S/st-br.json"   > "$S/br.txt"   2>"$S/br.err"
grep -c 'github-5yqbl\|github-6ew5z\|github-p8e6s\|github-yxk4w\|github-8lox9\|github-g6vst\|OFF-PLAN' "$S/site.txt" "$S/br.txt"
head -1 "$S/site.txt" "$S/br.txt"
```

Expected: `0` hits in both files (a `grep -c` of `0` exits 1 — that is the pass here; an exit of 2 is an error, not a pass); headers `ROADMAP · kaimoku-website · cut v0.5.0 · scoped` and `ROADMAP · beads-roadmap · cut v0.6.0 · scoped`; `UNSCHEDULED  0 features/epics carry no version` in both; no HOTFIX QUEUE block in either; `beads-roadmap` THROUGHPUT 7d `2 closed · 2 in a release set` (expected from the 2026-10-14 dump; live counts drift as rows are updated). `--json` on the site config: `"on_plan_share_14d": 1.0` and `"scoped": true`; no condition with `"id": 3`.

- [ ] **Step 3: Must-hit — the same rows are still visible where they belong**

```bash
ROADMAP_CONFIG="$S/infra.toml" python3 "$NEW" --today 2026-10-14 --state "$S/st-infra.json" | grep -n 'scoped\|github-5yqbl'
ROADMAP_CONFIG="$WS/roadmap.toml" python3 "$NEW" --today 2026-10-14 --state "$S/st-root-new.json" | grep -c 'github-5yqbl\|github-6ew5z'
```

Expected: the scoped `kaimoku-infra` board still lists `github-5yqbl` in its HOTFIX QUEUE (owned via its own `release:kaimoku-infra-backlog` label) — severity was not hidden from the owning board; the root (unscoped) board still shows the row and the orphans (count ≥ 2).

Also diff the IN FLIGHT / PLANNED blocks of the site board scoped vs unscoped (same `--today`, a copy of `site.toml` without the two keys): identical — scoping touched nothing above the hotfix queue.

- [ ] **Step 4: Byte-identity of the unscoped root board**

```bash
cp "$S/st-root-new.json" "$S/st-root-old.json" 2>/dev/null || true
ROADMAP_CONFIG="$WS/roadmap.toml" python3 "$OLD" --today 2026-10-14 --state "$S/st-root-old.json" > "$S/root-old.txt" 2>/dev/null
ROADMAP_CONFIG="$WS/roadmap.toml" python3 "$NEW" --today 2026-10-14 --state "$S/st-root-new.json" > "$S/root-new.txt" 2>/dev/null
diff "$S/root-old.txt" "$S/root-new.txt"; echo "DIFF_EXIT=$?"
ROADMAP_CONFIG="$WS/roadmap.toml" python3 "$OLD" --json --today 2026-10-14 --state "$S/st-root-old.json" 2>/dev/null > "$S/root-old.json"
ROADMAP_CONFIG="$WS/roadmap.toml" python3 "$NEW" --json --today 2026-10-14 --state "$S/st-root-new.json" 2>/dev/null > "$S/root-new.json"
diff "$S/root-old.json" "$S/root-new.json"
```

Expected: `DIFF_EXIT=0` for the text board; the JSON diff is exactly one added line, `"scoped": false,`. If the text diff shows only THROUGHPUT counts, a `bd` write landed between the two runs — re-run both back-to-back. Any other difference is a regression; stop.

- [ ] **Step 5: Record the evidence** in the issue: `bd note github-bjxle "$(cat <<'EOF' … EOF)"` from `$WS` (quoted heredoc — backticks in prose are command substitution otherwise), pasting the grep counts, both headers, the `DIFF_EXIT=0`, and the one-line JSON diff.

---

### Task 8: Merge, push, and the gated config rollout

- [ ] **Step 1:** Full suites once more on the branch; `git -C <beads-roadmap checkout> remote -v` — `origin` is GitHub (`Kaimoku-Technologies/beads-roadmap`); merge `feat/product-scoping` into `main` and push `origin main`. CI runs both suites on 3.11–3.13.

- [ ] **Step 2: Do NOT bump the version.** `release:beads-roadmap-v0.7.0` carries two more issues; the release commit bumps `plugin.json` / `marketplace.json`.

- [ ] **Step 3: Config rollout — gated on the installed plugin being ≥ 0.7.0** (`roadmap --version`). A 0.6.0 binary refuses the keys by name and the board from those directories goes silent (fail-open, reason on stderr; the root hook is unaffected). Then:
   - `$WS/beads-roadmap/roadmap.toml` (gitignored, local): add `scoped = true` and `claim_title_prefixes = ["beads-roadmap:"]`.
   - `$WS/kaimoku-website/roadmap.toml` (tracked in that repo): same two lines plus the `kaimoku-website:` prefix; commit there under **that repo's** branch and push rules (see the workspace `CLAUDE.md` — its deploy branch is not `main`), and gitignore its `.roadmap-state.json` while there.
   - `kaimoku-infra` and `console` (`kaimoku-lens/roadmap.toml`): only if the user says so (spec, open question 1).
   Re-run `cd <dir> && roadmap` with the **installed** binary for each edited board and paste the header line and the empty HOTFIX/UNSCHEDULED evidence into the issue.

- [ ] **Step 4: Close** `github-bjxle` from `$WS` with the pasted evidence from Tasks 7 and 8; the acceptance text is: no foreign hotfix/unscheduled rows and no OFF-PLAN on the `beads-roadmap` and `kaimoku-website` boards; root board byte-identical; selftest covers the two-namespace fixture.

---

## Separable follow-ups (for the user to file; not created by this plan)

- `claim_labels` (owner-label arm) — 19 + 2 + 2 open rows carry a repo-style label today; add when the convention is adopted.
- Workspace-level detection of "every board scoped, orphan severe rows on no board" — belongs with the multi-product hook, `github-7jn0v`.
- `cmd_init`'s multi-namespace refusal text could point at `scoped` and the README section.
- `kaimoku-website`: gitignore `.roadmap-state.json` (untracked today).
- Unify the list-of-strings validator with `auto_label_prefixes`'.
