# Product-scoped hotfix queue, unscheduled list and throughput — design

**Status** · proposed, awaiting approval; not yet implemented
**Scope** · `bin/roadmap`, `bin/roadmap-selftest.py`, `roadmap.example.toml`, `README.md`,
`docs/DESIGN.md`, `CHANGELOG.md`. The SessionStart hook and its suite are untouched.
**Canonical source** · this document, until the code lands; then the code
**Last verified** · 2026-10-14 (every premise re-probed against the tree at `4c75089` and a
fresh `bd list` dump of the reference workspace taken the same afternoon)
**Issue** · `github-bjxle` (release `beads-roadmap-v0.7.0`) · related `github-478rk` (shipped,
0.4.1), `github-kkq4a` M9 (shipped, 0.2.0), `github-7jn0v` (open, v0.8.0)

> Product names that would trip the decoupling scan at the end of the selftest are written
> generically here: "the mail product" is the product whose `roadmap.toml` sits at the
> reference workspace root, and `$WS` is that root. Everything else is named.

---

## What this is

`roadmap` renders ONE product's board from a `bd` database, keyed by `release_namespace`. On
the reference workspace five products share one database, each with its own `roadmap.toml`
(the mail product at the root; `kaimoku-website`, `beads-roadmap`, `kaimoku-infra` and
`console` in their checkouts, all with `workspace = $WS`). Three surfaces have no positive
ownership test, so an **unlabelled** row belongs to every board at once, and the throughput
denominator counts every close in the database while its numerator counts only this
product's. This design adds an ownership rule for unlabelled rows, opt-in per board, with
the unscoped board defined as the catch-all so severity is never hidden from every board.

---

## Premise verification

### Confirmed as written

| Claim in the issue | Evidence at `4c75089` |
| --- | --- |
| `unscheduled` has no ownership test | `bin/roadmap:474-481`: `issue_type in ('feature','epic') and not release_labels(i) and not is_backlog(i) and is_human_authored(i) and not is_deferred(i)`. Every predicate is a negative or type test; nothing says "mine". |
| `hotfix` has no ownership test | `:498-501`: `is_hotfix(i) and not release_labels(i) and not is_deferred(i)`. Same shape. |
| `backlog` is the model to follow | `:487-494`: `ns in backlog_namespaces(i)` — a positive, own-namespace test. |
| throughput numerator scoped, denominator not | `:949` `human = [i for i in closed_issues if is_human_authored(i, cfg)]` feeds `closed_%dd` (`:954`) and `rows14` (`:959`); `:955` and `:966` filter by `release_versions(i, cfg)`. M9 scoped the numerator and left the denominator. |
| the five leaking unscheduled rows | Live, every board: `github-6ew5z`, `github-p8e6s`, `github-yxk4w`, `github-8lox9`, `github-g6vst` — all `feature`, no labels, no `parent`, `github-*` ids. Tooling work for the meta-workspace itself. |
| false OFF-PLAN on `kaimoku-website` | Live: `OFF-PLAN -- 5% of the last 14 days of human-authored closes were in a release set.` (the issue says 6%; the number drifts with every close). `kaimoku-infra` fires at 8% and `console` at 7% for the same reason. `beads-roadmap` is inside its warm-up until 2026-10-28 and will then fire too. |
| `plan` already fixed for any-vs-own (`github-478rk`) | `_candidates` (`:653-667`) walks from this namespace's gating epics, so it is inherently scoped by ancestry. **No change needed there.** |

### Corrected — the leaking hotfix row is not the mail product's

The issue describes `github-5yqbl` as the mail product's hotfix. Its title names the mail product's images,
but its labels are `kaimoku-infra`, `release:kaimoku-infra-backlog`, `security`, `supply-chain`
and it has no parent. It is a P2 security-marked **feature**, so `is_hotfix` admits it, and a
backlog label never exempts a row from the queue (0.5.0, "severity outranks triage"). It is
**attributable by its own backlog label** to `kaimoku-infra`, and nothing else. That changes
what the fix must do: the rule's zero-hop arm — a row's own `release:<ns>-backlog` label names
its owner — removes it from four boards and keeps it on the fifth. The mail product's root
board also shows it today and, as the catch-all, will keep showing it (see below).

### Verified about the tool's inputs

`bd list --json` rows carry `parent` and dotted ids. Measured over all 7,976 rows: 3,178 dotted
ids, 3,204 rows with a `parent`, **0 rows where the two disagree**, 4 dotted ids with no
`parent` field. `descends_from()` already unions the two encodings; the upward walk here does
the same.

---

## Measurement (2026-10-14, `bd list` dump of the reference workspace)

Open family (`open,in_progress,blocked,deferred`) 1,200 rows; closed 6,776.

**Ids do not separate products.** `github-*` is 1,030 of 1,200 open rows (86%) and 5,897 of
6,776 closed (87%), shared by every product. Dotted epic namespaces exist (`mailsec` 31,
`homelab` 25, `rot` 23, `launch` 19, `michi` 17, `console` 16 open, …) but cover the minority.

**Labels.** Ten release/backlog namespaces on open rows: the mail product 185, `kaimoku-infra`
151, `console` 31, `michi` 17, `kaimoku-website` 13, `meta` 11, `beads-roadmap` 6, three others
≤ 5. Five of the ten have a `roadmap.toml`. Repo-style owner labels exist but are sparse: the
mail product's name as a plain label on 19 open rows, `kaimoku-infra` on 2, a build-agent tool
on 2 — too thin to be the rule, so an owner-label arm is deferred (follow-up below).

**The six leaking rows.** All five unscheduled rows are orphans: no labels, no parent, `github-`
id. Title prefixes: three have none a product would claim (`bin/secrets-gen:`,
`secret rotate:`, `secret audit --wire:`), one is a build-agent tool's name, one is `common:`.
**No product's board should own them.** The hotfix row `github-5yqbl` is owned by
`kaimoku-infra` via its own backlog label.

**Closes, human-authored under the root board's `auto_label_prefixes`.**

| window | closes | own release/backlog label | nearest labelled ancestor | title prefix only | nothing |
| --- | --- | --- | --- | --- | --- |
| 7 d | 118 | 104 (mail 83 · infra 19 · beads-roadmap 2) | 4 | 6 | 4 |
| 14 d | 220 | 184 (mail 128 · infra 27 · website 12 · console 15 · beads-roadmap 2) | 5 | 17 | 14 |
| 28 d | 530 | 324 (mail 210 · infra 40 · website 40 · console 15 · beads-roadmap 3 · michi 16) | 12 | 59 | 134 |

**On-plan share, 14 d, today vs. under the rule below** (own label + ancestor + title prefix):
mail 55% → 88–90% · `kaimoku-website` 5% → **100%** (12 of 12) · `beads-roadmap` 1% → 100% (2 of
2; warm-up until 10-28 regardless) · `kaimoku-infra` 8% → 59% · `console` 7% → 75%. Every false
OFF-PLAN stops; none becomes a false clean (the mail product's own 55% is real and unchanged).

**Title-prefix convention, among rows already labelled for a namespace:** `beads-roadmap` 8 of
9 titles start `beads-roadmap:`; `kaimoku-website` 25 of 53; the mail product 182 of 395;
`kaimoku-infra` 30 of 192; **`console` 0 of 46** — its rows are prefixed `kaimoku-lens:` /
`kaimoku-console:`. Where the convention is used it is precise (one cross-product miss seen:
a row prefixed with the mail product's name but labelled `kaimoku-website`). Because the
prefix is not derivable from the namespace, it must be **configured, never guessed**.

**Ancestor inheritance reach,** open unlabelled non-deferred rows whose nearest labelled
ancestor names a product: mail 22, `meta` 19, probe 5, `kaimoku-infra` 3, `console` 3,
`kaimoku-website` 1 — 53 rows that no label on the row itself would attribute.

**Expected boards after the change** (scoped boards claim `<name>:` title prefixes;
`kaimoku-infra` also `homelab-` ids; `console` claims `kaimoku-lens:`/`kaimoku-console:`):

| board | unscheduled | hotfix | 7 d closed / in release | 14 d share |
| --- | --- | --- | --- | --- |
| root (mail, **unscoped**) | 5 (unchanged) | 1 (unchanged) | 118 / 78 (unchanged) | 55% (unchanged) |
| `kaimoku-website` | 0 | 0 | 0 / 0 | 100% — OFF-PLAN gone |
| `beads-roadmap` | 0 | 0 | 2 / 2 | warm-up (then 100%) |
| `kaimoku-infra` (if scoped) | 0 | **1 — `github-5yqbl` stays** | 21 / 10 | 59% |
| `console` (if scoped) | 0 | 0 | 2 / 0 | 75% |

The `kaimoku-infra` row is the live must-hit control for "scoping never hides severity from the
owning board". Live counts drift by the minute as rows are updated (`updated_at` is the close
proxy), so the verification compares two binaries run back-to-back with the same `--today`,
not against this table.

---

## Decision — the ownership rule

A row is **owned** by the configured namespace `N` when any of these holds, checked in order
and OR-ed:

1. **Own label.** The row carries `release:N-v*` or `release:N-backlog`. (Zero hops. This is
   what attributes `github-5yqbl` to `kaimoku-infra`.)
2. **Nearest labelled ancestor.** Walking up through `parent` (falling back to the dotted
   parent of the id when `parent` is absent, and continuing on the bare id when an
   intermediate row is missing), through open **and closed** rows, the first ancestor that
   carries any release or backlog label carries one in `N`. *Nearest* wins: a sub-epic
   relabelled to another product takes its subtree with it. A shipped epic's unlabelled
   children are still its product's, which is why closed rows are in the index.
3. **Configured claim.** The title starts with one of `claim_title_prefixes`, or the id starts
   with one of `claim_id_prefixes`. Literal, case-sensitive `str.startswith`, the same
   semantics as `auto_label_prefixes`.

Ownership is consulted **only when `scoped = true`.** On a board without that key nothing is
consulted, nothing is filtered, and the text render is byte-identical to today (hard
requirement: most installs have one product per database). This is also what makes the
catch-all exist, below.

### Why opt-in and configured, not derived

Deriving "scoped" from "the board carries more than one namespace" would change the output of
every mixed workspace on upgrade, and the single-product default would stop being
byte-identical. Deriving the title prefix from the namespace is wrong on the one board where it
matters most (`console`). Both are config values the tool would be guessing, and the tool's
standing rule is that a guessed config value renders a clean, wrong board. The `init` refusal on
a multi-namespace board already routes shared-workspace users to a hand-written config; the
new keys are added there by hand too.

### The catch-all: rows claimed by no board

A board **without** `scoped = true` shows every unlabelled row, exactly as today. In a shared
workspace, **leave exactly one board unscoped** — the product the database was created for (on
the reference workspace, the root board, which the SessionStart hook also runs from). An
orphan P0 bug therefore appears on exactly that board and in that hook, never on none, and never
on all five.

If every board in a workspace is scoped, an orphan appears nowhere. **The tool cannot detect
this from one `roadmap.toml`**: by design it reads one config and knows nothing of its
siblings' claims, and a scoped board cannot tell "unowned by anyone" from "owned by the
catch-all by convention" — so a count of "rows not mine" would reintroduce the exact leak this
fixes, in count form. The decision is to **document the constraint and mark scoped boards
visibly** (header suffix ` · scoped`, JSON `scoped: true`) rather than invent a cross-config
reader here; detection belongs with the multi-product hook work (`github-7jn0v`, listed as a
follow-up). The root board stays unscoped on the reference workspace and therefore stays
"unchanged", which is the issue's own must-hit control.

### What does not change

- **Counts** (`versions`, `in_release_*`, `curve`) stay `release_versions()`-filtered — M9.
- **`backlog`** is already own-namespace.
- **`plan`** (`_candidates`) walks from this namespace's gating epics — already scoped by
  ancestry (`github-478rk`). Not touched.
- **`_namespace_mismatch`** keeps the agnostic helper — its detector depends on it.
- **"Already scheduled" stays any-namespace** (`release_labels`, `is_backlog`) on the three
  surfaces — `github-478rk`'s rule. Ownership is a second, positive test added beside it, not
  a replacement.
- **The SessionStart hook** reads `conditions`, `state_path`, `unconfigured`,
  `legacy_state_available` from the JSON and nothing else; conditions 3, 4 and 5 inherit the
  scoping through the model. No hook change, no hook-suite change.

---

## Config surface

Three new keys in `CONFIG_KEYS`, all optional, validated by name and type like `horizon`:

```toml
# Optional. On a bd board shared by several products, show only the rows this
# product OWNS: rows labelled for this namespace, rows whose nearest labelled
# ancestor epic is, and rows matched by the claim lists below. Leave it unset
# on exactly one board per shared board -- that board is the catch-all and
# shows every unlabelled row, so an unowned P0 bug is always visible somewhere.
# scoped = true
# claim_title_prefixes = ["acme-app:"]     # literal, case-sensitive title prefixes
# claim_id_prefixes = ["acme-"]            # literal id prefixes; include the separator
```

Validation, each refused **by name** with a `RoadmapUnavailable` (fail-open, loud on stderr):

- `scoped` must be a `bool` (`"true"` and `1` are refused — same reasoning as `horizon = true`).
- each `claim_*` must be a list of strings; a bare string is refused (the `str.startswith`
  tuple trap `auto_label_prefixes` documents); a non-string element is refused.
- an **empty string element** is refused: `''` is a prefix of every title and id, so one
  stray `""` would claim the whole board and silently un-scope it — the clean-wrong signal.
- a non-empty `claim_*` list with `scoped` absent or `false` is refused: a rule with no switch
  is a likely mistake, and the house style is to refuse rather than infer the switch.
- `scoped = true` with no claims is legal: ancestry-and-labels-only scope.

`load_config` returns `scoped` (bool, default `False`) and the two lists as tuples (default
`()`). Hand-built configs — `TEST_CFG`, `probe_layout`'s — lack the keys, so every read is
`cfg.get('scoped')` / `cfg.get('claim_…') or ()`. `cmd_init` does not write them (it refuses on
a multi-namespace board, which is the only board that needs them).

---

## Model and render changes

New helpers beside `is_deferred`, cited `github-bjxle`:

- `ownership_index(open_issues, closed_issues)` → `{id: row}` over both reads.
- `_parent_id(iid, row)` → `row['parent']`, else the dotted parent of `iid`, else `None`.
  Works on a bare id when `row` is `None`, so a missing intermediate row does not end the walk.
- `owner_namespaces(issue, byid)` → the namespace set of the row's own release/backlog labels,
  else of the nearest ancestor carrying any, else `set()`. Cycle-guarded like `descends_from`.
- `is_owned(issue, byid, cfg=None)` → arm 1/2 via `owner_namespaces`, arm 3 via the claim
  tuples.

`build_model`: `scoped = bool((CONFIG or {}).get('scoped'))`; when scoped, build the index once
and add `and owned(i)` to **unscheduled** and **hotfix** only. `model['scoped']` is recorded.

`compute_throughput`: `human` gains the same `is_owned` filter when `(cfg or {}).get('scoped')`,
so `closed_*d`, `rows14` and `on_plan_share_14d` all follow. The index is built locally from
the two lists it already receives; the signature is unchanged. `tags_*d` and `curve` are already
per-product.

`render_board`: header gains ` · scoped` when `model['scoped']`; nothing else moves. Unscoped
output is byte-identical. `render_json`: one new key, `"scoped": bool`. **This is the one
deliberate deviation from "identical"** — the JSON of an unscoped board gains `"scoped": false`,
as it gained `horizon` and `state_path` in earlier releases; the hook ignores unknown keys.

---

## Known miscounts, accepted

- **A row may be owned by two boards** (a title prefixed with product A's name under product
  B's epic). It is shown and counted on both. Shown twice beats shown nowhere; the alternative
  is a precedence rule nobody asked for.
- **Title prefixes are a convention, not a field.** A product that stops prefixing titles sees
  its new unlabelled rows drop off its scoped unscheduled list until labelled or parented.
  That is the trade for having no repo field in `bd`, and it is visible (the header says
  `scoped`).
- **All boards scoped hides orphans.** Documented, not detected — see the catch-all section.

---

## Test coverage

All in `bin/roadmap-selftest.py`, every rule in both directions, fixtures in `acme-app` with
`other-app` as the foreign namespace:

1. **Config**: defaults (`False`, `()`, `()`); `scoped = true` alone loads; claims load as
   tuples; refusals by name for wrong `scoped` type (string, int), bare-string claim,
   non-string element, empty-string element, claims without `scoped`.
2. **`is_owned` unit arms**: own backlog label (hit) · child via `parent` (hit) · dotted id with
   no `parent` field (hit) · two hops through an unlabelled middle row (hit) · child of a
   **closed** labelled epic (hit) · title claim (hit) · id claim (hit) · foreign epic's child
   (miss) · **nearest** labelled ancestor foreign under an own epic (miss) · orphan (miss) ·
   foreign backlogged security row, the `github-5yqbl` shape (miss) · with empty claim tuples
   the title/id rows become misses while the ancestry row stays a hit (proves which arm
   matched).
3. **`build_model`** on a two-namespace fixture under a scoped config and, as the control,
   under `TEST_CFG`: scoped unscheduled keeps the owned rows and drops orphan / foreign-child /
   nearest-foreign; scoped hotfix keeps an owned P1 bug and an own-backlog security row, drops
   the foreign-backlog security row and an **unowned P1 bug**; the unscoped render lists all
   of those (today's behaviour, and the catch-all's job); `versions` identical in both.
4. **`compute_throughput`**: scoped `closed_7d` excludes a foreign-labelled and an orphan close
   and includes an unlabelled child of a closed own epic and a title-claimed close;
   `in_release_7d` unchanged by scoping; `on_plan_share_14d` 2/4 scoped vs 2/6 unscoped.
5. **Render**: header suffix present iff scoped; the existing fixture's header is exactly
   `ROADMAP · acme-app · cut v0.15.0`; JSON `scoped` true/false.
6. **Mutation drills** (house style, after committing): drop `and owned(i)` from the hotfix
   comprehension — suite must fail; drop the `is_owned` clause from `human` — suite must fail.

The full existing suite is the byte-identity guard: `TEST_CFG` has no `scoped` key, so every
pre-existing assertion runs the unscoped path. The live diff (plan Task 7) is the second half.

---

## Documentation

- **README** — "Before you start" item 8 (optional `scoped = true` on a shared board);
  glossary rows *owned*, *scoped board*, *catch-all board*; "Reading the board" notes on
  HOTFIX QUEUE, UNSCHEDULED and THROUGHPUT; a new H3 **"Several products, one `bd` board"**
  after "Common tasks" with the three arms, the config, the exactly-one-catch-all rule, the
  all-scoped caveat, and the older-binary warning (a binary before 0.7.0 refuses the keys by
  name and the board goes silent); "Script against it" mentions the `scoped` JSON key.
- **`roadmap.example.toml`** — the commented block above, after `horizon`.
- **`docs/DESIGN.md`** — new section "Several products, one board": ownership is derived like
  everything else, why opt-in, the catch-all, why one config cannot detect all-scoped.
- **`CHANGELOG.md`** `[Unreleased]` — *Added*: `scoped` and the claim keys; *Fixed*: the
  throughput denominator and the leaking surfaces, naming the false OFF-PLAN.
- Optional one-clause notes in `commands/roadmap.md` / `skills/roadmap/SKILL.md` ("on a scoped
  board, this product's rows").

---

## Version

No bump in this issue. `release:beads-roadmap-v0.7.0` holds three issues; the release commit
bumps `plugin.json` / `marketplace.json`. 0.7.0 is correctly a **minor**: new config keys and
a new JSON key.

---

## Rollout and ordering

1. Code to `main`, pushed to `origin` (GitHub; check `git remote -v` first).
2. Live-verify **without editing any real config**: `ROADMAP_CONFIG=<scratch toml>` with
   absolute `workspace` / `tag_repo`, `--state` under the scratchpad, fixed `--today`.
3. **Only after the installed plugin is ≥ 0.7.0**: add `scoped = true` and
   `claim_title_prefixes` to `beads-roadmap/roadmap.toml` (gitignored, local) and
   `kaimoku-website/roadmap.toml` (tracked in that repo — follow that repo's branch and push
   rules). Until then a 0.6.0 binary run from those directories prints
   `roadmap: unavailable: … unknown key(s): scoped` and renders nothing; the root hook is
   unaffected because the root config does not change. `kaimoku-infra` and `console` are the
   same two-line edit each and are left to the user's decision.

---

## Open questions for the user

1. Scope `kaimoku-infra` and `console` in the same rollout, or file follow-ups? Measured
   effect: their false OFF-PLAN (8% / 7%) becomes 59% / 75% and stops firing; `github-5yqbl`
   stays on `kaimoku-infra`.
2. Rollout ordering: wait for the 0.7.0 plugin install before editing the two configs
   (recommended), or accept the loud-but-empty window from the installed 0.6.0?
3. Accept "exactly one unscoped board" as a documented convention for now, with detection
   deferred to `github-7jn0v`?

## Separable follow-ups (not filed; for the user to file)

- `claim_labels` (owner label arm): measured 19 + 2 + 2 open rows carry a repo-style label
  today; add when the convention is adopted.
- Workspace-level detection of "every board scoped, orphan severe rows on no board" — belongs
  with the multi-product hook (`github-7jn0v`), which is the first thing that reads more than
  one `roadmap.toml`.
- `cmd_init`'s multi-namespace refusal text could point at `scoped` and the README section.
- `kaimoku-website` has an untracked `.roadmap-state.json`; the README asks for it to be
  gitignored.
- Unify the list-of-strings validator with `auto_label_prefixes`' (left separate here to keep
  that code and its messages byte-identical).
