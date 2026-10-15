# Multi-board cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The catch-all `roadmap.toml` on a shared `bd` database can `boards = [...]` its sibling boards; the SessionStart hook (and `roadmap check`, which *is* the hook) then runs every listed board under its own `ROADMAP_CONFIG`, judges each on its own state file, and prints one combined report — the catch-all's block byte-identical to today, one headed block per listed board with something to say, and a line under the catch-all for every listed board that is missing, unreadable or a second catch-all. A board without the key produces byte-identical output, text and JSON apart from one added `workspace` key.

**Architecture:** One optional config key, validated and resolved in `load_config` (`boards` → a tuple of `{name, config_path, exists}`; refused with `scoped = true`). Two additive `--json` keys (`workspace` always, `boards` only when configured). The hook's single run becomes `board_report(payload, state, days) -> (prelude, body, stamp)` called once per board; listed boards run in a thread pool with every state read/write on the main thread; problem lines are one non-bypass pseudo-condition of the catch-all. No other surface changes — no `roadmap --all`, no text-board change, no walk below one level.

**Tech Stack:** Python 3.11 (stdlib only: `concurrent.futures`, `shlex`, `subprocess`, `json`). Tests are the two hand-rolled suites `bin/roadmap-selftest.py` and `hooks/test_roadmap_cadence.py`; **both are edited by this plan** (the first for config and payload, the second for hook behaviour).

**Spec:** `docs/superpowers/specs/2026-10-14-multi-board-cadence-design.md` — read *Premise verification* (the four *Corrected* items drive the task shapes), *Decision*, and the *Output — one emit* layout before Task 3.

Line numbers below are as of `a01b35a` (the 0.7.0 release commit); HEAD `6cc89b4` differs only by the spec document, so every code reference is current.

## Global Constraints

- **Python 3.11.16**, pinned in `.mise.toml`. Standard library only. CI (`.github/workflows/test.yml`) runs both suites on 3.11, 3.12 and 3.13 on every push.
- **Two suites, run both, every task:** `python3 bin/roadmap-selftest.py` and `python3 hooks/test_roadmap_cadence.py`. Each prints `ok` or `FAIL (n)` plus the failing labels, exiting 1.
- **Assertion helpers differ between the suites:** `bin/roadmap-selftest.py` has `check(label, got, want)`; the hook suite has `check(label, cond)`. Both are touched here — do not mix the two shapes.
- **Every new assertion needs both directions.** Pair each must-hit with a must-miss control, in one run where the spec says "both directions". A hook that always speaks and one that never speaks are byte-identical from outside.
- **No shipped file may name the origin workspace.** The decoupling scan (`bin/roadmap-selftest.py:2537-2636`) walks every tracked-or-unignored `.py/.md/.json/.toml/.yml` file, lowercased, for three coupled strings — **this plan file is itself scanned** (it lives under `docs/`). Fixtures, docs and this plan use `acme-app` (the catch-all), `other-app` and `third-app` (listed boards). Never a real product, host, user or absolute home path; the live-verification task says `$WS`, `$S`, `A` and `B`.
- **`github-*` ids in comments are deliberate provenance.** Cite `github-7jn0v` in comments explaining code added by this plan; the 0.7.0 code it extends is `github-bjxle`, the per-install state it relies on is `github-kkq4a`.
- The selftest module is loaded as `rm`. Fixture helpers exist: `issue(**kw)`, `write_cfg(text) -> (dir, path)` (`:1908`), `GOOD` (`:1918`, a valid TOML body with `workspace = "."` and `tag_repo = "."`), `check_type_rejected(label, toml_text, key)` (`:2014`, asserts the raise is `RoadmapUnavailable` *and* that `key` is a substring of the message — so `key` may be a message fragment), `_run_main(argv, open_issues=, closed_issues=, tag_dates=, raise_unavailable=, cfg=)` (`:1237`). **`_run_main` is redefined at `:2427` with signature `(argv)` for the `--version` arms and shadows the first for the rest of the file** — every new `_run_main(..., cfg=…)` call must sit **before `:2427`**. The hook suite has `fake_roadmap(payload, rc=0)`, `fake_roadmap_sleep(seconds, payload=None)`, `run_hook(roadmap_path, days='3', state=None, timeout='10', extra=()) -> (rc, stdout, state)` (always sets `ROADMAP_CADENCE_STATE`), the payload constants `BYPASS`, `THROTTLED`, `CLEAN`, `UNCONFIGURED`, `UNAVAILABLE_ORDINARY`, and `_record_argv_stub(capture_path)` (`:335`, whose output format existing arms index — leave it alone and add a sibling).
- **Config swapping pattern** (selftest): `_saved_cfg = rm.CONFIG; rm.configure(dict(_saved_cfg, …)); …; rm.configure(_saved_cfg)`. Always restore; a leaked config fails unrelated assertions later with misleading labels. Prefer `cfg=` on `_run_main`, which restores for you.
- **`TEST_CFG` has no `boards` key, on purpose, and neither does `probe_layout`'s hand-built config.** Every read in `bin/roadmap` is `cfg.get('boards')`, never `cfg['boards']`. The hook reads `payload.get('boards') or ()`.
- **`str.startswith` takes a tuple, never a str.** Not exercised by `boards` (it is never a prefix filter), but `_require_str_list` exists because a bare string must be refused by name rather than coerced; its message is pinned byte-identically by the `claim_*` arms at `:2868-2871`.
- **Commit before every mutation drill.** The drill ends in `git checkout -- <file>`, which discards every uncommitted change in that file.
- **zsh brace rule.** Every `$var` followed by `:` is a modifier in zsh (`git show "$BASE:bin/roadmap"` silently misparses): write `"${BASE}:bin/roadmap"`. Quote heredocs (`<<'EOF'`) in `bd note` and commit bodies — a backtick in double-quoted prose is command substitution.
- **Live runs never touch a real config or a real state file.** `ROADMAP_CONFIG=<scratch toml>` with absolute `workspace`/`tag_repo` inside; `--state <scratch>` on direct runs and `ROADMAP_CADENCE_STATE=<scratch>` on hook runs; listed boards are **scratch copies** of the real scoped configs so their default state path lands in scratch too. Fix `--today 2026-10-14` on every direct `--json` run; the hook has no `--today` seam (see *Spec deviations*), so old-vs-new hook comparisons run back-to-back on one calendar day.
- Work in the worktree on branch `feat/multi-board`. `bd` commands run from the workspace root (the directory holding the shared `.beads/`), never from the worktree. Do not bump `plugin.json` / `marketplace.json` — the v0.8.0 release commit does that.

## Review Focus

Input classes the spec implies but does not test. Each is pinned by a named arm in the task that owns it; a reviewer should check those arms exist and fail when the guard is removed.

1. **An entry spelled with a trailing slash or a `./` prefix** (`"other-app/"`, `"./other-app"`). `_resolve` normalises both to the same directory, so `config_path` is clean, but `name` is kept *as written* and is what the header line prints. Pinned in Task 1 (`boards: a trailing slash normalises but the name stays as written`) and Task 4 (`header: name as written, directory, and an unquoted cd (control)`, `header: the name is printed as written, non-ASCII intact`).
2. **An entry that names the catch-all's own directory by another spelling** — `"./"`, the absolute non-realpath form (macOS `/var/…` for a `/private/var/…` file), or a symlink to a directory already listed. Self and duplicate checks compare `os.path.realpath` of each entry's `roadmap.toml`, so all three are refused at load. Pinned in Task 1 (`boards names its own directory as "./"`, `boards names its own directory by an absolute non-realpath spelling`, `boards: a symlink to a listed directory is a duplicate`).
3. **Every listed board missing** (`exists: false` for all). `concurrent.futures.ThreadPoolExecutor(max_workers=0)` raises `ValueError` (verified on 3.11.16); the hook-wide `except Exception: sys.exit(0)` would swallow it and the problem lines would never print — a silent listed board, the exact failure the design forbids. The pool is created only when there is something to run. Pinned in Task 4 (`every listed board missing: still reported (no empty pool)`).
4. **Two listed boards both slower than the timeout.** Each must be reported `timed out after Ns`, and wall time must be one timeout, not the sum — the parallel run is a stated property. Pinned in Task 4 (`parallel: wall time is one timeout, not the sum`), with a 2.0 s bound on a 1 s timeout (sequential would take ≥ 2 s before process overhead).
5. **A board name or directory containing a space or non-ASCII.** The header's `cd <dir> && roadmap` tail is pasted by a human; a space breaks it unless quoted. `shlex.quote` leaves a plain path untouched (verified: a temp path round-trips unchanged) and quotes one with a space, so the single-board form is unaffected. Non-ASCII survives `json.dumps` (escaped) and `--text`. Pinned in Task 4 (`header: a directory with a space is shell-quoted in the cd target`, `header: name as written, directory, and an unquoted cd (control)`, `header: the name is printed as written, non-ASCII intact`).

Judged **not real** and left untested: a listed board whose `state_path` equals the catch-all's. The only way to produce it is a hand-built payload; a real listed board's state is beside *its* config, and an entry pointing back at the catch-all's directory is refused at load (item 2). The hook would still behave (all writes are sequential on the main thread; the second write re-stamps the same file).

## Spec deviations (code-correct variants, consistent with the spec's intent)

- **`roadmap check` cannot take a fixed `--today`.** `bin/roadmap:1486` runs the hook with argv `[hook, '--text']` only, and the hook runs the binary with `['--json']` (`hooks/roadmap-cadence.py:214`); `args.today` is parsed and ignored on the `check` path. The spec's live step "`roadmap check --state … with a fixed --today`" is therefore run as: `--today` on every direct `--json` comparison, and hook/`check` comparisons back-to-back on one day (Task 7).
- **`stamp` is "a condition survived the throttle", not literally `bool(body)`.** Today's hook (`:285-296`) prints the header/pointer/footer and stamps whenever conditions survive, even for a condition with empty `lines`. Equal on every payload `bin/roadmap` can emit; computing it from survival keeps the degenerate case byte-identical too.
- **The `boards` block in `load_config` is split in two.** The `boards`+`scoped` refusal sits where the spec puts it (after the `scoped` bool check, before the `claim_*` loop, `:195`); the type/emptiness/resolution checks need `_resolve`, which is defined at `:233`, so they sit between `_resolve` and the `return`.
- **`_record_argv_stub` is not adapted.** Its capture is a bare `sys.argv` list that the I3 arms index (`:366-402`); Task 4 adds a sibling `_record_env_stub` that records `{'argv', 'config'}` per invocation instead of changing a format three arms depend on.
- **The selftest's payload arms sit at `:1310`, not with the config arms at `:2876`**, because the `_run_main(…, cfg=)` helper is shadowed from `:2427` on (Global Constraints).

---

### Task 1: Config layer — `_require_str_list`, `boards` validation and resolution

**Files:**
- Modify: `bin/roadmap` — `CONFIG_KEYS` (`:85-87`); new module-level `_require_str_list` just above `load_config` (`:120`); `load_config` after the `scoped` check (`:191-194`), the `claim_*` loop (`:195-213`), and between `_resolve` (`:233-234`) and the `return` (`:236-249`)
- Test: `bin/roadmap-selftest.py` — new section after the last `claims with scoped = false are refused` arm (`:2874`), before `# --- github-bjxle: who OWNS an unlabelled row` (`:2876`)

**Interfaces:**
- Produces: `_require_str_list(path, key, val) -> None`; raises `RoadmapUnavailable('%s: %s must be a list of strings, got %r' % (path, key, val))` for a bare `str`, a non-`list`, or a list with a non-`str` element. Message byte-identical to the 0.7.0 inline `claim_*` check.
- Produces: `load_config(...)['boards']` — `()` when the key is absent, else a tuple of `{'name': <as written>, 'config_path': <_resolve(name)>/roadmap.toml, 'exists': os.path.isfile(config_path)}` in list order. Nothing is read from a listed board's file.
- Refusals, all `RoadmapUnavailable`, messages (after the `%s: ` path prefix): `boards must be a list of strings, got %r` · `boards is empty -- list a directory or remove the key` · `boards contains an empty string` · `boards: %r is this file's own directory` · `boards: %r and %r resolve to the same roadmap.toml` · `boards and scoped = true cannot be combined -- the board that lists the others is the catch-all; remove one`.

- [ ] **Step 1: Write the failing tests** (after `:2874`)

```python
# --- github-7jn0v: boards -- the catch-all lists its sibling boards ---------
# One OPTIONAL key, on the CATCH-ALL only: directories, relative to this
# file, each holding a roadmap.toml. Only the session-start hook reads it.
# Nothing is read from a listed board here -- `a/roadmap.toml` below is an
# EMPTY file and still counts as present, because the catch-all's load must
# never fail over a sibling's broken file (decision 4). Every refusal is
# paired with a loading control.
_bd_dir, _bd_path = write_cfg(GOOD + 'boards = ["a", "./b"]\n')
os.makedirs(os.path.join(_bd_dir, 'a'))
open(os.path.join(_bd_dir, 'a', 'roadmap.toml'), 'w').close()
os.makedirs(os.path.join(_bd_dir, 'b'))
_bd_real = os.path.realpath(_bd_dir)     # macOS /var -> /private/var, as the walk-up arm notes
_bd_cfg = rm.load_config(_bd_path)
check('boards: resolved in list order, name as written',
      [e['name'] for e in _bd_cfg['boards']], ['a', './b'])
check('boards: config_path is <dir>/roadmap.toml under the realpath base',
      [e['config_path'] for e in _bd_cfg['boards']],
      [os.path.join(_bd_real, 'a', 'roadmap.toml'),
       os.path.join(_bd_real, 'b', 'roadmap.toml')])
check('boards: exists is measured per entry (must-hit and must-miss in one load)',
      [e['exists'] for e in _bd_cfg['boards']], [True, False])
check('boards: loads as a tuple, like every list key', isinstance(_bd_cfg['boards'], tuple), True)
check('boards: an absent key loads as an empty tuple (control)',
      rm.load_config(write_cfg(GOOD)[1])['boards'], ())
_abs_dir = tempfile.mkdtemp()
_, _abs_path = write_cfg(GOOD + 'boards = ["%s"]\n' % _abs_dir)
check('boards: an absolute entry resolves to itself, as written',
      rm.load_config(_abs_path)['boards'][0]['config_path'],
      os.path.join(_abs_dir, 'roadmap.toml'))
# Review focus 1: a trailing slash is a spelling, not a different directory.
_ts = rm.load_config(write_cfg(GOOD + 'boards = ["a/"]\n')[1])['boards'][0]
check('boards: a trailing slash normalises but the name stays as written',
      (_ts['name'], os.path.basename(os.path.dirname(_ts['config_path']))), ('a/', 'a'))

check_type_rejected('boards bare string', GOOD + 'boards = "other-app"\n',
                    'boards must be a list of strings')
check_type_rejected('boards non-list', GOOD + 'boards = 5\n',
                    'boards must be a list of strings')
check_type_rejected('boards non-string element', GOOD + 'boards = [1]\n',
                    'boards must be a list of strings')
check_type_rejected('boards empty list', GOOD + 'boards = []\n', 'boards is empty')
check_type_rejected('boards empty string', GOOD + 'boards = [""]\n',
                    'boards contains an empty string')
check_type_rejected('boards names its own directory', GOOD + 'boards = ["."]\n',
                    "is this file's own directory")
# Review focus 2: three other spellings of "this directory".
check_type_rejected('boards names its own directory as "./"', GOOD + 'boards = ["./"]\n',
                    "is this file's own directory")
check_type_rejected('boards duplicates', GOOD + 'boards = ["a", "./a"]\n',
                    'resolve to the same roadmap.toml')


def _refused(label, path, needle):
    """Like check_type_rejected, for a config whose text had to embed a path
    only known after write_cfg() created its directory."""
    try:
        rm.load_config(path)
        check(label + ' raises', 'no raise', 'RoadmapUnavailable')
    except Exception as exc:
        check(label + ' is RoadmapUnavailable', isinstance(exc, rm.RoadmapUnavailable), True)
        check(label + ' names it', needle in str(exc), True)


_sd, _sp = write_cfg(GOOD)
with open(_sp, 'w') as _fh:            # the tempdir's NON-realpath spelling (/var/... on macOS)
    _fh.write(GOOD + 'boards = ["%s"]\n' % _sd)
_refused('boards names its own directory by an absolute non-realpath spelling', _sp,
         "is this file's own directory")
_ld, _lp = write_cfg(GOOD + 'boards = ["a", "link"]\n')
os.makedirs(os.path.join(_ld, 'a'))
os.symlink(os.path.join(_ld, 'a'), os.path.join(_ld, 'link'))
_refused('boards: a symlink to a listed directory is a duplicate', _lp,
         'resolve to the same roadmap.toml')
# MUST-MISS control for the pair above: two DIFFERENT directories load.
check('boards: two distinct entries load with two entries (control)',
      len(rm.load_config(write_cfg(GOOD + 'boards = ["a", "b"]\n')[1])['boards']), 2)

# boards + scoped: the board that lists the others IS the catch-all.
_, _bs = write_cfg(GOOD + 'scoped = true\nboards = ["a"]\n')
try:
    rm.load_config(_bs)
    check('boards with scoped = true raises', 'no raise', 'RoadmapUnavailable')
except Exception as _exc:
    check('boards with scoped = true is RoadmapUnavailable',
          isinstance(_exc, rm.RoadmapUnavailable), True)
    check('boards with scoped = true names BOTH keys',
          'boards' in str(_exc) and 'scoped' in str(_exc), True)
    check('boards with scoped = true says which board lists the others',
          'catch-all' in str(_exc), True)
check('boards with scoped = false loads (control)',
      rm.load_config(write_cfg(GOOD + 'scoped = false\nboards = ["a"]\n')[1])['scoped'], False)
# `scoped = true` alone still loads: the 0.7.0 arm above. The claim_* type
# arms above keep their 'must be a list of strings' messages: that is the
# byte-identity guard for extracting _require_str_list.
```

- [ ] **Step 2: Run the suite; the new assertions must fail**

Run: `python3 bin/roadmap-selftest.py`
Expected: `FAIL (n)`. The loading arms fail with `KeyError: 'boards'`-shaped results or, where the fixture carries the key, with `unknown key(s): boards` (the 0.7.0 loader refuses it by name). Every `check_type_rejected('boards …')` arm whose needle is a message fragment (`boards must be a list of strings`, `boards is empty`, …) fails its `names it` half because the message is `unknown key(s): boards`. Note which arms pass by accident (the needle `boards` alone would) — Step 4 must show the *new* refusals firing. If the run aborts with a traceback on `_bd_cfg['boards']`, that is still RED.

- [ ] **Step 3: Implement**

`CONFIG_KEYS`:

```python
CONFIG_KEYS = ('workspace', 'tag_repo', 'release_namespace',
               'convention_start', 'auto_label_prefixes', 'horizon',
               'scoped', 'claim_title_prefixes', 'claim_id_prefixes', 'boards')
```

Above `load_config` (`:120`):

```python
def _require_str_list(path, key, val):
    """Refuse a non-list or a list with a non-string BY NAME. A bare string
    is refused rather than coerced -- the auto_label_prefixes trap:
    str.startswith() accepts a tuple, so a bare string would decompose into
    one-character prefixes. Extracted from the 0.7.0 claim_* loop so `boards`
    can share it (github-7jn0v); the message is pinned byte-identically by
    the claim_* arms in the selftest."""
    if (isinstance(val, str) or not isinstance(val, list)
            or not all(isinstance(x, str) for x in val)):
        raise RoadmapUnavailable('%s: %s must be a list of strings, got %r'
                                 % (path, key, val))
```

After the `scoped` check (`:194`), before `claims = {}`:

```python
    # boards (github-7jn0v): the board that LISTS the others is the catch-all,
    # structurally. Refused here, before the claim_* loop, so a config with
    # all three wrong gets the most structural reason first.
    if 'boards' in raw and scoped:
        raise RoadmapUnavailable(
            '%s: boards and scoped = true cannot be combined -- the board that '
            'lists the others is the catch-all; remove one' % path)
```

In the `claim_*` loop, replace the inline type check (`:198-203`) with:

```python
        # Same trap as auto_label_prefixes: see _require_str_list.
        _require_str_list(path, k, val)
```

(keep the empty-string and `val and not scoped` checks that follow — they are claim-specific).

Between `_resolve` (`:234`) and the `return` (`:236`):

```python
    # boards (github-7jn0v): directories, relative to this file like tag_repo,
    # each holding its own roadmap.toml. Resolved and stat'ed here; NOTHING is
    # read from a listed board -- the catch-all's load must not fail because
    # a sibling's file is broken, and the hook learns the rest by running the
    # board. One level only: a listed board's own `boards` is never followed.
    # Self and duplicates compare realpaths, so "./", an absolute non-realpath
    # spelling and a symlink are all the same directory.
    boards = ()
    if 'boards' in raw:
        _require_str_list(path, 'boards', raw['boards'])
        if not raw['boards']:
            raise RoadmapUnavailable(
                '%s: boards is empty -- list a directory or remove the key' % path)
        if any(x == '' for x in raw['boards']):
            raise RoadmapUnavailable('%s: boards contains an empty string' % path)
        own = os.path.realpath(path)
        seen = {}
        entries = []
        for name in raw['boards']:
            cfg_path = os.path.join(_resolve(name), 'roadmap.toml')
            real = os.path.realpath(cfg_path)
            if real == own:
                raise RoadmapUnavailable(
                    "%s: boards: %r is this file's own directory" % (path, name))
            if real in seen:
                raise RoadmapUnavailable(
                    '%s: boards: %r and %r resolve to the same roadmap.toml'
                    % (path, seen[real], name))
            seen[real] = name
            entries.append({'name': name, 'config_path': cfg_path,
                            'exists': os.path.isfile(cfg_path)})
        boards = tuple(entries)
```

Return dict, after `'claim_id_prefixes': claims['claim_id_prefixes'],`:

```python
            'boards': boards,
```

- [ ] **Step 4: Run both suites — `ok` from both**

Then prove the right refusal fires, not the unknown-key one:

```bash
python3 - <<'PY'
import importlib.machinery, importlib.util, os, tempfile
spec = importlib.util.spec_from_loader('rm', importlib.machinery.SourceFileLoader('rm', 'bin/roadmap'))
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)
d = tempfile.mkdtemp(); p = os.path.join(d, 'roadmap.toml')
open(p, 'w').write('workspace = "."\ntag_repo = "."\nrelease_namespace = "acme-app"\nboards = []\n')
try: rm.load_config(p)
except rm.RoadmapUnavailable as e: print(e)
PY
```

Expected: a message ending `boards is empty -- list a directory or remove the key`, not `unknown key(s)`.

- [ ] **Step 5: Commit**

`git add bin/roadmap bin/roadmap-selftest.py` · `git commit -m "feat(roadmap): boards config key -- the catch-all lists its sibling boards (github-7jn0v)" -- bin/roadmap bin/roadmap-selftest.py` — body: optional, catch-all only, refused with `scoped = true`; resolved to `{name, config_path, exists}` without reading a sibling's file; `_require_str_list` extracted from the `claim_*` loop with its message unchanged. End with the attribution line from your session's system reminder.

- [ ] **Step 6: Mutation drills** (after the commit)

Drill A — drop the `boards`+`scoped` refusal:

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path('bin/roadmap'); s = p.read_text(); orig = s
s = s.replace("    if 'boards' in raw and scoped:\n", "    if False:\n")
assert s != orig, "mutation did not apply -- re-check the combo check text by hand"
p.write_text(s)
PY
python3 bin/roadmap-selftest.py > /tmp/mut.out 2>&1; echo "EXIT=$?"
grep -c 'boards with scoped = true' /tmp/mut.out
git checkout -- bin/roadmap
python3 bin/roadmap-selftest.py
```

Expected: `EXIT=1` and the `boards with scoped = true …` labels in the output (the `(control)` arm must not be among them); `ok` after the checkout.

Drill B — stop measuring `exists`: replace `'exists': os.path.isfile(cfg_path)` with `'exists': True` the same way. Expected: `EXIT=1` with `boards: exists is measured per entry …` failing; `ok` after the checkout. If either mutated run passes, the guard is not real — stop and report.

---

### Task 2: Payload — `render_json` gains `workspace` (always) and `boards` (only when configured)

**Files:**
- Modify: `bin/roadmap` — `render_json` (`:1144-1174`)
- Test: `bin/roadmap-selftest.py` — after the I3 `--json reports the resolved state path` block (`:1302-1308`), before the I2 comment at `:1310`. **Not** beside the Task 1 arms: `_run_main(…, cfg=)` is shadowed from `:2427`.

**Interfaces:**
- `render_json(model, conditions, cfg=None) -> str` — signature unchanged. Output gains `'workspace': cfg.get('workspace')` unconditionally (right after `'repo'`), and `'boards': [dict(e) for e in cfg.get('boards')]` **only when** `cfg.get('boards')` is non-empty, appended after `legacy_state_available`. The unavailable payload shapes at `:1511-1512` and `:1560` are untouched.

- [ ] **Step 1: Write the failing tests** (insert after `:1308`)

```python
# --- github-7jn0v: --json carries `workspace` ALWAYS and `boards` only when
# the config has the key. `boards` is what the hook iterates; `workspace` is
# what it compares to spot a second catch-all. Hand-built configs (TEST_CFG,
# probe_layout's) have neither key, so cfg.get() is the only read.
_BD_ENTRIES = ({'name': 'other-app', 'config_path': '/nonexistent/workspace/other-app/roadmap.toml',
                'exists': False},)
with tempfile.TemporaryDirectory() as _d:
    _rc, _out, _err = _run_main(['--json', '--state', os.path.join(_d, 's.json'),
                                 '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[],
                                cfg=dict(TEST_CFG, boards=_BD_ENTRIES))
    _pl_boards = json.loads(_out)
    check('--json: boards emitted when configured, three keys per entry',
          _pl_boards.get('boards'), [dict(e) for e in _BD_ENTRIES])
    check('--json: workspace is the loaded value (listing config)',
          _pl_boards.get('workspace'), TEST_CFG['workspace'])
    _rc, _out, _err = _run_main(['--json', '--state', os.path.join(_d, 't.json'),
                                 '--today', '2026-11-01'],
                                open_issues=[], closed_issues=[], tag_dates=[])
    _pl_plain = json.loads(_out)
    check('--json: NO boards key at all without the config key (must-miss control)',
          'boards' in _pl_plain, False)
    check('--json: workspace is unconditional', _pl_plain.get('workspace'),
          TEST_CFG['workspace'])
```

- [ ] **Step 2: Run the suite; expected:** `--json: boards emitted …: got None, want [...]` and both `workspace` arms `got None`; the must-miss control passes already (note that — it is the arm the mutation drill below makes fail).

- [ ] **Step 3: Implement**

Rewrite `render_json` so the dict is built, then conditionally extended:

```python
def render_json(model, conditions, cfg=None):
    cfg = cfg or CONFIG
    v = lambda x: _fmt_v(x) if x else None
    out = {
        'repo': cfg['release_namespace'],
        # github-7jn0v: the resolved workspace, ALWAYS -- the hook compares a
        # listed board's to the catch-all's to spot a second catch-all, and a
        # conditional key would make that depend on which side carried it.
        'workspace': cfg.get('workspace'),
        'cut': v(model.get('cut')),
        'in_flight': v(model.get('in_flight')),
        'planned': [_fmt_v(x) for x in model.get('planned') or []],
        'baseline': model.get('baseline'),
        'versions': {
            _fmt_v(k): {'open': len(e['leaves_open']),
                        'closed': e['leaves_closed'],
                        'gates': [g['id'] for g in e['gates']],
                        'leaves': [i['id'] for i in e['leaves_open']]}
            for k, e in model['versions'].items()},
        'unscheduled_count': len(model['unscheduled']),
        'unscheduled': [{'id': i['id'], 'priority': _prio(i),
                         'title': i.get('title') or ''} for i in model['unscheduled']],
        'backlog_count': len(model.get('backlog') or []),
        'backlog': [{'id': i['id'], 'priority': _prio(i),
                     'title': i.get('title') or ''} for i in (model.get('backlog') or [])],
        'horizon': cfg.get('horizon') or 0,
        'scoped': bool(model.get('scoped')),
        'hotfix_count': len(model['hotfix']),
        'hotfix': [{'id': i['id'], 'priority': _prio(i),
                    'title': i.get('title') or ''} for i in model['hotfix']],
        'throughput': model.get('throughput') or {},
        'conditions': conditions,
        'state_path': model.get('state_path'),
        'legacy_state_available': bool(model.get('legacy_state_available')),
    }
    # github-7jn0v: only the catch-all that LISTS boards carries the key. A
    # config without it produces a payload without it -- absent and empty
    # must stay distinguishable, and TEST_CFG / probe_layout's config have
    # no key at all.
    boards = cfg.get('boards')
    if boards:
        out['boards'] = [dict(e) for e in boards]
    return json.dumps(out, indent=2)
```

(The keys `cut` through `legacy_state_available` are `:1149-1173` verbatim; only `workspace` is inserted and the trailing `boards` added.)

- [ ] **Step 4: Run both suites — `ok`**

- [ ] **Step 5: Commit** — `git commit -m "feat(roadmap): --json carries workspace and, when configured, boards (github-7jn0v)" -- bin/roadmap bin/roadmap-selftest.py`

- [ ] **Step 6: Mutation drill** — make `boards` unconditional:

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path('bin/roadmap'); s = p.read_text(); orig = s
s = s.replace("    if boards:\n        out['boards'] = [dict(e) for e in boards]\n",
              "    out['boards'] = [dict(e) for e in (boards or ())]\n")
assert s != orig, "mutation did not apply -- re-check the render_json tail by hand"
p.write_text(s)
PY
python3 bin/roadmap-selftest.py > /tmp/mut.out 2>&1; echo "EXIT=$?"
grep -c 'NO boards key at all' /tmp/mut.out
git checkout -- bin/roadmap
python3 bin/roadmap-selftest.py
```

Expected: `EXIT=1`, the must-miss control named; `ok` after the checkout.

---

### Task 3: Hook — pin the single-board form, then extract `board_report`

**Files:**
- Modify: `hooks/roadmap-cadence.py` — docstring properties 3 and 4 (`:26-30`) and the seams block (`:43-47`); `main` from `state = …` (`:236`) to `return 0` (`:297`)
- Test: `hooks/test_roadmap_cadence.py` — new arm after the `--text` block's shebang arm (`:555-562`), before `if FAILURES:` (`:564`)

**Interfaces:**
- Produces: `board_report(payload, state, days) -> (prelude, body, stamp)` — `prelude`: the once-ever state-move lines (marker `legacy_state_reported` written to **this** `state`), else `[]`; `body`: the `lines` of every condition that survives **this** board's throttle (`read_stamp(state)` against `days`, bypass conditions always), else `[]`; `stamp`: `True` iff at least one condition survived — exactly when the pre-change hook wrote its stamp. The `roadmap init` nudge is **not** in `board_report`; `main` appends it to the catch-all's `prelude`.
- Consumes: `read_stamp`, `write_stamp`, `legacy_lines`, `already_legacy_reported`, `mark_legacy_reported` — unchanged.

This task changes **no behaviour**. The byte-identity arm is written first, passes against the current hook, and then guards the extraction; the pre-existing suite runs unmodified as the behavioural half of the same guard.

- [ ] **Step 1: Write the byte-identity arm** (passes now — it is a pin, not a RED step; insert before `:564`)

```python
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
```

Run: `python3 hooks/test_roadmap_cadence.py` → `ok`. Commit: `git commit -m "test(hook): pin the single-board output exactly (github-7jn0v)" -- hooks/test_roadmap_cadence.py`.

- [ ] **Step 2: Extract `board_report`** — add above `main` (`:192`):

```python
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
```

Replace `:238-297` of `main` (from the `# C1 (github-kkq4a)` comment through `return 0`) with:

```python
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
        # here, matching property 4. It speaks only ONCE per state file (a
        # dedicated marker, not the normal throttle stamp). Consulted for
        # the catch-all only: a LISTED board cannot be unconfigured.
        if payload.get('unconfigured') and not already_nudged(state):
            prelude.append(
                'No roadmap.toml found -- run `roadmap init` once per '
                'workspace to set this up. (This prints once; silent '
                'after that until the file exists.)')
            mark_nudged(state)

    lines = list(prelude)
    if stamp:
        lines.append('ROADMAP CADENCE CHECK (roadmap, github-4jmwr)')
        lines.extend(body)
        lines.append('Full board: `roadmap`  ·  queue: `roadmap hotfix`')
        lines.append('(Throttled conditions run at most once every %g days;'
                     ' bypass conditions repeat every session.)' % days)
    if not lines:
        return 0  # clean, throttled, or an already-reported notice -> silence
    emit('\n'.join(lines), plain=plain)
    if stamp:
        write_stamp(state)
    return 0
```

Docstring edits (same commit): property 3 → `3. READ-ONLY, ALWAYS. It runs \`bin/roadmap --json\` -- once for this board and, from Task 4 on, once per board the catch-all LISTS -- and nothing else.` (write the final wording in Task 4; here only the `board_report` reference matters). Seams block: `ROADMAP_CADENCE_STATE    path to the stamp file -- the CATCH-ALL's only (github-7jn0v); a listed board is always judged on the state_path its own payload names`.

- [ ] **Step 3: Run both suites — `ok`.** The three `exact:` arms and every pre-existing arm pass unchanged. If any `state move:` or `unconfigured:` arm fails, the nudge or the marker moved relative to the prelude — compare against `:248-271` of the committed file.

- [ ] **Step 4: Commit** — `git commit -m "refactor(hook): board_report judges one board on its own state file (github-7jn0v)" -- hooks/roadmap-cadence.py`

- [ ] **Step 5: Mutation drill** — leak a header into the single-board form:

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path('hooks/roadmap-cadence.py'); s = p.read_text(); orig = s
s = s.replace("        lines.append('ROADMAP CADENCE CHECK (roadmap, github-4jmwr)')\n",
              "        lines.append('ROADMAP CADENCE CHECK (roadmap, github-4jmwr)')\n        lines.append('-- acme-app')\n")
assert s != orig, "mutation did not apply"
p.write_text(s)
PY
python3 hooks/test_roadmap_cadence.py > /tmp/mut.out 2>&1; echo "EXIT=$?"
grep -c 'exact: the single-board' /tmp/mut.out
git checkout -- hooks/roadmap-cadence.py
python3 hooks/test_roadmap_cadence.py
```

Expected: `EXIT=1` with both `exact: the single-board …` arms named and **no other** arm failing (every pre-existing arm is a substring test — that is why the exact pin was needed); `ok` after the checkout.

---

### Task 4: Hook — run the listed boards, report problems (a) and (b), assemble one emit

**Files:**
- Modify: `hooks/roadmap-cadence.py` — imports (`:49-53`: add `concurrent.futures`, `shlex`); new functions `_run_board`, `run_listed`, `problem_lines`, `board_header` above `main`; `main` between `state = …` and the `lines = list(prelude)` block from Task 3; docstring properties 3 and 4
- Test: `hooks/test_roadmap_cadence.py` — a new section after Task 3's `exact:` arms, before `if FAILURES:`; the fixture helpers go at the top of that section

**Interfaces:**
- `_run_board(binary, entry, timeout) -> (payload, None) | (None, reason)` — pool worker; runs `[sys.executable, binary, '--json']` with `env=dict(os.environ, ROADMAP_CONFIG=entry['config_path'])`, never `--state`. Catches everything. Reasons: `timed out after %ds` · `exited %d` · `unparseable json` · the payload's `unavailable` string (or `unconfigured`) · `no conditions in payload` (the **key** is absent — `conditions: []` is a clean board) · `payload carries no state_path` · `str(exc)`.
- `run_listed(binary, boards, timeout) -> [(entry, payload, line)]` in list order; exactly one of `payload`/`line` is `None`; `line` is the finished text `boards: <name> listed, no roadmap.toml there` (shape a) or `boards: <name> unavailable: <reason>` (shape b). Entries with `exists` falsy or no `config_path` never run. The pool is created only when there is something to run (Review Focus 3).
- `problem_lines(catch_payload, outcomes) -> [str]` — shapes (a) and (b) now; Task 5 adds (c) here.
- `board_header(entry) -> str` — `'-- %s  ·  %s  ·  full board: cd %s && roadmap' % (name, dir, shlex.quote(dir))` with `dir = os.path.dirname(entry['config_path'])`.
- Hook-suite helpers: `fake_roadmap_boards(by_config, rc=0) -> stub path` (keys: `None` for the catch-all, a `config_path` for a listed board; values: a payload `str`, or `{'payload': str, 'rc': int, 'sleep': float}`); `listed_board(name, **payload) -> (entry, payload_json)` (own temp dir, real empty `roadmap.toml`, own `state_path`, `conditions` defaulting to `[]`); `catch_all(boards, workspace='/ws/acme-app', **payload) -> payload_json` (`workspace=None` omits the key); `seed_stamp(path, age=0.0) -> float`; `stamp_of(path) -> float | None`; `_record_env_stub(capture_dir, by_config) -> stub path`.

- [ ] **Step 1: Fixture helpers and the failing arms** (one section; every arm below fails against the Task 3 hook because no listed board is run)

```python
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
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    with open(path, 'w') as fh:
        fh.write('#!/usr/bin/env python3\nimport os, sys, time\n')
        fh.write('TABLE = %r\n' % by_config)
        fh.write('key = os.environ.get("ROADMAP_CONFIG")\n')
        fh.write('if key not in TABLE:\n')
        fh.write('    sys.stderr.write("stub: unknown ROADMAP_CONFIG %r\\n" % (key,))\n')
        fh.write('    sys.exit(3)\n')
        fh.write('spec = TABLE[key]\n')
        fh.write('if isinstance(spec, str):\n    spec = {"payload": spec}\n')
        fh.write('time.sleep(spec.get("sleep", 0))\n')
        fh.write('sys.stdout.write(spec["payload"])\n')
        fh.write('sys.exit(spec.get("rc", %d))\n' % rc)
    os.chmod(path, 0o755)
    return path


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


def fresh_state():
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    os.unlink(path)
    return path


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
# unquoted plain directory.
_dir1 = os.path.dirname(_e1['config_path'])
check('header: name as written, directory, and an unquoted cd (control)',
      '-- other-app  ·  %s  ·  full board: cd %s && roadmap' % (_dir1, _dir1) in out2)

# 2. A MISSING listed board speaks; a present CLEAN board is silent.
_e2, _p2 = listed_board('other-app')
_stub2 = fake_roadmap_boards({None: catch_all([_e2, MISSING]), _e2['config_path']: _p2})
rc, out, _ = run_hook(_stub2)
check('missing board: named', 'boards: third-app listed, no roadmap.toml there' in out)
check('missing board: a clean present board has no block (must-miss)', '-- other-app' not in out)
check('missing board: the catch-all pointer line still prints', 'Full board: `roadmap`' in out)
check('missing board: the problem line sits before the pointer line',
      out.index('third-app listed') < out.index('Full board: `roadmap`'))
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
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    with open(path, 'w') as fh:
        fh.write('#!/usr/bin/env python3\nimport os, sys, json\n')
        fh.write('open(os.path.join(%r, "%%d.json" %% os.getpid()), "w").write(json.dumps(\n'
                 '    {"argv": sys.argv, "config": os.environ.get("ROADMAP_CONFIG")}))\n' % capture_dir)
        fh.write('TABLE = %r\n' % by_config)
        fh.write('sys.stdout.write(TABLE.get(os.environ.get("ROADMAP_CONFIG"), ""))\n')
        fh.write('sys.exit(0)\n')
    os.chmod(path, 0o755)
    return path


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
```

- [ ] **Step 2: Run the hook suite; expected RED:** every arm in groups 1 (except the catch-all-speaks and exits-0 lines), 2, 3 (`speak on a fresh stamp`), 4, 6, 7 (`both boards ran`), 8 (`-- other-app` arms), and both review-focus header arms fail — the Task 3 hook never runs a listed board. Group 9 and the `I8 control` pass already (they are controls). The suite still prints `FAIL (n)` and exits 1 without a traceback; a traceback means a fixture bug — fix the fixture, not the hook.

- [ ] **Step 3: Implement**

Imports (`:49-53`): add `import concurrent.futures` and `import shlex` in alphabetical order.

Above `main`, after `board_report`:

```python
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
    return lines


def board_header(entry):
    """`-- <name as written>  ·  <dir>  ·  full board: cd <dir> && roadmap`.
    The cd target is shell-quoted because a human pastes it; shlex.quote
    leaves a plain path untouched, so the usual case reads as before."""
    d = os.path.dirname(entry['config_path'])
    return '-- %s  ·  %s  ·  full board: cd %s && roadmap' % (entry['name'], d, shlex.quote(d))
```

In `main`, directly after `state = forced_state or payload.get('state_path') or LEGACY_STATE` and before the Task 3 `prelude, body, stamp = board_report(...)` line:

```python
    # github-7jn0v: the catch-all may LIST its sibling boards. Run each now --
    # in parallel, each under its own ROADMAP_CONFIG, never with --state --
    # BEFORE any state is read, so every stamp read and write below happens
    # on this thread, in list order. A listed board that cannot be run is a
    # line under the catch-all: the one deliberate exception to property 4.
    # The catch-all's own `boards` is the only list read (one level).
    outcomes = run_listed(binary, payload.get('boards') or (), timeout)
    problems = problem_lines(payload, outcomes)
    if problems:
        payload['conditions'] = list(payload.get('conditions') or []) + [
            {'id': 'boards', 'bypass': False, 'lines': problems}]
```

Replace the Task 3 assembly (from `lines = list(prelude)` to the final `return 0`) with:

```python
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
```

Docstring, final wording: property 3 → `3. READ-ONLY, ALWAYS. It runs \`bin/roadmap --json\` -- once for this board and once per board the catch-all's \`boards\` key LISTS (github-7jn0v) -- and nothing else. It never applies a label. The suite walks this file's AST for argv list literals and checks them against a set of write verbs.` Property 4 → after `every path exits 0 with no output.` add: `ONE deliberate exception (github-7jn0v): a board the catch-all LISTS and that is missing, unreadable or a second catch-all is reported as a line under the catch-all -- listing a board is the user asking to be told when it breaks, and a silent listed board would be the false-clean this tool exists to refuse. The catch-all itself still fails open: if IT cannot be read there is no list, and the hook is silent.`

- [ ] **Step 4: Run both suites — `ok`.** The AST read-only arm still finds `--json` and `--state` and no write verb (the new argv literal is the same three tokens). The `exact:` arms from Task 3 pass — the single-board path skips `run_listed` (empty list), `blocks` is empty, `speaking == stamp`.

- [ ] **Step 5: Commit** — `git commit -m "feat(hook): report every board the catch-all lists, each on its own throttle (github-7jn0v)" -- hooks/roadmap-cadence.py hooks/test_roadmap_cadence.py`

- [ ] **Step 6: Mutation drills** (after the commit)

Drill A — one shared stamp (the spec's "sequential with one shared stamp" falsifier): replace `            write_stamp(st_i)\n` with `            write_stamp(state)\n`. Expected: `EXIT=1`, `throttles (swapped): the listed board's stamp was written` and `throttles (swapped): the catch-all's seeded stamp is untouched` named; `ok` after `git checkout -- hooks/roadmap-cadence.py`.

Drill B — the empty pool: replace `    if todo:\n        with concurrent.futures` with `    if True:\n        with concurrent.futures`. Expected: `EXIT=1`, `every listed board missing: still reported (no empty pool)` named (the hook exits 0 silent — the exact failure the arm exists for); `ok` after the checkout.

Drill C — run the catch-all only: replace `    outcomes = run_listed(binary, payload.get('boards') or (), timeout)` with `    outcomes = []`. Expected: `EXIT=1` with every group-1/2/4/6/7/8 listed-board arm named, and the `exact:` arms still passing (the single-board form is untouched by this mutation — which is the point of pinning it separately); `ok` after the checkout.

---

### Task 5: Hook — the second catch-all (c), and the cross-suite key agreement

**Files:**
- Modify: `hooks/roadmap-cadence.py` — `problem_lines` (Task 4) and a new `second_catch_all` beside it
- Test: `hooks/test_roadmap_cadence.py` — continue the Task 4 section (group 5)
- Test: `bin/roadmap-selftest.py` — extend the payload-key agreement arm (`:2378-2392`)

**Interfaces:**
- `second_catch_all(catch_payload, listed_payload) -> bool` — `True` iff `listed_payload.get('scoped')` is falsy **and** both payloads carry a truthy `workspace` **and** `os.path.realpath(a) == os.path.realpath(b)`. No evidence, no finding.
- `problem_lines` gains shape (c): for an outcome with a payload, `two catch-all boards: %s repeats every unowned row -- add scoped = true` when `second_catch_all` holds. The board is still reported as a board (its own block, its own throttle).

- [ ] **Step 1: Write the failing arms** (after group 9 / the review-focus-5 arms)

```python
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
_e5m, _p5m = listed_board('other-app', scoped=False, conditions=OTHER_CREEP)      # no workspace
rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e5m], workspace=_ws5), _e5m['config_path']: _p5m}))
check('two catch-alls: listed side lacks workspace -> absent (no evidence)', _TWO not in out)
_e5n, _p5n = listed_board('other-app', scoped=False, workspace=_ws5, conditions=OTHER_CREEP)
rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e5n], workspace=None), _e5n['config_path']: _p5n}))
check('two catch-alls: catch-all side lacks workspace -> absent (no evidence)', _TWO not in out)
check('two catch-alls: ...and the board is still reported (control)', '-- other-app' in out)
# The (c) line rides the catch-all's throttle like (a) and (b).
_e5t, _p5t = listed_board('other-app', scoped=False, workspace=_ws5, conditions=OTHER_CREEP)
_ca5t = fresh_state()
seed_stamp(_ca5t)
rc, out, _ = run_hook(fake_roadmap_boards({None: catch_all([_e5t], workspace=_ws5), _e5t['config_path']: _p5t}),
                      state=_ca5t)
check('two catch-alls: the line is throttled with the catch-all', _TWO not in out)
check('two catch-alls: ...while the listed board still speaks on its own stamp', '-- other-app' in out)
```

Selftest, replace the loop at `:2380-2382` and extend (keep the `unconfigured` and `legacy_state_migrated` arms):

```python
_RENDERED_KEYS = rm.render_json({'versions': {}, 'unscheduled': [], 'hotfix': []}, [])
for _key in ('state_path', 'legacy_state_available', 'conditions'):
    check('the hook reads %r by the name render_json emits it' % _key,
          _key in _HOOK_SRC and ('"%s"' % _key) in _RENDERED_KEYS, True)
# github-7jn0v: the three multi-board keys, searched QUOTED in the hook. The
# bare word `workspace` already occurs in the hook's prose, so the bare
# search above would pass against a hook that never reads the key. `boards`
# is emitted only under a config that has it, so it needs its own render.
_RENDERED_BOARDS = rm.render_json(
    {'versions': {}, 'unscheduled': [], 'hotfix': []}, [],
    cfg=dict(TEST_CFG, boards=({'name': 'other-app', 'config_path': '/x/other-app/roadmap.toml',
                                'exists': False},)))
for _key, _rendered in (('workspace', _RENDERED_KEYS), ('scoped', _RENDERED_KEYS),
                        ('boards', _RENDERED_BOARDS)):
    check('the hook reads %r (quoted) by the name render_json emits it' % _key,
          ("'%s'" % _key) in _HOOK_SRC and ('"%s"' % _key) in _rendered, True)
check('boards is absent from a render without the key (control)',
      '"boards"' in _RENDERED_KEYS, False)
check('a quoted key neither side uses is in neither (control)',
      "'legacy_state_migrated'" in _HOOK_SRC, False)
```

- [ ] **Step 2: Run both suites; expected RED:** hook suite — `two catch-alls (unscoped, same workspace): line present` and `(… realpath form): line present` fail (every `absent` control and every `still reported` arm passes already — note that; Step 4 keeps them green). Selftest — `the hook reads 'scoped' (quoted) …` fails if Task 4's hook does not yet read `'scoped'`; `'boards'` and `'workspace'`… `'workspace'` fails until `second_catch_all` reads it. If all three already pass, the hook text happens to carry the quoted names — still implement, the drill below proves the arm bites.

- [ ] **Step 3: Implement** — above `problem_lines`:

```python
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
    if not a or not b:
        return False
    return os.path.realpath(a) == os.path.realpath(b)
```

`problem_lines` body becomes:

```python
    lines = []
    for entry, payload, line in outcomes:
        if line is not None:
            lines.append(line)
        elif second_catch_all(catch_payload, payload):
            lines.append('two catch-all boards: %s repeats every unowned row -- '
                         'add scoped = true' % entry['name'])
    return lines
```

- [ ] **Step 4: Run both suites — `ok`**

- [ ] **Step 5: Commit** — `git commit -m "feat(hook): flag a listed board that is a second catch-all; pin the three payload keys across suites (github-7jn0v)" -- hooks/roadmap-cadence.py hooks/test_roadmap_cadence.py bin/roadmap-selftest.py`

- [ ] **Step 6: Mutation drills**

Drill A — drop the realpath: replace `    return os.path.realpath(a) == os.path.realpath(b)` with `    return a == b`. Expected: `EXIT=1` with `two catch-alls (unscoped, same workspace in realpath form): line present` named on macOS (on Linux the temp dir is already real and this drill is inconclusive — say so in the commit evidence rather than skipping it silently); `ok` after `git checkout -- hooks/roadmap-cadence.py`.

Drill B — drop the evidence rule: replace `    if not a or not b:\n        return False\n` with `    a = a or ''\n    b = b or ''\n`. Expected: `EXIT=1` with both `-> absent (no evidence)` arms named; `ok` after the checkout.

Drill C — the agreement arm bites: in the hook, rename `listed_payload.get('scoped')` to `listed_payload.get('scopd')`; run the **selftest**. Expected: `the hook reads 'scoped' (quoted) …` fails; `git checkout -- hooks/roadmap-cadence.py`; `ok`.

---

### Task 6: Documentation

**Files:**
- Modify: `README.md` (`:95-104` list, `:111-125` glossary, `:324-330` *Script against it*, `:343-382` *Several products*, `:384-397` *SessionStart hook*, `:445-458` *drift check*), `roadmap.example.toml` (after `:67`), `docs/DESIGN.md` (`:113-148` *Fail-open*, `:150-191` *Several products*), `CHANGELOG.md` (`:8`, the empty `## [Unreleased]`)
- Optional: `commands/roadmap.md:36`, `skills/roadmap/SKILL.md:30`

No code; run both suites at the end — the decoupling scan walks every `.md` and `.toml`, including this plan.

- [ ] **Step 1: `README.md`**

1. **"Before you start"** — item 9 after item 8:
   > 9. **Optional: `boards = ["other-app", "third-app"]` in the catch-all's `roadmap.toml`**, listing the directories of the scoped boards that share its `bd` database. The session-start check and `roadmap check`, run from the catch-all's directory, then report every listed board, each on its own throttle. Cannot be combined with `scoped = true`. See [Hearing every board from one session](#hearing-every-board-from-one-session).
2. **Glossary** — one row after *catch-all board*:
   `| **listed board** | A scoped board named in the catch-all's `boards` list. The catch-all's session-start check runs it too and reports it under a `-- <name>` header; a listed board that is missing or cannot be read is itself reported. |`
3. **"Script against it"** — after the `"scoped"` sentence: *`--json` also carries `"workspace"` (the resolved path) and, only on a board whose config has the key, `"boards"` — one `{name, config_path, exists}` per listed board.*
4. **New H4 "Hearing every board from one session"** at the end of *Several products, one `bd` board* (before *The SessionStart hook*). Content, in order: the symptom (a session opened at the workspace root hears only the catch-all's drift; a scoped board's empty horizon reaches only a session opened inside it); the config block from the spec's *Section 1* (the commented `# boards = [...]` lines, then `boards = ["other-app", "third-app"]` uncommented); the rule *the board that lists the others is the catch-all — `boards` with `scoped = true` is refused*; what the report looks like (the catch-all's lines as today, then `-- other-app  ·  <dir>  ·  full board: cd <dir> && roadmap` blocks for listed boards with something to say); the three problem lines and what each means (`boards: other-app listed, no roadmap.toml there` · `boards: other-app unavailable: <reason>` · `two catch-all boards: other-app repeats every unowned row -- add scoped = true`), that they repeat every three days like scope creep, and that a listed board on a *different* workspace that is unscoped is fine (it is another database's catch-all); one level only; and the upgrade order — **update the install before adding the key**: a `roadmap` older than 0.8.0 refuses it by name, prints `roadmap: unavailable: … unknown key(s): boards` when run by hand, and the catch-all's session-start check goes silent, exactly as the 0.7.0 note says for `scoped`.
5. **"The SessionStart hook"** — one sentence after the throttle sentence: *When the catch-all's `roadmap.toml` lists `boards`, the check also covers every listed board, each on its own throttle, under a `-- <name>` header.*
6. **"The drift check: `roadmap check`"** — one sentence after the first paragraph: *With `boards` in the catch-all's config, `roadmap check` reports every listed board too.*

- [ ] **Step 2: `roadmap.example.toml`** — append after the `claim_id_prefixes` line:

```toml

# Optional, on the CATCH-ALL board only. Directories, relative to this file,
# that each hold their own roadmap.toml. The session-start check (and
# `roadmap check`) run from this directory then report every listed board,
# each on its own throttle, not just this one. The text board and --json of
# a board never change. Cannot be combined with scoped = true: the board
# that lists the others is the catch-all.
# boards = ["other-app", "third-app"]
```

- [ ] **Step 3: `docs/DESIGN.md`** — *Several products, one board* gains a closing paragraph (replace the last sentence `Detection belongs with the multi-product hook work (github-7jn0v), …`): the catch-all **lists** its siblings (`boards`, github-7jn0v); only the hook reads the list; each listed board runs under its own `ROADMAP_CONFIG`, in parallel, and is judged on its own state file, so one board's report never resets another's throttle; why the list is explicit (a glob reports boards nobody asked about, from a cwd the hook does not control, and has no answer for a sibling checkout outside the root); why `boards` and `scoped` exclude each other (the board that reads more than one config is, structurally, the catch-all — the property 0.7.0 could only document is now enforced in the one place that can check it); what the catch-all can detect among listed boards (a second unscoped board on the same workspace) and what it still cannot (an unlisted one). *Fail-open, always* gains a sentence after **One exception.** paragraph: *A second exception (github-7jn0v): a board the catch-all lists and that is missing or unreadable is reported as a line under the catch-all rather than silenced — listing it is the user asking to be told. The catch-all itself still fails open; if it cannot be read there is no list.*

- [ ] **Step 4: `CHANGELOG.md`** — under `## [Unreleased]` (`:8`; the 0.7.0 release commit `a01b35a` renamed the previous `[Unreleased]` to `[0.7.0] — 2026-10-14` and left this empty section, so the v0.8.0 release commit will do the same):

```markdown
### Added

- **`boards` in the catch-all's `roadmap.toml`: the session-start check and
  `roadmap check` report every listed board.** The catch-all lists the
  directories of its sibling boards; the hook runs each under its own config,
  in parallel, judges each on its own state file and throttle, and prints one
  report — the catch-all's lines as before, then a `-- <name>` block per
  listed board with something to say. A listed board that is missing, cannot
  be read, or is a second unscoped board on the same workspace is named under
  the catch-all instead of being silent. `boards` with `scoped = true` is
  refused: the board that lists the others is the catch-all. `--json` carries
  `workspace` on every board and `boards` on one that lists them. An older
  `roadmap` refuses the key by name; update the install before adding it.

### Changed

- Nothing for a board without `boards`: the text board, `--json` (apart from
  the added `workspace` key) and the session-start check are byte-identical.
```

- [ ] **Step 5 (optional):** `commands/roadmap.md:36` → append *(every listed board too, when the catch-all lists them)*; `skills/roadmap/SKILL.md:30` → same clause.

- [ ] **Step 6: Run both suites — `ok`** (the decoupling scan must stay empty). **Commit** — `git commit -m "docs: boards -- hearing every board from one session (github-7jn0v)" -- README.md roadmap.example.toml docs/DESIGN.md CHANGELOG.md commands/roadmap.md skills/roadmap/SKILL.md` (drop the two optional paths if untouched).

---

### Task 7: Live verification on the reference workspace — scratch configs only, nothing real touched

**Preconditions:** `bd` and `git` reachable; the worktree at `$WT` (this checkout); the merge-base tree extracted to `$S/old` (binary **and** hook — `roadmap check` resolves the hook beside its own binary, so the old `check` must run against the old hook). `WS` = the directory holding the shared `.beads/` and the catch-all `roadmap.toml`; `S` = the session scratchpad. Pick two real scoped checkouts under `$WS` — call them `A` and `B` — whose `roadmap.toml` carries `scoped = true`. Brace every `${var}` that is followed by a colon. Every listed board is a **scratch copy** of the real config, so its default state path (`<config dir>/.roadmap-state.json`) lands in `$S`, never beside a real config.

- [ ] **Step 1: Binaries and scratch configs**

```bash
WT=<absolute path of this worktree>; S=<scratchpad>; WS=<workspace root>
NEW="$WT/bin/roadmap"
BASE=$(git -C "$WT" merge-base HEAD main)
mkdir -p "$S/old/bin" "$S/old/hooks" "$S/A" "$S/B" "$S/root" "$S/nowhere"
git -C "$WT" show "${BASE}:bin/roadmap" > "$S/old/bin/roadmap"
git -C "$WT" show "${BASE}:hooks/roadmap-cadence.py" > "$S/old/hooks/roadmap-cadence.py"
OLD="$S/old/bin/roadmap"
```

Write `$S/A/roadmap.toml` and `$S/B/roadmap.toml` as copies of `$WS/A/roadmap.toml` and `$WS/B/roadmap.toml` with `workspace` and `tag_repo` rewritten to **absolute** paths (`workspace = "<WS>"`, `tag_repo = "<WS>/A"`); keep `scoped`, claims, `horizon`, `convention_start` as they are. Write `$S/root/roadmap.toml` as a copy of `$WS/roadmap.toml` with absolute paths **plus**:

```toml
boards = ["../A", "../B", "../nowhere"]
```

(`$S/nowhere` exists and holds no `roadmap.toml` — the shape-(a) must-hit.) Write `$S/root-plain/roadmap.toml` as the same copy **without** `boards` (the single-board control), and `$S/root-two/roadmap.toml` as `$S/root/roadmap.toml` with `boards = ["../A", "../root-plain"]` — a second unscoped board on the same workspace, the shape-(c) must-hit.

- [ ] **Step 2: Oracle — which listed boards are in drift today** (direct `--json`, fixed `--today`)

```bash
for b in A B; do
  ROADMAP_CONFIG="$S/$b/roadmap.toml" python3 "$NEW" --json --today 2026-10-14 --state "$S/st-$b.json" 2>"$S/$b.err" \
    | python3 -c 'import json,sys; p=json.load(sys.stdin); print(sys.argv[1], [c["id"] for c in p["conditions"]], p.get("scoped"), p.get("workspace"))' "$b"
done
```

Expected: each line names the board, its condition ids, `True`, and `<WS>`. At least one of `A`/`B` must list a non-empty id list (a `HORIZON SHORT` on a board with `horizon` set is the usual one); if both are empty, pick a third scoped checkout or lower `horizon` in the scratch copy until one is in drift — the must-hit needs a board that speaks. Record which is the speaking board (`SPEAK`) and which is clean (`QUIET`). Also confirm `python3 "$NEW" --json ... | grep -c '"boards"'` is `0` on `$S/A/roadmap.toml` (a scoped board never carries the key) and `1` on `$S/root/roadmap.toml`.

- [ ] **Step 3: Must-hit / must-miss through the hook** (`roadmap check` = the hook in `--text`; fresh scratch stamps so nothing is throttled)

```bash
rm -f "$S/st-root.json" "$S/A/.roadmap-state.json" "$S/B/.roadmap-state.json"
ROADMAP_CONFIG="$S/root/roadmap.toml" python3 "$NEW" check --state "$S/st-root.json" > "$S/check-new.txt" 2>"$S/check-new.err"; echo "EXIT=$?"
grep -n '^-- \|^boards: \|two catch-all\|^ROADMAP CADENCE CHECK\|^Full board' "$S/check-new.txt"
```

Expected, in this order: `ROADMAP CADENCE CHECK (roadmap, github-4jmwr)` (the catch-all's own lines as today follow it); `boards: ../nowhere listed, no roadmap.toml there` **before** `Full board:`; a `-- ../SPEAK  ·  <S>/SPEAK  ·  full board: cd <S>/SPEAK && roadmap` header with that board's condition lines under it (must-hit); **no** `-- ../QUIET` header (must-miss); no `two catch-all boards` line (A and B are scoped). `$S/A/.roadmap-state.json` and `$S/B/.roadmap-state.json` now exist (the listed boards' binaries wrote their own state), and `last_reported_at` is present only in `SPEAK`'s — `python3 -c 'import json; print(json.load(open("'"$S"'/QUIET/.roadmap-state.json")).get("last_reported_at"))'` prints `None`. The real `$WS/A/.roadmap-state.json` mtime is unchanged (`stat -f %m` before and after).

Second run, same files: the catch-all's throttled lines and the `boards:` line are gone; any bypass condition on `SPEAK` repeats; exit 0.

Shape (c):

```bash
ROADMAP_CONFIG="$S/root-two/roadmap.toml" python3 "$NEW" check --state "$S/st-root-two.json" | grep -c 'two catch-all boards: ../root-plain repeats every unowned row'
```

Expected: `1`. Control: the Step 3 run above contains `0` such lines (`grep -c` printing `0` exits 1 — that is the pass; exit 2 is an error).

Unavailable (b): point a fourth entry at a scratch dir holding a `roadmap.toml` with a typo'd key (`release_namespc = "x"`); expected `boards: ../broken unavailable: <path>: unknown key(s): release_namespc` and every other board still reported.

- [ ] **Step 4: Byte-identity of the single-board hook output, old vs new**

```bash
rm -f "$S/st-plain-old.json" "$S/st-plain-new.json"
ROADMAP_CONFIG="$S/root-plain/roadmap.toml" python3 "$OLD" check --state "$S/st-plain-old.json" > "$S/plain-old.txt" 2>/dev/null
ROADMAP_CONFIG="$S/root-plain/roadmap.toml" python3 "$NEW" check --state "$S/st-plain-new.json" > "$S/plain-new.txt" 2>/dev/null
diff "$S/plain-old.txt" "$S/plain-new.txt"; echo "DIFF_EXIT=$?"
ROADMAP_CONFIG="$S/root-plain/roadmap.toml" python3 "$OLD" --json --today 2026-10-14 --state "$S/st-plain-old.json" 2>/dev/null > "$S/plain-old.json"
ROADMAP_CONFIG="$S/root-plain/roadmap.toml" python3 "$NEW" --json --today 2026-10-14 --state "$S/st-plain-new.json" 2>/dev/null > "$S/plain-new.json"
diff "$S/plain-old.json" "$S/plain-new.json"
ROADMAP_CONFIG="$S/root-plain/roadmap.toml" python3 "$OLD" --today 2026-10-14 --state "$S/st-plain-old.json" 2>/dev/null > "$S/board-old.txt"
ROADMAP_CONFIG="$S/root-plain/roadmap.toml" python3 "$NEW" --today 2026-10-14 --state "$S/st-plain-new.json" 2>/dev/null > "$S/board-new.txt"
diff "$S/board-old.txt" "$S/board-new.txt"; echo "BOARD_DIFF_EXIT=$?"
```

Expected: `DIFF_EXIT=0` (the hook's text form — both runs on the same day, back-to-back, fresh stamps, so both speak or both are silent; **a non-empty `plain-new.txt` is required for this to count** — if both files are empty, the catch-all is clean today and the comparison is vacuous: temporarily set `horizon = 9` in `root-plain` to force a bypass condition and re-run both); the JSON diff is exactly one added line, `"workspace": "<WS>",`; `BOARD_DIFF_EXIT=0` for the text board. If a diff shows only THROUGHPUT counts, a `bd` write landed between the runs — re-run back-to-back. Any other difference is a regression; stop.

- [ ] **Step 5: Record the evidence** on the issue from `$WS`: `bd note github-7jn0v "$(cat <<'EOF' … EOF)"` — the Step 2 oracle lines, the Step 3 grep (headers present/absent, the `boards:` line, the `two catch-all` count and its control), the `None` stamp on `QUIET`, the unchanged real-state mtime, `DIFF_EXIT=0`, the one-line JSON diff, `BOARD_DIFF_EXIT=0`. Then remove `$S/A/.roadmap-state.json` etc. with the scratchpad — nothing under `$WS` was written.

---

### Task 8: Merge, push, CI — and the gated config rollout as a post-release step

- [ ] **Step 1: Full suites on the branch** — `python3 bin/roadmap-selftest.py` and `python3 hooks/test_roadmap_cadence.py` both `ok`; `git -C "$WT" status --short` clean.

- [ ] **Step 2: Push the branch first and wait for CI.** `git -C "$WT" remote -v` — `origin` is GitHub (`Kaimoku-Technologies/beads-roadmap`), the one remote; pushing it is correct and required. `git -C "$WT" push origin feat/multi-board`, then `gh run list --repo Kaimoku-Technologies/beads-roadmap --branch feat/multi-board --limit 3` until the `test` workflow shows both suites green on 3.11, 3.12 and 3.13 (poll — CI is external state the harness cannot see). A red matrix cell is a stop: the parallel-timing arm (Review Focus 4, 2.0 s bound) is the one most likely to be runner-sensitive; if it alone fails on one version, widen the bound to 2.5 s in its own commit and re-push rather than deleting the arm.

- [ ] **Step 3: Merge fast-forward and push `main`.** From the main checkout of this repo (not the worktree): `git merge --ff-only feat/multi-board` on `main` (`main` is at `a01b35a`, the branch point, so ff applies), then `git push origin main`. Confirm `gh run list --branch main --limit 1` goes green too.

- [ ] **Step 4: Do NOT bump the version.** `release:beads-roadmap-v0.8.0` is cut by its own release commit, which bumps `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (the selftest's manifest-agreement arm pins both) and renames `## [Unreleased]` to `## [0.8.0] — <date>` leaving a fresh empty `[Unreleased]`, exactly as `a01b35a` did for 0.7.0.

- [ ] **Step 5 (post-release, not part of this plan's acceptance): the gated config rollout.** Only after 0.8.0 is cut and installed and `roadmap --version` prints `roadmap 0.8.0 (…)` for the *installed* binary: add `boards = ["<dir of A>", "<dir of B>", …]` to the catch-all `roadmap.toml` at the workspace root, one entry per scoped checkout, relative to that file. The scoped boards' configs are untouched. Then open a session at `$WS` (or run `roadmap check` there with the installed binary) and confirm the output names each listed board that is in drift under its `-- <name>` header, with the pre-fix control being the same session on the 0.7.0 install, which reports only the catch-all. Until step 4 is done, adding the key makes the 0.7.0 install print `unknown key(s): boards` and the root session's hook goes silent — the README (Task 6) warns in the same words it uses for `scoped`.

- [ ] **Step 6: Close** `github-7jn0v` from `$WS` with the Task 7 evidence and the CI run URLs; acceptance: a catch-all that lists boards reports each listed board on its own throttle and names a missing/unreadable/second-catch-all board; a board without the key is byte-identical (text, hook) apart from `workspace` in `--json`; both suites cover both directions of every rule.

---

## Separable follow-ups (for the user to file; not created by this plan)

- A `max_workers` cap for the listed-board pool if `bd` ever fails under N+1 concurrent readers (measured fine at five; the fallback is a one-line change, spec *Open questions*).
- `--today` pass-through from `roadmap check` to the hook and binary, so hook-level comparisons can be pinned to a date like the direct runs are (spec deviation 1).
- Workspace-level detection of an **unlisted** unscoped board on the same database (the 0.7.0 caveat that `boards` narrows but does not close).
- `roadmap init` could mention `boards` in its multi-namespace refusal text, beside `scoped`.
- Unify `_require_str_list` with the `auto_label_prefixes` validator (its bare-string message differs and is pinned by an arm — out of scope by the spec).
