# beads-roadmap

A roadmap for your [beads](https://github.com/steveyegge/beads) (`bd`) issue
board: which release each open issue belongs to, what is in flight, what is
urgent enough to hotfix, and what nobody has scheduled yet.

**Why it exists.** A `bd` board grows fast — hundreds of open issues, a dozen
epics, and a new idea every five minutes. Without a roadmap, every idea
competes with the release you are trying to finish. `roadmap` gives each issue
a version, shows you the one in flight, and nags you (at session start, and
only when something is actually off) when work is drifting away from the plan.
So one session can work on `v1.2.0` while the shiny new idea waits in the
backlog instead of sneaking into the release.

**Who it's for.** Anyone tracking work in `bd` who cuts versioned releases —
especially if AI coding agents do part of the work. It ships as a
[Claude Code](https://claude.com/claude-code) plugin, and as a plain
command-line tool you can run from any terminal, IDE or other coding agent.

**It only reads.** The tool never writes to `bd` — no label, no comment, no
field. Every run rebuilds the roadmap from a fresh `bd` read ("derived, not
stored"). The only local state is a small file next to your `roadmap.toml`
holding a scope-creep baseline and a throttle stamp, kept so the next run has
something to compare against.

## What it looks like

An illustrative board (the issues are invented; the layout is real):

```
ROADMAP · acme-app · cut v1.1.0

  IN FLIGHT
     v1.2.0       3 open · 5 done
        P1 bug      acme-7       Login fails when the session cookie is expired
        P2 feature  acme-12      Export reports as CSV
        P3 task     acme-15      Rename the settings page
        gates: acme-5      Reporting overhaul

  HOTFIX QUEUE v1.2.1 (implied)   1 unversioned · cuttable independently
    P1 bug       acme-42 Password reset link never arrives

  PLANNED
     v1.3.0       4 open · 0 done
        P2 feature  acme-70      Single sign-on
        P2 feature  acme-71      Dark mode
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

[Reading the board](#reading-the-board) explains each section.

## Before you start: what your board needs

The tool derives everything from conventions your board must **already**
follow. If it doesn't, `roadmap` still renders — usually an empty or
misleading board — **without an error telling you why**. So check these
first:

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
6. **Optional: `release:<namespace>-backlog` marks triaged work you have
   deliberately parked beyond the horizon.** It takes a row out of the
   unscheduled list (any type is listed by `roadmap backlog`), so
   "unscheduled" comes to mean *nobody has triaged this yet*. It never
   exempts a row from the hotfix queue, and a backlogged priority-0/1
   feature or epic is still reported, because parking something that severe
   is itself the planning bug. Promote from the backlog by removing the
   label and adding a version.
7. **Optional: `horizon = N` in `roadmap.toml`** asks for the in-flight
   version plus the planned minors to number at least N. When fewer carry
   work, the board and the session-start check report `HORIZON SHORT` and
   name the next minor to tag. Off (0) by default.
8. **Optional: `scoped = true` in `roadmap.toml`, when several products
   share one `bd` board.** The board then lists only the hotfix and
   unscheduled rows this product *owns* and counts only its own closes.
   Leave exactly one board per shared `bd` database unscoped: it is the
   catch-all that shows every unlabelled row. See
   [Several products, one `bd` board](#several-products-one-bd-board).
9. **Optional: `boards = ["other-app", "third-app"]` in the catch-all's `roadmap.toml`**, listing the directories of the scoped boards that share its `bd` database. The session-start check and `roadmap check`, run from the catch-all's directory, then report every listed board, each on its own throttle. Cannot be combined with `scoped = true`. See [Hearing every board from one session](#hearing-every-board-from-one-session).

You also need **Python 3.11 or newer** (standard library only) and `bd` on
your `PATH`. See [Requirements](#requirements) for the details.

### Terms used below

| Term | Meaning |
| --- | --- |
| **namespace** | The `<namespace>` in your release labels — a string you choose, e.g. `acme-app`. Lets several products share one `bd` board. |
| **cut** | The newest `v*` git tag: the last version you shipped. |
| **in flight** | The lowest version above the cut tag that has issues labelled for it — the release you are working toward now. |
| **planned** | Later minor or major versions that already have at least one labelled issue. (A patch version is never "planned": see hotfix queue.) |
| **gating epic** | An epic carrying a version's release label. Its children are where `roadmap plan` looks for work that belongs in that version. |
| **hotfix queue** | Urgent work with no version: priority-0/1 bugs, plus security issues at priority 0–2. Shippable as a patch without waiting for the in-flight release. |
| **unscheduled** | Features and epics with no release label: nobody has decided when they ship. |
| **backlog** | Work labelled `release:<namespace>-backlog`: triaged, and deliberately parked beyond the planning horizon. |
| **scope creep** | Issues added to the in-flight version after it went in flight, compared against a baseline snapshot. |
| **owned** | An unlabelled row this board claims: it carries this namespace's release or backlog label, its nearest labelled ancestor epic does, or a configured title/id prefix matches. |
| **scoped board** | A board with `scoped = true`: hotfix queue, unscheduled list and throughput cover owned rows only. Its header ends in `· scoped`. |
| **catch-all board** | A board without `scoped`: shows every unlabelled row, as a single-product board always has. Keep exactly one per shared `bd` database. |
| **listed board** | A scoped board named in the catch-all's `boards` list. The catch-all's session-start check runs it too and reports it under a `-- <name>` header; a listed board that is missing or cannot be read is itself reported. |
| **drift** | Any of nine planning problems (see [DESIGN.md](docs/DESIGN.md)) that the session-start check reports. |

## Install

Pick one. Both give you the same `roadmap` command.

### Option A: Claude Code plugin

```
/plugin marketplace add Kaimoku-Technologies/beads-roadmap
/plugin install roadmap@beads-roadmap
```

This adds the `/roadmap` slash command, a skill that tells Claude when to run
it, and a session-start check that reports planning drift. (If you're working
from a local checkout instead of a marketplace listing, point Claude Code's
plugin loader at this directory directly.)

### Option B: plain command-line tool (any terminal, IDE or agent)

Everything that matters is one script, `bin/roadmap`. Download a release and
put it on your `PATH`; no git needed:

```
curl -fsSL https://github.com/Kaimoku-Technologies/beads-roadmap/archive/refs/tags/v0.7.0.tar.gz | tar xz
ln -s "$PWD/beads-roadmap-0.7.0/bin/roadmap" ~/.local/bin/roadmap
roadmap --version
```

Keep the unpacked `beads-roadmap-0.7.0/` directory where it is: the link
points into it, and `roadmap check` and `--version` read files beside the
script. Any directory on your `PATH` works in place of `~/.local/bin`.
`--version` should print a path inside that directory. Install 0.4.0 or
later this way: earlier releases don't follow the symlink, so `--version`
reports `version unknown` and `roadmap check` doesn't exist.

The script runs under the first `python3` on your `PATH`, which must be
3.11 or newer. macOS's `/usr/bin/python3` is 3.9, and on it `roadmap` prints
`roadmap: unavailable: needs Python 3.11 or newer` instead of a board.

**Prefer git?** `git clone https://github.com/Kaimoku-Technologies/beads-roadmap.git`
and link `beads-roadmap/bin/roadmap` instead; `git pull` then upgrades to
whatever is on `main`, which may be ahead of the latest release.

**In an IDE** (PyCharm, VS Code, …), run `roadmap` in the built-in terminal,
or register it as an external tool / task with the project root as its
working directory. The output is plain text.

**With another coding agent** (Cursor, Codex, Gemini CLI, …), install it this
way, then see [Using it with other agents](#using-it-with-other-agents).

## First run: `roadmap init`

Run `init` once per workspace. **Inside a Claude Code session** — where the
plugin's `bin/` is on your `PATH` — that is:

```
/roadmap init
```

With Option B, it's `roadmap init` in a shell. With Option A but outside a
session, bare `roadmap` will not resolve: `PATH` only carries the plugin's
`bin/` because Claude Code injects it. Call it by path instead:

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

**Starting from scratch?** If your board has no release labels yet, `init`
has no namespace to find. Label one issue first, then run `init`:

```
bd label add <some-issue-id> release:<your-namespace>-v0.1.0
```

## Using it

Inside a Claude Code session, use the `/roadmap` slash command, or just ask
("what should we ship next?", "is this a hotfix?") and the bundled skill runs
it for you. In a shell, the same commands are `roadmap …` (by full path
outside a session with Option A; see above).

| Command | What it shows |
| --- | --- |
| `/roadmap` | The whole board (see below) |
| `/roadmap v1.2.0` | One version in detail: every open issue, gating epics, counts |
| `/roadmap hotfix` | The full hotfix queue (the board shows the top three) |
| `/roadmap unscheduled` | Every feature and epic with no version (the board shows the top three) |
| `/roadmap backlog` | Every issue labelled `release:<namespace>-backlog`: triaged, deliberately beyond the horizon |
| `/roadmap plan` | Proposes what to put in the next planned version |
| `/roadmap plan v1.2.0` | The same for a specific version |
| `/roadmap pin v1.2.0` | Re-baselines that version's scope-creep snapshot |
| `/roadmap init` | Writes `roadmap.toml` (once per workspace, see above) |
| `/roadmap --version` | The plugin version, and the path of the `roadmap` that answered |
| `/roadmap check` | The session-start drift check, as plain text (nothing when clean) |

Every command rebuilds everything from a fresh `bd` read, so there is nothing
to refresh or sync: run it whenever you want the current picture.

### Reading the board

Using the [example above](#what-it-looks-like):

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
  On a scoped board, only rows this product owns; the catch-all board has
  the rest.
- **PLANNED** is every later minor or major version that has at least one
  labelled issue. Only its features are listed; the rest are counted in
  `…N more`. Run `/roadmap <version>` to see all of them.
- **UNSCHEDULED** is features and epics with no release label. Tasks with no
  version are not roadmap lines and are left out. On a scoped board, only
  rows this product owns; the catch-all board has the rest.
- **THROUGHPUT** looks backward, never forward. It shows how many issues
  closed, how many of those were in a release, and how many tags were cut
  over the last 7 and 28 days. It also shows the in-flight version's open
  count for each of the last six days. `creep` compares the in-flight
  version's current issues with the baseline taken when it went in flight.
  On a scoped board `closed` counts only this product's closes.
- **Drift conditions**, when any apply, print last. Each names the problem
  and the command that fixes it. See [`docs/DESIGN.md`](docs/DESIGN.md) for
  all nine.

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
the exit code. `--json` also carries `"scoped"`, true when the board is
scoped. `--json` also carries `"workspace"` (the resolved path) and, only on
a board whose config has the key, `"boards"` — one `{name, config_path,
exists}` per listed board.

**Check which version you're running.** `roadmap --version` prints something
like `roadmap 0.2.1 (/path/to/bin/roadmap)`. It works without a
`roadmap.toml`. The path matters as much as the number: updating the plugin
only takes effect after you restart Claude Code, and a local checkout can
differ from the installed copy. To pick up a new release, see
[Upgrading](#upgrading).

Other flags: `--today YYYY-MM-DD` renders the board as of another date (for
the day-count windows and warm-up), `--state PATH` uses a different state
file, and `init --force` overwrites an existing `roadmap.toml`.

### Several products, one `bd` board

When several products keep their issues in one `bd` database, each with its
own `roadmap.toml` and namespace, an issue with no release label belongs to
no product in particular. Without scoping, every board lists every other
product's untriaged features and urgent bugs, and the THROUGHPUT on-plan
share collapses, because it divides this product's release work by every
close in the database. A board that opts in shows only what it owns:

```toml
# Optional. On a bd board shared by several products, show only the rows this
# product OWNS: rows labelled for this namespace, rows whose nearest labelled
# ancestor epic is, and rows matched by the claim lists below. Leave it unset
# on exactly one board per shared board -- that board is the catch-all and
# shows every unlabelled row, so an unowned P0 bug is always visible somewhere.
scoped = true
claim_title_prefixes = ["acme-app:"]     # literal, case-sensitive title prefixes
claim_id_prefixes = ["acme-"]            # literal id prefixes; include the separator
```

A row is owned when any of these holds:

- it carries `release:<namespace>-v*` or `release:<namespace>-backlog` itself;
- its **nearest** ancestor that carries any release or backlog label carries
  one for this namespace (through `parent` or a dotted id, open or closed);
- its title or id starts with one of the configured claim prefixes.

The scoping applies to the hotfix queue, the unscheduled list and THROUGHPUT's
`closed` count. Version counts, the backlog and `plan` were already limited to
your namespace and do not change. A scoped board's header ends in `· scoped`.

**Leave exactly one board unscoped**, normally the product the database was
created for. It is the catch-all: an unowned priority-0 bug is always on that
board and in its session-start check. **If every board is scoped, an unowned
row appears on no board, and the tool cannot detect that** from one
`roadmap.toml`, since it reads only its own config.

A `roadmap` older than 0.7.0 refuses these keys by name and prints
`roadmap: unavailable: … unknown key(s): scoped`, so the board goes silent.
Update the install before adding them.

#### Hearing every board from one session

A session opened at the workspace root hears only the catch-all's drift. A
scoped board's empty horizon, or its hotfix queue, reaches only a session
opened inside that board's directory. The catch-all can list its siblings so
that one session hears them all:

```toml
# Optional, on the CATCH-ALL board only. Directories, relative to this file,
# that each hold their own roadmap.toml. The session-start check (and
# `roadmap check`) run from this directory then report every listed board,
# each on its own throttle, not just this one. The text board and --json of
# a board never change. Cannot be combined with scoped = true: the board
# that lists the others is the catch-all.
# boards = ["other-app", "third-app"]
boards = ["other-app", "third-app"]
```

The board that lists the others is the catch-all, so `boards` together with
`scoped = true` is refused. Each listed directory must hold its own
`roadmap.toml`. Entries are compared by their real path, so the catch-all's
own directory (by any spelling) and a repeated directory are refused at load.

The report is the catch-all's lines as today, then one block per listed board
that has something to say, headed
`-- other-app  ·  <dir>  ·  full board: cd <dir> && roadmap`. A listed board
with nothing to say adds nothing. Listed boards run in parallel, and the
check still prints a single report. Each listed board is judged on its own
state file, beside its own `roadmap.toml`, so one board's report never resets
another's throttle.

Three problem lines appear under the catch-all, in the order the boards are
listed:

- `boards: other-app listed, no roadmap.toml there`: the directory has no
  `roadmap.toml`.
- `boards: other-app unavailable: <reason>`: the board could not be read
  (bad config, `bd` down, a timeout, no usable output).
- `two catch-all boards: other-app repeats every unowned row -- add scoped = true`:
  the listed board is unscoped and uses the same `bd` workspace as the
  catch-all, so both show every unlabelled row.

These repeat every three days, like scope creep, not every session. A listed
board that is unscoped but uses a *different* workspace is fine: it is
another database's catch-all. Listing is one level only; a listed board's own
`boards` key is never followed.

**Update the install before adding the key.** A `roadmap` older than 0.8.0
refuses `boards` by name and prints `roadmap: unavailable: … unknown key(s):
boards` when run by hand, and the catch-all's session-start check goes
silent, exactly as the 0.7.0 note above says for `scoped`.

### The SessionStart hook

The plugin runs a check when each Claude Code session starts. **When nothing
needs attention it prints nothing.** When something does, it prints a short
`ROADMAP CADENCE CHECK` block naming each condition and the command to fix
it. Two conditions are gentle nudges, scope creep and a low on-plan share,
and those print at most once every three days (set
`ROADMAP_CADENCE_DAYS` to change that). When the catch-all's `roadmap.toml` lists `boards`, the check also covers every listed board, each on its own throttle, under a `-- <name>` header. Everything else repeats every
session until fixed, including a hotfix queue that holds a priority-0/1
issue. The same conditions appear at the bottom of the full board, so
`/roadmap` is always the place to look closer.

Not on Claude Code? `roadmap check` prints the same thing; see
[below](#the-drift-check-roadmap-check).

## Using it with other agents

Any coding agent that can run shell commands can use `roadmap`: it is
standard-library Python 3.11+, reads `bd`, and finds `roadmap.toml` by
walking up from the current directory. Install it with
[Option B](#option-b-plain-command-line-tool-any-terminal-ide-or-agent). The
Claude Code plugin only adds packaging — the install, the `/roadmap` command,
a skill that tells the agent when to use it, and the session-start check.
Here is how to get the last three elsewhere.

### Tell your agent about it

Most agents read a project instructions file: `AGENTS.md`, a Cursor rule
under `.cursor/rules/`, `GEMINI.md`, or similar (check your tool's docs for
the current name and location). Paste this in:

````markdown
## Roadmap

This project's roadmap is derived from the beads (`bd`) board by the
`roadmap` command. Use it to answer "what should we ship next?", "what's in
v1.2?", "is anything unscheduled?" or "should this be a hotfix?".

- `roadmap`: the whole board. `roadmap v1.2.0`: one version.
- `roadmap hotfix` / `roadmap unscheduled`: the full lists.
- `roadmap plan` (or `plan v1.2.0`): proposes issues for a version and
  prints the `bd label add` commands. Nothing is applied until they run.
- `roadmap check`: planning drift, or nothing when all is well.

Report its output as printed. Two rules:

- An empty `plan` is one of two different results. "Nothing unversioned
  below the gating epics" means the version looks ready to cut. "No gating
  epic" means readiness could not be judged. Never report the second as the
  first.
- `bd label add <id> <label>` takes the label LAST. With the label first it
  prints an error and still exits 0, so it looks like it worked.

`roadmap: unavailable: …` means the board could not be read. It is not an
empty board, even though the exit code is 0.
````

For a `/roadmap`-style shortcut, most agents also support custom commands;
the whole command is "run `roadmap` with these arguments and show the
output verbatim".

### The drift check: `roadmap check`

`roadmap check` runs the same check as the Claude Code session-start hook
and prints it as plain text. It prints **nothing** when the board is fine,
and it shares the hook's throttle and once-only messages, kept in the state
file beside `roadmap.toml`. With `boards` in the catch-all's config, `roadmap check` reports every listed board too. Where to run it:

- **Your agent's session-start hook, if it has one.** Check whether the tool
  passes a hook's output to the model; if it doesn't, the agent never sees
  the message.
- **A git hook or shell alias**, for example `post-checkout` or `post-merge`.
  That reaches you rather than the agent, which is often enough.
- **Your agent instructions**: "run `roadmap check` at the start of planning
  work" (already in the snippet above).

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

## Upgrading

**Plugin (Option A):** run `/plugin marketplace update beads-roadmap`, then
`/plugin update roadmap@beads-roadmap`, then restart Claude Code — the update
only takes effect after the restart.

**Plain command (Option B):** download the newer release the same way and
move the link to it with `ln -sfn`; then delete the old directory. Your
board's state lives beside `roadmap.toml`, not in the install, so nothing is
lost.

The [CHANGELOG](CHANGELOG.md) lists what each release changed.

### Upgrading from 0.1.x

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

## Design

See [`docs/DESIGN.md`](docs/DESIGN.md) for the short public design: what
"derived, not stored" means concretely, the nine drift conditions the
SessionStart hook can report, and the fail-open contract that keeps a broken
or unconfigured install from ever breaking a session.

## `github-*` ids in code comments

Several comments and docstrings in this codebase cite ids like `github-4jmwr`
— these are provenance from the tool's original issue tracker (the workspace
this plugin was extracted from) and were kept deliberately, as a record of
*why* a given piece of logic exists. They do not resolve to any public issue
tracker; don't follow them expecting a link to work.

## License

MIT. Copyright (c) 2026 Kaimoku Technologies, LLC. See [`LICENSE`](LICENSE).
