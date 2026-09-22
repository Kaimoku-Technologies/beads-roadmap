# Deferred hardening from the cold-start review — design

**Status** · approved, not yet implemented
**Scope** · `bin/roadmap`, `bin/roadmap-selftest.py`, `hooks/roadmap-cadence.py`,
`hooks/test_roadmap_cadence.py`, `README.md`, `CHANGELOG.md`, `.gitignore`, both plugin manifests
**Canonical source** · this document, until the code lands; then the code
**Last verified** · 2026-09-21 (every premise below re-probed against the tree at `9bccc8b`)
**Issue** · `github-kkq4a`

---

## What this is

`github-kkq4a` collects the findings from the final whole-branch review of
beads-roadmap that were deliberately *not* fixed in the first wave. That wave
took the two Criticals (init guessing `release_namespace`; `BEADS_DIR`
overriding `workspace`) plus I4/I6/I7/I8. Eight items remained.

Before designing anything, every premise was re-probed against the tree rather
than taken from the ticket. **Two of the eight did not survive**, and one new
defect was found and filed separately. That section comes first, because it
changes what gets built.

---

## Premise verification

### Confirmed as written

| Item | Evidence |
| --- | --- |
| **I3** | `DEFAULT_STATE = os.path.expanduser('~/.claude/roadmap-cadence-state.json')` (`bin/roadmap`), and `baseline_key(v)` returns `'%d.%d.%d' % v` — a bare version with no namespace. |
| **I5** | `probe_layout` appends *no semver v\* tags* to `ambiguous`, so `cmd_init` refuses. The runtime accepts it: with `tags == []`, `cut` is `None`, so `above = sorted(v for v in all_versions if cut is None or v > cut)` admits **every** version and `in_flight = above[0]` is the **lowest**. |
| **M9** | `bin/roadmap:749` and `:760` call `release_labels(i)` (namespace-agnostic) where versions use `release_versions(i, cfg)` (namespace-filtered). The issue cites `:637,648`; line numbers drifted, the code is identical. |
| **M10** | `command -v roadmap` resolves to `~/.claude/plugins/cache/beads-roadmap/roadmap/0.1.2/bin/roadmap`. That directory is on `PATH` **only** because Claude Code injects plugin `bin/` into the session. Outside a session the README's `roadmap init` does not resolve. |
| **M11** | `README.md`'s Requirements section names Python 3.11+ and nothing about `bd`. |

### Corrected — the `errors=replace` comment is not overclaiming

The review held that the decoupling scan's comment — *"a REPLACEMENT byte
cannot hide a needle since none of the needles contain one"* — proves
*fabricate* but is false for *hide*, because "a replacement byte inside a
needle's span splits it."

Probed directly. `NEEDLE` below stands for one of the four-or-more-character
ASCII strings in `_COUPLED` — written as a placeholder rather than spelled out,
because this document is itself a shipped `.md` file that the scan walks, and a
literal here would trip the very gate it is describing.

| bytes | needle in bytes | needle after decode |
| --- | --- | --- |
| `NEEDLE` | yes | **yes** |
| `NEEDLE` + `\xff` | yes | **yes** |
| `\xff` + `NEEDLE` | yes | **yes** |
| `\xf0` + `NEEDLE` | yes | **yes** |
| `\xf0\x90` + `NEEDLE` | yes | **yes** |
| `\xf0\x90\x80` + `NEEDLE` | yes | **yes** |
| `NEEDLE` with one interior byte overwritten by `\xff` | no | no |
| `NEEDLE` encoded as UTF-16LE / UTF-16BE | no | no |
| `NEEDLE` split by a literal U+FFFD | no | no |

Python's UTF-8 decoder never folds a byte `< 0x80` into a replacement's
maximal subpart, so an **all-ASCII** needle cannot be split by one. Every
apparent "hide" in the lower block is a case where the needle was never in the
bytes — nothing was hidden because nothing was there.

The claim is therefore true, but it is true *because the needles are ASCII*,
and the comment does not say so. A future non-ASCII needle would void it
silently. **That** is the real defect, and it is much smaller than reported.

### Corrected — the fail-open wrapper is partly tested already

The issue states `main()`'s `configure(load_config(...))` wrapper "has no
automated test" because `_run_main`'s stub makes `load_config` always succeed.
Stale: `bin/roadmap-selftest.py:1002-1034` already drives that branch *past*
the stub, on both arms, with a must-miss control.

The residual gap is narrower and specific:

- `_unc_err` and `_bad_err` are captured and **never asserted** — the "reason
  reaches stderr" arm is uncovered on this path.
- Both existing tests pass `--json`. The **text-mode** branch of the same
  `except` is never run.

### Found while verifying, filed separately — `github-aci1y`

`load_issues()` issues exactly two reads, `--status=open` and
`--status=closed`. `bd`'s status filter is exact, not a family. Measured on
the reference workspace 2026-09-21: `open 858 · in_progress 1 · blocked 1 ·
deferred 55 · closed 6347` — **57 rows visible to neither read**. A versioned
issue moved to `in_progress` silently leaves its version's *N open* count
without being counted done.

Out of scope here; filed as `github-aci1y` so it is not lost.

---

## 1 · I3 — one global state file for all workspaces

### The defect

`--state` defaults to `~/.claude/roadmap-cadence-state.json` for both the CLI
and the SessionStart hook, and nothing in it is keyed by workspace. The
collision surface is **five fields, not one**:

| field | written by | effect of a collision |
| --- | --- | --- |
| `last_cut` | `refresh_baselines` | a foreign cut fires a spurious condition 6 and mis-baselines creep |
| `baselines` | `refresh_baselines`, `roadmap pin` | bare-version keys — two products at `1.0.0` overwrite each other |
| `convention_start` | `load_state` | one product's install date governs the other's 14-day warm-up |
| `last_reported_at` | hook `write_stamp` | one workspace's report throttles every other |
| `unconfigured_reported` | hook `mark_nudged` | the one-time init nudge fires for the first workspace only |

The reviewer hit this by accident: a run from a scratch repo overwrote the live
`last_cut` from `0.16.0` to `1.0.0`. Keying `baselines` by namespace would have
fixed one row of five and left the observed symptom in place.

### The fix

The state file moves **next to `roadmap.toml`** — one config, one state file.

- `load_config()` adds `'config_path': os.path.realpath(path)` to its
  **returned dict**. `CONFIG_KEYS` validates the *raw TOML* and is untouched,
  so hand-written configs are unaffected and the unknown-key guard still
  rejects `config_path` if a user writes it.
- New `default_state_path(cfg)` → `<dirname(config_path)>/.roadmap-state.json`.
  When `config_path` is absent — a caller that configured by hand, including
  the suite's `TEST_CFG` — it falls back to the legacy global path. No call
  site can `KeyError`.
- `--state` defaults to `None`. The real default resolves in `main()` *after*
  `configure(load_config(...))`, because it depends on the config.
- `render_json` gains `"state_path"`, the resolved absolute path.

### Hook contract

The hook stops computing the path independently:

1. Run `[binary, '--json']` with **no** `--state`.
2. Read `payload['state_path']` and use it for `read_stamp` / `write_stamp`.
3. If that key is absent — the `unavailable` or `unconfigured` payload, or an
   older binary — fall back to the legacy global path.

`unconfigured_reported` therefore **stays global, deliberately**: an install
with no `roadmap.toml` has no config directory for state to sit beside. The
known consequence is that a second never-configured workspace is not nudged
again. That is pre-existing behaviour, it is recorded here rather than fixed,
and it is the correct trade against inventing a config location for an install
that has none.

`ROADMAP_CADENCE_STATE` continues to force both the subprocess argument and
the stamp path, so the existing test seams keep working unchanged.

### Migration — none, on purpose

The reference deployment's state carries a real 14-issue baseline for
`0.17.0`. Auto-seeding the new per-config file from the legacy global one
would hand **every** workspace a copy of it; two products would each inherit
the other's baseline.

This codebase already treats `no baseline yet` as an honest state worth
having — `refresh_baselines` refuses to invent a plan-at-cut-time for a
version that was already in flight, and `render_board` distinguishes four
creep states rather than three, precisely so a false baseline cannot render as
a clean one. Auto-seeding would manufacture exactly the wrong baseline that
design refuses.

Instead: when the resolved state path does not exist and the legacy global
file does, print a one-time notice naming both paths and let the human decide.
The copy for this deployment is a deploy step, verified by re-reading the
baseline afterwards.

---

## 2 · I5 — init and the runtime disagree about the same condition

### The defect

`init` refuses a repo with no semver `v*` tags and tells the user to write
`roadmap.toml` by hand — which routes them **past the namespace probe**, the
one guard that genuinely cannot be replaced by a guess. The runtime then
accepts the same repo and renders the *lowest* labelled version as in flight,
so an already-shipped release appears to be in progress.

Two entry points, two standards, and the refusal pushes users toward the
weaker one.

### The fix — init accepts what the runtime accepts; the runtime gets honest

A new repo with labels and no tag yet is a legitimate, expected state. Both
halves move toward describing it accurately.

**`probe_layout`** grows a `warnings` list alongside `ambiguous`. The no-tags
reason moves to `warnings`. The namespace probe stays in `ambiguous` — it
remains the only hard refusal.

**`cmd_init`** prints warnings after the `Detected:` block and **still writes**
the file, returning 0.

**`build_model`** learns `no_tags = not tags`. When true:

- `in_flight = None` — nothing has been cut, so nothing is in flight.
- `planned` becomes every non-patch version in `above`, not `above[1:]` —
  nothing is behind us, so everything labelled is ahead.
- `model['no_tags'] = True` for the condition below.

**New condition 8**, `bypass: True` (same reasoning as conditions 1 and 7 — a
clean-looking board that is silently measuring nothing is the failure this
design exists to refuse):

```
NO VERSION TAGS -- <tag_repo> carries no semver v* tags, so nothing has been cut.
  No version is in flight, and every version below is shown as PLANNED.
  Cut a tag (e.g. `git tag v0.1.0`) for roadmap to tell shipped from planned.
```

### Knock-ons, traced

| site | behaviour with `in_flight = None` | verdict |
| --- | --- | --- |
| condition 1 | `nxt` is `None`; prints `<version>` | already handled |
| condition 5 | prints `(no in-flight version)` | already handled |
| `render_board` | skips the IN FLIGHT block; hotfix header shows `(none)`; `creep: n/a — no version in flight` | already handled |
| `compute_throughput` | `curve` stays `[]` | already handled |
| `refresh_baselines` | `cut_key` is `None`, so the `last_cut is None` branch is taken every run and `cut_advanced` stays `False` | **correct** — no tag was cut |
| `roadmap plan` | `pick = model['planned']`, which is non-empty | already handled |

Conditions 1 and 8 overlap only where they should. Condition 1 keys on `not
planned`, so on a tagless board that *does* carry release labels it now stays
quiet — `planned` is non-empty — and condition 8 alone explains the state. On a
board with **neither** tags nor labels both fire, which is correct: an empty
horizon and an untagged repo are two separate things a cold install needs told,
and both are `bypass: True` precisely so a cold install hears them.

---

## 3 · M9 — namespace-agnostic counts in throughput and condition 3

`bin/roadmap:749` and `:760` replace `release_labels(i)` with
`release_versions(i, cfg)`, so `in_release_7d`, `in_release_28d` and
`on_plan_share_14d` count only this product's release sets. In a shared
workspace another product's labels no longer count toward your on-plan share.

**`_namespace_mismatch` at `:269` keeps `release_labels` — that is its entire
detector.** It exists to find issues carrying a release label in *some other*
namespace, which is only expressible with the agnostic helper. A test pins
this so a later consistency cleanup cannot quietly break it.

The "unsurfaced tell" the issue describes — `>0 in a release set` printed
beside `versions: {}` — resolves itself: those counts go to 0 in the mismatch
case, and condition 7 fires with a named diagnosis instead of a number the
reader has to interpret.

---

## 4 · Test coverage

Three additions, matching the corrected premises above.

1. **The `load_config` fail-open branch, the two arms that are actually
   uncovered.** Assert `roadmap: unavailable:` reaches **stderr** on both the
   `unconfigured` and malformed-config runs (today `_unc_err` / `_bad_err` are
   captured and dropped), and add one **text-mode** run of the same branch
   asserting exit 0, an empty stdout, and the reason on stderr.

2. **`compute_throughput`'s `convention_start` fallback**, never exercised
   because every call site passes it explicitly. Two arms: `cfg` supplied with
   `convention_start` omitted, and `cfg=None` with no module `CONFIG`.

3. **The ASCII precondition on `scan_tree`.** A test proving a needle survives
   an adjacent invalid byte and a truncated `\xf0\x90\x80` lead, plus a
   must-miss showing `ku\xffu` is *not* reported. The comment is amended to
   state that the property holds because every needle is ASCII, and that a
   non-ASCII needle would void it — rather than softened to a weaker claim
   than the truth.

New behaviour from sections 1–3 carries its own tests: the resolved state path
and its fallback, `state_path` in the JSON payload, the hook reading it back,
`no_tags` model semantics, condition 8, and the namespace-filtered counts with
`_namespace_mismatch` pinned to the agnostic helper.

---

## 5 · M10 / M11 — documentation

`README.md` gains:

- **Where `roadmap.toml` goes**: `init` writes to the **current working
  directory**. Only `roadmap.example.toml`'s first comment said so.
- **How `roadmap` resolves**: bare `roadmap` works because Claude Code injects
  the plugin's `bin/` into the session `PATH`. Show `/roadmap init` as the
  in-session form, and give the explicit path form for a shell outside one.
- **A `bd` requirements subsection**: the exact surface consumed —
  `bd list --status=<s> -n 0 --json`, and the row fields read (`id`, `title`,
  `labels`, `issue_type`, `priority`, `parent`, `updated_at`) — stating
  **verified against bd 1.2.2; no lower bound has been tested**. No invented
  floor: claiming a minimum that was never exercised is the overclaiming this
  codebase refuses, and the honest statement is more useful to someone
  checking their own version.
- **`.gitignore` guidance** for `.roadmap-state.json`, with the line added to
  this repo's own `.gitignore` too.

`CHANGELOG.md` is added (the repo has none) in Keep a Changelog form, with an
entry for this release and a brief retrospective entry for `0.1.0`–`0.1.2`
reconstructed from the git log.

---

## Version

`0.1.2` → **`0.2.0`** in `.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json`. Minor, not patch: the default state path
moves and `in_flight` semantics change on a tagless repo. Both are visible
behaviour changes, and a user with an existing install sees a reset baseline
unless they perform the documented copy.

---

## Testing

`python3 bin/roadmap-selftest.py` and `python3 hooks/test_roadmap_cadence.py`,
run on the pinned 3.11.16 (`.mise.toml`). CI runs both on 3.11, 3.12 and 3.13.
No new dependency; both suites stay standard-library-only and feed synthetic
rows, so neither needs `bd` or a git fixture.
