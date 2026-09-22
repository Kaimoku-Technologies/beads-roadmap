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
   priority-0/1/2 issues) carrying no release label either.

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
