# Multi-board session-start check: one catch-all config lists its sibling boards — design

**Status** · approved in conversation (every decision below was taken by the user); not yet
implemented
**Scope** · `bin/roadmap` (config loader, `render_json`), `hooks/roadmap-cadence.py`,
`bin/roadmap-selftest.py`, `hooks/test_roadmap_cadence.py`, `roadmap.example.toml`,
`README.md`, `docs/DESIGN.md`, `CHANGELOG.md`. `roadmap check` changes only because it IS
the hook (`bin/roadmap:1478-1490` runs `hooks/roadmap-cadence.py --text`); the text board,
`hotfix`, `unscheduled`, `backlog`, `plan`, `pin` and `init` are untouched.
**Canonical source** · this document, until the code lands; then the code
**Last verified** · 2026-10-14 (every premise re-probed against the tree at `a01b35a`, the
0.7.0 release commit, which `feat/multi-board` branches from)
**Issue** · `github-7jn0v` (release `beads-roadmap-v0.8.0`) · builds on `github-bjxle`
(shipped, 0.7.0: `scoped`, the catch-all) and `github-kkq4a` (shipped, 0.2.0: per-install
state files, which is what makes per-board throttling possible) · precedent document
`docs/superpowers/specs/2026-10-14-product-scoping-design.md`

> Product names are generic throughout, as the decoupling scan at the end of the selftest
> requires of every shipped file: **`acme-app`** is the unscoped catch-all whose
> `roadmap.toml` sits at the shared workspace root `$WS`; **`other-app`** and **`third-app`**
> are scoped boards in their own checkouts under `$WS`, each with its own `roadmap.toml` and
> `workspace = $WS`.

---

## What this is

Several products share one `bd` database. Since 0.7.0 each has its own board: a scoped
`roadmap.toml` per checkout, plus exactly one unscoped catch-all at the workspace root. The
SessionStart hook runs `roadmap --json` **once**, from the session's cwd, and `find_config`
walks up to the nearest `roadmap.toml` (`bin/roadmap:102-117`). A session opened at `$WS`
therefore hears only `acme-app`'s drift. `other-app`'s empty horizon or unversioned P0 is
reported only to a session that happens to open inside `other-app/`, and never to the root
session that most planning work starts from.

This design lets the catch-all's config **list** its sibling boards, and teaches the hook to
run each listed board, judge each on its own state file, and print one combined report.
Nothing else reads the list.

---

## Premise verification

### Confirmed as written

| Claim | Evidence at `a01b35a` |
| --- | --- |
| The hook runs the binary once, from the session cwd, with no config argument | `hooks/roadmap-cadence.py:214-218`: `argv = [sys.executable, binary, '--json']`, optional `--state`, one `subprocess.run`. No `cwd=`, no `ROADMAP_CONFIG`. |
| `roadmap check` is the hook's `--text` form, not a reimplementation | `bin/roadmap:1478-1490`: resolves `hooks/roadmap-cadence.py` beside itself, sets `ROADMAP_CADENCE_BIN=<self>` (and `ROADMAP_CADENCE_STATE` from `--state`), runs it with `--text`, 120 s timeout, exits 0 on any failure. Every change below reaches `check` for free; `check` needs no code of its own. |
| `$ROADMAP_CONFIG` selects a config verbatim, before the walk-up | `bin/roadmap:106-108`; selftest `env override wins` pins it. This is the seam the hook uses to run a listed board without changing cwd. |
| Relative config paths resolve against the config file's directory | `bin/roadmap:228-234` (`base`, `_resolve`). `boards` entries follow the same rule, like `tag_repo`. |
| `scoped` is a validated bool, default `False`, in the loaded dict and the payload | `bin/roadmap:191-194`, `:242`; `render_json` emits `'scoped'` at `:1166`. |
| Each board already has its own state file | `default_state_path` (`bin/roadmap:626-643`): `<config dir>/.roadmap-state.json`. The hook stamps `payload['state_path']` (`hooks/roadmap-cadence.py:236`). Per-board throttling needs no new state. |
| The hook's unavailable handling is silent for every reason but `unconfigured` | `hooks/roadmap-cadence.py:253-271` and the I8 arms of the hook suite. The design's one new exception (listed-board problems) is additive and lives under the catch-all. |
| The hook suite drives the hook through env seams and scripted fakes, never bd | `hooks/test_roadmap_cadence.py:32-72` (`fake_roadmap`, `fake_roadmap_sleep`, `run_hook`); seams listed in the hook docstring `:43-47`. |
| A pre-0.8.0 binary refuses an unknown key by name | `bin/roadmap:135-141`; selftest `unknown key is named`. `boards` on an old install prints `roadmap: unavailable: … unknown key(s): boards` and the hook stays silent. |

### Corrected — what the code does NOT already carry

1. **The `--json` payload has no `workspace` key.** `render_json` (`bin/roadmap:1144-1174`)
   emits `repo`, `cut`, `in_flight`, `planned`, `baseline`, `versions`, `unscheduled*`,
   `backlog*`, `horizon`, `scoped`, `hotfix*`, `throughput`, `conditions`, `state_path`,
   `legacy_state_available`. Rule (c) below ("unscoped AND shares the catch-all's
   `workspace`") cannot be judged from today's payload. **This spec adds `workspace`** as a
   second additive key, beside `boards` — the same class of change as 0.7.0's `scoped`,
   where the unscoped board's JSON gained a key the hook ignores.
2. **The payload's namespace key is `repo`, not `release_namespace`** (`:1148`). The hook
   needs no namespace at all (block headers use the `boards` entry name as written), so
   nothing is added; the spec just uses the real name where it matters.
3. **There is no reusable list-of-strings validator function.** The `claim_*` checks are
   inline inside a `for k in (...)` loop (`bin/roadmap:195-213`), as `auto_label_prefixes`'
   are (`:159-177`). "Validated with the existing validator" therefore means: extract the
   two `claim_*` type checks into a helper and call it for the third key, keeping the two
   messages byte-identical (the existing `check_type_rejected` arms pin them). This is the
   "only if trivially needed" case the 0.7.0 design left open, and it is now needed.
4. **The payload-key agreement arm is a bare substring search.** Selftest `:2371-2392`
   asserts each key name appears in the hook source and, quoted, in `render_json`'s output.
   The word `workspace` already occurs in the hook's prose (`hooks/roadmap-cadence.py:59`,
   `:171`, `:181-183`, `:235`, `:266`), so adding it to that loop as written would pass
   against a hook that never reads it. The new arm must search for the quoted form
   (`'workspace'`), and the same for `boards` and `scoped`.

---

## Decision

1. **An explicit list.** The catch-all's `roadmap.toml` gains `boards`, a list of directory
   paths. No auto-discovery, no `[[product]]` tables (see *Rejected alternatives*).
2. **Only the hook reads it** — and `roadmap check`, which is the hook. The text board, its
   subcommands and the JSON model of a board are unchanged except for two additive JSON keys.
   There is no `roadmap --all`.
3. **The board that lists others is the catch-all, structurally.** `boards` with
   `scoped = true` is refused at load. 0.7.0 documented "exactly one unscoped board per shared
   database" as a convention it could not check from one config; a workspace that adopts
   `boards` now has that property enforced in the one place that reads more than one config.
4. **Listed-board problems are reported, never fatal.** The catch-all's own report always
   runs. A listed board that is missing, broken or a second catch-all becomes a line under the
   catch-all; it never silences anything.
5. **Each board is judged on its own state file**, in parallel, and the result is one emit.

---

## Section 1 — config surface

One new key in `CONFIG_KEYS` (`bin/roadmap:85-87`), optional:

```toml
# Optional, on the CATCH-ALL board only. Directories, relative to this file,
# that each hold their own roadmap.toml. The session-start check (and
# `roadmap check`) run from this directory then report every listed board,
# each on its own throttle, not just this one. The text board and --json of
# a board never change. Cannot be combined with scoped = true: the board
# that lists the others is the catch-all.
# boards = ["other-app", "third-app"]
```

### Validation, all at `load_config`, each refused by name with `RoadmapUnavailable`

- **Type.** The `claim_*` inline checks (`:200-203`) become `_require_str_list(path, key,
  val)` — a bare string refused with the `must be a list of strings, got %r` message, a
  non-list or non-string element likewise. Both `claim_*` keys and `boards` call it; the
  `claim_*` empty-string check (`:206-208`, message `contains an empty string, which would
  claim every row`) stays beside its callers because its reason is claim-specific.
- **Non-empty list.** `boards = []` is refused: `boards is empty -- list a directory or
  remove the key`. Absent and empty would otherwise be indistinguishable in the payload, and
  an empty list is a config someone meant to fill in.
- **Non-empty strings.** `""` resolves to the config's own directory; refused:
  `boards contains an empty string`.
- **No self, no duplicates.** An entry whose resolved `roadmap.toml` is this config's own
  path is refused (`boards: %r is this file's own directory`); two entries resolving to the
  same file are refused (`boards: %r and %r resolve to the same roadmap.toml`). Both are
  errors in the file being loaded, so they belong to the refusal class, not the report class
  (filled-in mechanic; the approved design did not name these two cases).
- **`boards` with `scoped = true`** is refused, naming both keys:
  `boards and scoped = true cannot be combined -- the board that lists the others is the
  catch-all; remove one`. Order: after the `scoped` bool check, before the `claim_*` loop,
  so a config with all three wrong gets the most structural reason first.

### Resolution, in the loader

For each entry, in list order: `_resolve(entry)` (the existing closure, `:233-234`) gives
the directory; the entry's `config_path` is `os.path.join(dir, 'roadmap.toml')`; `exists`
is `os.path.isfile(config_path)` at load time. The loaded dict gains:

```python
'boards': (                      # () when the key is absent
    {'name': 'other-app',        # as written in the TOML
     'config_path': '<abs>/other-app/roadmap.toml',
     'exists': True},
    ...)
```

Nothing is read from a listed board's `roadmap.toml` at this point — no TOML parse, no
second `load_config`, no `scoped`/`workspace` lookup. The catch-all's load must not fail
because a sibling's file is broken (decision 4), and the hook learns everything else by
running the board.

**One level only.** A listed board's own `boards` key, if it has one, is neither resolved
here nor followed by the hook. There is no visited set because there is no walk.

### What the catch-all cannot be told

- A listed board on a **different** `workspace` that is unscoped is legitimate (it is the
  catch-all of another database) and is not flagged.
- A board that is not listed is simply not reported. The list is the user's statement of
  which boards this session should hear about; the tool does not second-guess it.

---

## Section 2 — payload

`render_json` gains two keys:

- **`boards`** — emitted **only when** `cfg.get('boards')` is non-empty: the tuple above as
  a JSON array, entry keys `name`, `config_path`, `exists`. A config without the key produces
  a payload without the key. Hand-built configs (`TEST_CFG`, `probe_layout`'s) lack it, so
  `cfg.get('boards')` is the only read.
- **`workspace`** — always emitted, `cfg.get('workspace')`, the resolved absolute path. This
  is the deviation from "unchanged apart from `boards`" that *Corrected* item 1 forces; it is
  unconditional because a conditional key would make the hook's same-workspace comparison
  depend on which side happened to carry it. The unavailable payload shapes (`:1511-1512`,
  `:1560`) are unchanged.

The hook reads from a **listed** board's payload: `conditions`, `state_path`,
`legacy_state_available`, `scoped`, `workspace`, `unavailable`. From the **catch-all's**
payload it additionally reads `boards` and `workspace`, and ignores `boards` on any listed
board's payload (one level).

---

## Section 3 — hook

### Run order

1. Run the catch-all exactly as today: `[sys.executable, binary, '--json']`, `--state` only
   when `ROADMAP_CADENCE_STATE` is set, env inherited. Fail open as today on a missing binary,
   non-zero exit, bad JSON or timeout — a catch-all that cannot be read yields **no list**, so
   the whole hook is silent, which is property 4 applied to the only board the hook can find
   on its own.
2. If the payload carries `boards`, partition its entries: `exists: false` entries become
   problem lines immediately; the rest are run **in parallel** with
   `concurrent.futures.ThreadPoolExecutor(max_workers=len(existing))`, each a
   `subprocess.run([sys.executable, binary, '--json'], env=dict(os.environ,
   ROADMAP_CONFIG=entry['config_path']), capture_output=True, text=True, timeout=timeout)`.
   No `--state` is ever passed to a listed board, even when `ROADMAP_CADENCE_STATE` is set:
   that seam forces the **catch-all's** stamp only (docstring updated to say so). The listed
   board's binary resolves its own default state path beside its config. Wall time is the
   slowest board plus process overhead.
3. **Subprocesses run in the pool; every state read and write happens on the main thread**,
   after `as_completed`/`result()` has returned, in list order. The stamp files are per
   board, so no two writes race, but keeping the writes sequential means a later debugging
   session never has to ask.
4. Each worker catches `Exception` itself and returns an outcome tuple; a worker's exception
   becomes that board's `unavailable` line, never a `.result()` re-raise that would trip the
   hook-wide `except Exception: sys.exit(0)` and silence every board.

### Per-board judgement — `board_report(payload, state, days)`

Today's lines `hooks/roadmap-cadence.py:229-296` become one function, called once for the
catch-all and once per listed board, returning `(prelude, body, stamp)`:

- `state` is `ROADMAP_CADENCE_STATE or payload['state_path'] or LEGACY_STATE` for the
  catch-all (unchanged, `:236`). For a listed board it is `payload['state_path']` and
  nothing else: a listed payload with no `state_path` is reported as
  `unavailable: payload carries no state_path`, because falling back to `LEGACY_STATE`
  would share one stamp across boards and reintroduce exactly the cross-board reset this
  design forbids.
- `prelude`: the once-ever state-move notice (`legacy_lines`, keyed on
  `legacy_state_reported` in **this** board's file) — unchanged in content.
- The `roadmap init` nudge (`unconfigured`) is consulted for the **catch-all only**. A
  listed board cannot be unconfigured (the hook set `ROADMAP_CONFIG` to a file it was told
  exists); a listed payload carrying `unconfigured` is treated as `unavailable` with its
  reason.
- `body`: the condition lines, each kept or dropped by **this board's** throttle
  (`read_stamp(state)` against `days`) and its `bypass` flag — the loop at `:287-290`.
- `stamp`: `True` iff `body` is non-empty, i.e. exactly when today's `write_stamp` runs
  (`:296`). Prelude-only output never stamps (the existing `does not consume the throttle
  stamp` arm).

One board's report never touches another board's file: there is no shared stamp, and the
`roadmap init` marker stays where it is today.

### Listed-board problem lines

Three shapes, all under the catch-all, `name` as written in the TOML:

| case | detected by | line |
| --- | --- | --- |
| (a) no config there | `entry['exists']` is false | `boards: other-app listed, no roadmap.toml there` |
| (b) cannot be read | non-zero exit · timeout · unparseable JSON · payload with `unavailable` · payload with neither `conditions` nor `unavailable` · no `state_path` · worker exception | `boards: other-app unavailable: <reason>` — the reason is the payload's `unavailable` string when there is one, else `exited N` / `timed out after Ns` / `unparseable json` / `no conditions in payload` / `payload carries no state_path` / `<exception>` |
| (c) second catch-all | listed payload has `scoped` falsy **and** both payloads carry `workspace` **and** `os.path.realpath(listed) == os.path.realpath(catch_all)` | `two catch-all boards: other-app repeats every unowned row -- add scoped = true` |

`realpath` on both sides because `_resolve` normalises a relative path against a
realpath'd base but returns an absolute path as written, so `/var/x` and `/private/var/x`
must not read as two workspaces. If either side lacks `workspace` the rule does not fire:
a finding needs evidence, and an older or stubbed payload is not evidence.

Problem lines are **one non-bypass pseudo-condition of the catch-all**: they are dropped
when the catch-all is throttled, and when they print they count as the catch-all speaking,
so its stamp is written. A missing board is therefore re-reported every `days`, like scope
creep, not every session like an empty horizon. **This is the one deliberate exception to
property 4** (every unavailable reason but `unconfigured` stays silent): listing a board is
the user asking to be told when it breaks, and a silent listed board would be the
false-clean this tool exists to refuse. The hook docstring's property 4 gains that sentence.

A listed board judged under (c) is **still reported** as a board: its own conditions appear
in its own block, on its own throttle. The two-catch-all line says the rows are duplicated;
it does not hide them.

### Output — one emit

`emit()` writes one JSON object (`:67-78`) and must keep doing so; everything below is
collected into one `lines` list first, as `prelude` already is (`:246-248`).

```
<catch-all prelude: state-move notice, roadmap init nudge>        (as today, before the header)
ROADMAP CADENCE CHECK (roadmap, github-4jmwr)                      (iff any block below)
<catch-all condition lines>                                        (as today)
boards: third-app listed, no roadmap.toml there                    (problem lines, catch-all block)
Full board: `roadmap`  ·  queue: `roadmap hotfix`                  (as today; iff the catch-all block is non-empty)
-- other-app  ·  <abs dir>  ·  full board: cd <abs dir> && roadmap (one headed block per listed board with something to say)
<other-app prelude, then its condition lines>
(Throttled conditions run at most once every 3 days; bypass conditions repeat every session.)
```

- **The catch-all's block is today's form verbatim** — no header line is added to it when
  `boards` is present. The session is in or under the catch-all's directory, so the
  unheaded block is "here" and the headed blocks are "elsewhere"; that is the information a
  header carries, and it is also what makes byte-identity free (filled-in mechanic: the
  approved design said "one block per board, headed by name + directory"; the catch-all's
  name and directory are implied by the cwd, and giving it a header would change the
  single-board output).
- Problem lines sit after the catch-all's condition lines and before its pointer line. A
  catch-all with no conditions but with problem lines still gets the pointer line.
- A listed board's block exists iff its `prelude` or `body` is non-empty; its prelude (the
  state-move notice for **its** state file) goes inside its block, under its header.
- The `ROADMAP CADENCE CHECK` header and the throttle footer are emitted iff at least one
  block (catch-all or listed) has condition or problem lines. A listed board whose only
  content is a once-ever notice still gets its block (the notice has to reach the session)
  under no header, exactly as the catch-all's prelude reaches the session alone today.
- Stamps: after assembling, `write_stamp(state_i)` for every board whose `stamp` is true.
- Nothing from any board → no output, exit 0.

**Byte-identity.** With no `boards` key in the catch-all's payload, steps 2-3 of the run
order are skipped, `board_report` for the catch-all produces today's `prelude`/`body`, and
the assembly above degenerates to today's `lines`. The existing hook suite must pass
without a single edit.

### Fail open

Per board: timeout, non-zero exit, bad JSON, or a worker exception becomes a line under the
catch-all; every other board still reports. Hook-wide: the `__main__` guard (`:300-304`) is
unchanged, so an exception the per-board handling does not reach still exits 0 silent.

### Seams

No new environment seam is needed. `ROADMAP_CADENCE_BIN` is the whole lever: the hook runs
it for every board, so a fake that **branches on `ROADMAP_CONFIG`** plays every board of a
fixture (helper below). `ROADMAP_CADENCE_STATE` keeps its meaning and gains a documented
limit — catch-all only. `ROADMAP_CADENCE_TIMEOUT` applies per subprocess, so a slow listed
board is bounded by the same number as the catch-all.

---

## Known limits, accepted

- **The list is hand-maintained.** A new board nobody lists is not reported. The upgrade
  path for a new product is one line in the root `roadmap.toml`; a glob would report boards
  nobody asked about and would be read from a cwd the hook does not control.
- **The catch-all is the single point of silence.** If the root board cannot be read, no
  listed board is run. The alternative — a hook that finds other boards without a working
  catch-all — needs discovery, which was rejected.
- **A second catch-all is detected only among listed boards**, and only when both carry
  `workspace`. An unlisted unscoped board on the same database is still the 0.7.0 caveat.
- **`roadmap init` never writes `boards`.** It refuses a multi-namespace board already; the
  catch-all of a shared database is a hand-written config, and the key is added by hand.
- **Concurrent `bd list` readers.** N listed boards means N+1 concurrent `bd list` pairs
  against one database. See *Open questions*.

---

## Test coverage

### `bin/roadmap-selftest.py` — config and payload

Fixtures via `write_cfg` (`:1908`) and `check_type_rejected` (`:2014`); listed boards are
real temp directories so `exists` is measured, not assumed. Every rule in both directions:

1. **Type.** Bare string (`boards = "other-app"`), non-list (`boards = 5`), non-string
   element (`boards = [1]`) — each `RoadmapUnavailable`, each naming `boards`. The two
   `claim_*` bare-string / non-string arms keep passing with unchanged messages (that is the
   byte-identity guard for the extraction).
2. **Emptiness.** `boards = []` refused naming `boards`; `boards = [""]` refused naming
   `boards`; control: `boards = ["other-app"]` loads.
3. **Self and duplicates.** `boards = ["."]` refused; `boards = ["a", "./a"]` refused;
   control: `["a", "b"]` loads with two entries.
4. **`boards` + `scoped`.** `scoped = true` plus `boards` refused, message naming **both**
   `boards` and `scoped`; control: `scoped = false` plus `boards` loads; control: `scoped =
   true` alone still loads (0.7.0 arm).
5. **Resolution.** A fixture dir with `a/roadmap.toml` present and `b/` empty: the loaded
   `boards` tuple has `name` as written (`"a"`, `"./b"`), `config_path` equal to the realpath
   form (same macOS `/var` caveat the walk-up arm documents), `exists` `True`/`False`
   respectively; an absolute entry resolves to itself.
6. **Payload.** Through `_run_main` (`:1237`) with `cfg=` a loaded config: `--json` carries
   `boards` with the three entry keys when configured; the **must-miss control** is the same
   run under `TEST_CFG` — no `boards` key at all (not an empty list). `workspace` is present
   in both and equals the loaded value.
7. **Agreement arm (`:2371-2392`).** Extend the loop with `boards`, `workspace`, `scoped`,
   searching the hook source for the **quoted** name (`'boards'`), since the bare word
   `workspace` already appears in the hook's prose and a bare search would be vacuous
   (*Corrected* item 4).
8. **Decoupling scan** (`:2636`) stays empty: the new fixtures, this document and the hook
   fixtures use `acme-app` / `other-app` / `third-app` only.
9. **Mutation drills** (house style, after committing): drop the `boards`+`scoped` refusal —
   arm 4 fails; drop the `exists` stat — arm 5 fails; make `boards` unconditional in
   `render_json` — arm 6's control fails.

### `hooks/test_roadmap_cadence.py` — behaviour

A new fixture helper beside `fake_roadmap` (`:32`):

```python
def fake_roadmap_boards(by_config, rc=0):
    """A stub that prints by_config[os.environ.get('ROADMAP_CONFIG')] -- the
    catch-all's payload under the key None -- so ONE ROADMAP_CADENCE_BIN plays
    every board of a fixture. Nothing here touches bd."""
```

Each catch-all payload names its listed boards with `config_path`s that are real temp
files (so `exists` is honest) and distinct `state_path`s per board in fresh temp dirs. Every
assertion paired must-hit / must-miss, each pair in one run where the design says "both
directions":

1. **Independent throttles.** Catch-all `THROTTLED`-shaped with a fresh stamp, `other-app`
   `THROTTLED`-shaped with a **seeded** stamp: the output carries the catch-all's creep line
   and the `-- other-app` header is **absent**; swap the stamps: the catch-all's line is
   absent and `other-app`'s block is present. Then assert the stamp file of the silent board
   was **not** written (`last_reported_at` unchanged) while the speaking board's was — one
   board's report never resets another's throttle.
2. **Missing listed board speaks; a present clean board is silent.** `third-app` with
   `exists: false`, `other-app` existing and `CLEAN`: output has
   `boards: third-app listed, no roadmap.toml there` and no `-- other-app` header. Control
   on the same fixture with `third-app` existing and `CLEAN` too: total silence (`''`), the
   same assertion the single-board `no conditions -> total silence` arm makes.
3. **Problem lines ride the catch-all's throttle.** The missing-board fixture with a seeded
   catch-all stamp: silent. The same with a fresh stamp: speaks and the catch-all stamp is
   written. Control: a `BYPASS` catch-all with a seeded stamp still speaks — problem lines
   are not bypass-class but do not suppress one either.
4. **Unavailable listed board.** `other-app` stub exits 1 / prints `not json` / prints
   `{"unavailable": "bd exited 1"}` / sleeps past `ROADMAP_CADENCE_TIMEOUT=1` (reuse
   `fake_roadmap_sleep`'s shape): each yields `boards: other-app unavailable: …` with the
   matching reason, and in the timeout case the hook returns well under the suite's own
   30 s. Control: the catch-all's own `unavailable` payload still yields silence (the
   existing I8 control), proving the exception is scoped to **listed** boards.
5. **Two catch-alls.** `other-app` payload `scoped: false`, `workspace` equal to the
   catch-all's: output has `two catch-all boards: other-app repeats every unowned row`.
   Controls: `scoped: true` same workspace — absent; `scoped: false` **different**
   workspace — absent; `scoped: false` same workspace but `workspace` missing from one side
   — absent (no evidence, no finding). Plus the realpath pair: `/var/…` versus
   `/private/var/…` forms of one temp dir are flagged (macOS) or trivially equal (Linux).
6. **Per-board once-ever notice.** `other-app` with `legacy_state_available: true`: its
   block carries `ROADMAP STATE MOVED` naming **its** `state_path`; second run on the same
   files: absent; the marker is in `other-app`'s state file and **not** in the catch-all's.
7. **No `--state` leaks to a listed board.** `_record_argv_stub` (`:335`) adapted to record
   `ROADMAP_CONFIG` beside `sys.argv`: with `ROADMAP_CADENCE_STATE` set, the catch-all's
   recorded argv carries `--state <forced>` and the listed board's carries `--json` only,
   with `ROADMAP_CONFIG` equal to the entry's `config_path`. Control: the unset arm already
   present.
8. **One JSON object.** On a two-board report, `json.loads(out)` parses and carries
   `hookSpecificOutput.hookEventName == 'SessionStart'`; `--text` form opens with
   `ROADMAP CADENCE CHECK` and contains both the catch-all's line and the `-- other-app`
   header.
9. **Catch-all unreadable → everything silent.** Catch-all stub exits 1 while `other-app`
   would speak: `''`. (Property 4 for the catch-all; the list is unreachable.)
10. **Byte-identity.** A new exact-equality assertion pins the full single-board `BYPASS`
    output (header line, condition line, pointer line, footer — the first exact-string arm in
    this suite), so a later edit to the multi-board layout that leaks a header or an extra
    line into the single-board form fails loudly rather than by inspection. The pre-existing
    suite runs unmodified as the behavioural half of the same guard.
11. **Read-only AST walk** (`WRITE_VERBS`, `:306`): the new argv literal is the same three
    tokens, so the `--json` and `--state` controls still hit and no write verb appears.
12. **Falsifiability drills** (the suite's own header): a hook that runs only the catch-all
    fails arms 1, 2, 4-7; a hook that runs listed boards sequentially with one shared stamp
    fails arm 1's stamp assertions; a hook that heads the catch-all block fails arm 10.

### Live verification (for the plan, at the v0.8.0 cut)

Without editing any real config until the installed plugin is ≥ 0.8.0: a scratch catch-all
`roadmap.toml` with absolute `workspace`/`tag_repo` and `boards` naming two real scoped
checkouts, run via `ROADMAP_CONFIG=<scratch> roadmap check --state <scratch state>` with a
fixed `--today`. Expected: the catch-all's own lines as today, then one headed block per
listed board that has drift (must-hit: at least one listed board known to be in drift that
session — e.g. a short horizon — appears under its header; must-miss: a listed board known
clean does not). Then a session opened at `$WS` after the real root config gains `boards`:
the SessionStart output names each listed board with drift. Pre-fix control: the same
session on the 0.7.0 install reports only the catch-all.

---

## Documentation

- **README** — "Before you start" gains item 9 (optional `boards` on the catch-all, after
  `scoped`); the glossary gains *listed board*; "Several products, one `bd` board" gains an
  H4 or paragraph *Hearing every board from one session* with the config block, the
  "cannot be combined with `scoped`" rule, what the three problem lines mean, that a
  different-workspace unscoped board is fine, and the upgrade order: **update the install
  before adding the key** — a `roadmap` older than 0.8.0 refuses it by name and the catch-all
  board goes silent in the hook (`roadmap: unavailable: … unknown key(s): boards` on stderr
  when run by hand), exactly as 0.7.0's note says for `scoped`. "The SessionStart hook" and
  "The drift check: `roadmap check`" each gain one sentence: with `boards`, the report covers
  every listed board, each on its own throttle. "Script against it" lists the two new JSON
  keys.
- **`roadmap.example.toml`** — the commented block above, after the `scoped` block.
- **`docs/DESIGN.md`** — "Several products, one board" gains a closing paragraph: the
  catch-all lists its siblings; the hook judges each on its own state; why the list is
  explicit; why `boards` and `scoped` exclude each other; the one exception to "Fail-open,
  always" is cross-referenced from that section too.
- **Hook docstring** — property 4 gains the listed-board exception; the seams block says
  `ROADMAP_CADENCE_STATE` is the catch-all's stamp only.
- **`CHANGELOG.md`** `[Unreleased]` — *Added*: `boards`; the hook and `roadmap check`
  report every listed board; `--json` carries `boards` and `workspace`. *Changed*: nothing
  for a board without the key (say so explicitly — byte-identical output is the contract).
- Optional one-clause notes in `commands/roadmap.md` (`check` line) and
  `skills/roadmap/SKILL.md` (`roadmap check` line): "every listed board, when the catch-all
  lists them".

---

## Version

`release:beads-roadmap-v0.8.0`; the release commit bumps `plugin.json` / `marketplace.json`
(the selftest's manifest-agreement arm pins both). A **minor**: a new config key, two new
JSON keys, no removed or renamed surface.

---

## Rollout and ordering

1. Code to `main`, pushed to `origin` (check `git remote -v` first, per the workspace rule).
2. Live-verify with a scratch config as above — no real `roadmap.toml` edited.
3. Cut and install 0.8.0; confirm `roadmap --version` names it.
4. **Only then** add `boards = [...]` to the root catch-all `roadmap.toml`, listing each
   scoped checkout. The scoped boards' configs are untouched. Until step 3 is done, adding
   the key makes the 0.7.0 install print `unknown key(s): boards` and the root session's
   hook goes silent — the README warns about this in the same words it uses for `scoped`.

---

## Rejected alternatives

- **Auto-discovery (glob for nested `roadmap.toml`).** Reports boards nobody asked about,
  walks a tree from a cwd the hook does not control, and has no answer for a board outside
  the root (a sibling checkout). An explicit list is one line per board and says exactly what
  a session should hear.
- **Several products in one config (`[[product]]` tables).** Every board already has a
  config, a state file, a `scoped` flag and a namespace of its own; duplicating those into
  the root file creates two sources of truth for each board and a migration for the four
  that exist. Listing directories reuses what 0.7.0 built.
- **`roadmap --all` (a multi-board text render).** The text board is one product's board by
  design, and the hook is the surface that needed to hear every board. A combined render
  would be a third consumer of the list with its own layout questions; nobody asked for it.

---

## Out of scope

- Any non-plugin consumer of the list — a workspace-level banner, a status line, or another
  tool that wants "which boards exist here". The list is readable from the catch-all's
  `--json` (`boards`), which is the whole export; nothing else is promised.
- `claim_labels` (the owner-label arm the 0.7.0 design deferred). Unrelated to this issue.
- Unifying the `auto_label_prefixes` validator (`:159-177`) with the extracted helper. Its
  bare-string message differs (`did you mean [%r]?`) and is pinned by an arm; the `claim_*`
  extraction is the only unification this design needs.
- Following a listed board's own `boards` (two levels, cycles, a visited set). One level is
  the design; if a workspace ever needs a tree, that is a new decision.
- Changing the catch-all's own output (a header, a directory). The single-board form is
  byte-identical by requirement.

---

## Open questions

1. **Does `bd list --json` tolerate N+1 concurrent readers on one database?** Not
   verifiable from this tree (the binary shells out to `bd`, `bin/roadmap:363-385`, and bd's
   own concurrency is outside it). If a reader fails under contention the board is reported
   `unavailable`, never silent, so the failure is visible; the live verification at the cut
   is where this is measured, and the fallback is a `max_workers` cap, which is a one-line
   change rather than a design change.
