# roadmap

A Claude Code plugin that renders a product roadmap **derived** from a
[beads](https://github.com/steveyegge/beads) (`bd`) issue board on every run —
versions, a hotfix queue, unscheduled work, and scope creep against a pinned
baseline. It ships a SessionStart hook that reports planning drift and stays
silent when there is none.

The tool never writes to `bd` — no label, no comment, no field. The only
local state it keeps is a small state file next to your `roadmap.toml` (the
scope-creep baseline plus the SessionStart hook's throttle stamp), and that
file exists precisely so it can be compared against a fresh `bd` read on the
next run, not as a cache of it.

## Install

```
/plugin marketplace add Kaimoku-Technologies/beads-roadmap
/plugin install roadmap@beads-roadmap
```

(If you're working from a local checkout instead of a marketplace listing,
point Claude Code's plugin loader at this directory directly.)

## Upgrading from 0.1.x

0.2.0 moved the state file. It was one file per machine:

```
~/.claude/roadmap-cadence-state.json
```

and it is now one per install, beside your `roadmap.toml`:

```
<the directory holding roadmap.toml>/.roadmap-state.json
```

**Nothing is migrated automatically, on purpose.** The old file was shared by
every workspace on the machine, so it holds whatever the last workspace to run
`roadmap` left there — in most workspaces, *another* product's numbers.
Seeding every install from it would hand them all the same baselines, and a
wrong baseline is the false-clean signal this tool exists to prevent.

Copy it **only if this is the workspace that was using it**:

```
cp ~/.claude/roadmap-cadence-state.json <dir>/.roadmap-state.json
```

`roadmap` prints that line with both paths filled in the first time it runs
with no state file beside your config, and the SessionStart hook says the same
thing once in-session.

**Ignoring it is a legitimate choice** — and in every workspace that was not
the one writing that file, it is the right one. What you give up — and the one
thing you do not:

- **The scope-creep baselines.** The version in flight reports `no baseline
  yet` until you re-baseline it deliberately with `roadmap pin v1.2.0`, or
  until the next tag is cut and the tool snapshots the new version itself.
- **`last_cut`.** The first run records where the tag train stands now and
  baselines nothing, so a tag cut between your last 0.1.x run and this one
  goes unannounced.
- **Not the warm-up start**, as long as your `roadmap.toml` sets
  `convention_start` — `roadmap init` writes it, and an absent state file is
  seeded from it. If you hand-wrote a config without that key, warm-up
  restarts from today and the off-plan condition stays quiet for 14 days.

Add `.roadmap-state.json` to your `.gitignore`. Once every workspace you care
about has been dealt with, the old file can be deleted; the only thing still
reading that path is the fallback for an install with no `roadmap.toml` at all.

## First run: `roadmap init`

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

It probes the directory layout — is this a git checkout, does it carry
semver `v*` tags — and reads the release-label namespace off the **board
itself** (via `bd list`, not the directory name): if the board carries
release labels in exactly one namespace, that's the evidence it uses. It
prints what it found and writes `roadmap.toml`.

A repo with **no `v*` tags yet** doesn't stop it: `init` prints a warning and
writes `roadmap.toml` anyway. Refusing there used to send people off to
hand-write the file, which walks straight past the namespace probe — the one
thing here that genuinely cannot be guessed. It still **refuses to guess**,
writing nothing, on an actually ambiguous layout: no `.git`, or a board whose
release labels are absent or span more than one namespace. (The directory
name appears only as a last-resort suggestion in that refusal, never as a
value it writes on its own.) In that case, copy `roadmap.example.toml` and
fill in the three keys by hand.

## Using it

Inside a Claude Code session, use the `/roadmap` slash command, or just ask
("what should we ship next?", "is this a hotfix?") and the bundled skill runs
it for you. In a shell, the same commands are `roadmap …` (by full path
outside a session; see above).

| Command | What it shows |
| --- | --- |
| `/roadmap` | The whole board (see below) |
| `/roadmap v1.2.0` | One version in detail: every open issue, gating epics, counts |
| `/roadmap hotfix` | The full hotfix queue (the board shows the top three) |
| `/roadmap unscheduled` | Every feature and epic with no version (the board shows the top three) |
| `/roadmap plan` | Proposes what to put in the next planned version |
| `/roadmap plan v1.2.0` | The same for a specific version |
| `/roadmap pin v1.2.0` | Re-baselines that version's scope-creep snapshot |
| `/roadmap init` | Writes `roadmap.toml` (once per workspace, see above) |
| `/roadmap --version` | The plugin version, and the path of the `roadmap` that answered |

Every command rebuilds everything from a fresh `bd` read, so there is nothing
to refresh or sync: run it whenever you want the current picture.

### Reading the board

An illustrative board (the issues are invented; the layout is real):

```
ROADMAP · acme-app · cut v1.1.0

  IN FLIGHT
     v1.2.0       3 open · 5 done
        P1 bug      Login fails when the session cookie is expired
        P2 feature  Export reports as CSV
        P3 task     Rename the settings page
        gates: acme-5      Reporting overhaul

  HOTFIX QUEUE v1.2.1 (implied)   1 unversioned · cuttable independently
    P1 bug       acme-42 Password reset link never arrives

  PLANNED
     v1.3.0       4 open · 0 done
        P2 feature  Single sign-on
        P2 feature  Dark mode
        …2 more · /roadmap v1.3.0

  UNSCHEDULED  6 features/epics carry no version
    P1 feature   acme-51 Audit log
    P2 feature   acme-60 Slack notifications
    P2 epic      acme-61 Mobile app
     …3 more · /roadmap unscheduled

  THROUGHPUT    7d    14 closed ·   9 in a release set ·  1 tags cut
               28d    52 closed ·  37 in a release set ·  2 tags cut
     v1.2.0        8  7  6  5  4  3   open, last 6 days
     creep:   none since baseline (8 issues)
```

- **The header** names the release namespace and the newest `v*` tag (`cut`).
- **IN FLIGHT** is the lowest version above that tag: the release you are
  working toward now. `open · done` counts only leaf issues. Epics listed as
  `gates:` never add to the count; their children count only if they carry
  the release label themselves. In-progress, blocked and deferred issues all
  count as open: a deferred issue still holds up its release until you move
  it to a later one.
- **HOTFIX QUEUE** is priority-0/1 bugs, plus security-marked issues at
  priority 0–2, that carry **no** release label. The patch version shown
  (the in-flight version's next patch) is implied, not planned: cut it
  whenever one fix is ready, without waiting for the in-flight version.
- **PLANNED** is every later minor or major version that has at least one
  labelled issue. Only its features are listed; the rest are counted in
  `…N more`. Run `/roadmap <version>` to see all of them.
- **UNSCHEDULED** is features and epics with no release label. Tasks with no
  version are not roadmap lines and are left out.
- **THROUGHPUT** looks backward, never forward. It shows how many issues
  closed, how many of those were in a release, and how many tags were cut
  over the last 7 and 28 days. It also shows the in-flight version's open
  count for each of the last six days. `creep` compares the in-flight
  version's current issues with the baseline taken when it went in flight.
- **Drift conditions**, when any apply, print last. Each names the problem
  and the command that fixes it. See [`docs/DESIGN.md`](docs/DESIGN.md) for
  all eight.

Issues auto-filed by tooling (labels matching `auto_label_prefixes` in
`roadmap.toml`) are left out of the hotfix queue, the unscheduled list,
`plan` proposals and throughput. If one carries a release label, it still
counts toward that version. Deferred issues are left out of
the hotfix queue, the unscheduled list and `plan` proposals, since deferring
means "not now".

### Common tasks

**Put an issue in a version.** Add its release label in `bd`. The label goes
**last**:

```
bd label add acme-42 release:acme-app-v1.2.0
```

With the label first, `bd label add` prints an error and still **exits 0**,
so a script reads it as success while nothing was applied. Run `roadmap`
again to see the issue land.

**Plan the next version.** `/roadmap plan` picks the first planned version
(or the in-flight one if nothing is planned yet); `plan v1.3.0` names one.
It looks at the epics gating that version and proposes the unversioned work
beneath them, ranked by priority and then by type (feature, bug, task), up to seven items
with the true total shown. It ends with a ready-to-paste `bd label add` block.
Nothing is applied until you run it. An empty proposal is one of two
different results, so read which one it printed:

- **Gating epics exist, but nothing unversioned sits beneath them:** the
  version looks ready to cut.
- **The version has no gating epic:** the tool says it cannot judge
  readiness, because it has nothing to check against. Unversioned work may
  still belong in the version.

**Ship a version.** Cut the `v*` tag in `tag_repo` as you normally would.
The next run notices the new tag, moves the next version into flight and
snapshots its scope as the new creep baseline. You don't need to run
anything extra.

**Accept scope growth.** When the in-flight version has grown and you've
decided that's fine, `/roadmap pin v1.2.0` makes its current issues the new
baseline. This throws away the record of what was added, so only do it on
purpose; if the growth wasn't agreed, move issues out instead.

**Script against it.** `roadmap --json` prints the same model as JSON; the
SessionStart hook reads this form. If `roadmap` can't read the board (no
config, `bd` missing, Python too old), it prints `roadmap: unavailable: …` on
stderr, puts the reason under an `unavailable` key in JSON, and **still exits
0** so it can never break a session. Check for that key rather than trusting
the exit code.

**Check which version you're running.** `roadmap --version` prints something
like `roadmap 0.2.1 (/path/to/bin/roadmap)`. It works without a
`roadmap.toml`. The path matters as much as the number: updating the plugin
only takes effect after you restart Claude Code, and a local checkout can
differ from the installed copy. To pick up a new release, run
`/plugin marketplace update beads-roadmap`, then
`/plugin update roadmap@beads-roadmap`, then restart.

Other flags: `--today YYYY-MM-DD` renders the board as of another date (for
the day-count windows and warm-up), `--state PATH` uses a different state
file, and `init --force` overwrites an existing `roadmap.toml`.

### The SessionStart hook

The plugin runs a check when each Claude Code session starts. **When nothing
needs attention it prints nothing.** When something does, it prints a short
`ROADMAP CADENCE CHECK` block naming each condition and the command to fix
it. Two conditions are gentle nudges, scope creep and a low on-plan share,
and those print at most once every three days (set
`ROADMAP_CADENCE_DAYS` to change that). Everything else repeats every
session until fixed, including a hotfix queue that holds a priority-0/1
issue. The same conditions appear at the bottom of the full board, so
`/roadmap` is always the place to look closer.

## Conventions your board must already follow

This tool derives everything from existing `bd` conventions. If your board
doesn't yet follow these, it will render — usually an empty or misleading
board — without an error telling you why:

1. **[beads](https://github.com/steveyegge/beads) (`bd`) is the issue
   tracker.** The tool shells out to `bd list --json`; there is no other
   input.
2. **Release labels are shaped `release:<namespace>-v<semver>`**, e.g.
   `release:acme-app-v1.2.0`. This is how an issue is tied to a version.
3. **Versions are semver `v*` git tags** (`v1.2.0`, not `1.2.0` or
   `v1.2.0-beta`) in the repository named by `tag_repo`. The highest tag
   reachable there is what "in flight" is measured against.
4. **`bd`'s parent/epic hierarchy is populated.** Work proposed for a version
   (`roadmap plan`) is found by walking from that version's gating epics
   through `bd`'s parent links — both the `parent` field and dotted child
   ids, since neither encoding alone is complete on a real board.
5. **`bd`'s `feature` / `epic` / `bug` issue types and 0–4 priority scale are
   in use.** Unscheduled work is `feature`/`epic` rows carrying no release
   label; the hotfix queue is priority-0/1 bugs (plus security-marked
   priority-0/1/2 issues) carrying no release label either. Deferred issues
   are left out of both.

## Requirements

**Python 3.11 or newer, standard library only.** The config loader uses
`tomllib`, which shipped in the standard library starting in 3.11 — there is
no TOML dependency to install. Nothing else here reaches outside the standard
library either. The floor is **enforced**, not just documented: on an older
interpreter (`/usr/bin/python3` on macOS is commonly 3.9.6) `roadmap` prints
`roadmap: unavailable: ...` naming both the requirement and the interpreter
it found, then exits 0, the same fail-open contract every other unavailable
reason follows — instead of an uncaught traceback.

If you use [mise](https://mise.jdx.dev/), `.mise.toml` pins the exact patch
this project develops against. It deliberately names the **oldest** supported
version rather than the newest that works, so a 3.12-or-later-only construct
cannot slip in unnoticed; CI then runs the suites on 3.11, 3.12 and 3.13 to
prove the newer ones still pass.

**`bd` (beads).** The tool shells out to exactly one read, twice:

```
bd list --status=open,in_progress,blocked,deferred -n 0 --json
bd list --status=closed -n 0 --json
```

and reads these fields off each row: `id`, `title`, `labels`, `issue_type`,
`priority`, `parent`, `status`, `updated_at`. `-n 0` is mandatory — `bd list`
silently truncates otherwise. `--status` is an exact match, so every
not-done status is named, in one comma-separated flag: repeating `--status`
silently keeps only the last one.

**Verified against `bd` 1.2.2. No lower bound has been tested**, so no minimum
is claimed here: an older `bd` may well work, and stating a floor that was
never exercised would be a guess wearing the costume of a fact. If yours is
older, check it emits those flags and fields. A `bd` that rejects the flags
exits non-zero and `roadmap` fails open with a named reason; one that omits
`labels` would render an empty board instead, which is why the check is worth
doing by hand.

## `github-*` ids in code comments

Several comments and docstrings in this codebase cite ids like `github-4jmwr`
— these are provenance from the tool's original issue tracker (the workspace
this plugin was extracted from) and were kept deliberately, as a record of
*why* a given piece of logic exists. They do not resolve to any public issue
tracker; don't follow them expecting a link to work.

## Design

See [`docs/DESIGN.md`](docs/DESIGN.md) for the short public design: what
"derived, not stored" means concretely, the eight drift conditions the
SessionStart hook can report, and the fail-open contract that keeps a broken
or unconfigured install from ever breaking a session.

## License

MIT. Copyright (c) 2026 Kaimoku Technologies, LLC. See [`LICENSE`](LICENSE).
