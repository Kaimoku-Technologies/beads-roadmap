# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **A release in another namespace now counts as scheduled.** In a bd
  workspace shared by several products, an issue already tagged for a
  sibling product's release was still offered by `roadmap plan` (and could
  sit in the hotfix queue or the unscheduled list) as if it had no version,
  and the paste-ready block would have given it a second, wrong release.
  Those three surfaces now skip any issue with a release label in any
  namespace, and so do the JSON `hotfix_count` / `unscheduled_count` and
  the session-start nags built on them. Version and throughput counts are
  unchanged: they still count only this board's namespace.

### Documentation

- **Install without git.** The README's "Using it with other agents" now
  installs from the release tarball GitHub publishes for each tag (`curl`,
  `tar`, one symlink), with how to upgrade; cloning is the alternative. The
  self-test fails if the version in that snippet doesn't match
  `plugin.json`, so a release can't ship a link to the previous one.

## [0.4.0] — 2026-09-22

Makes `roadmap` usable from agents other than Claude Code: `roadmap check`
prints the drift check as plain text, a symlinked install works, and the
README explains the setup. No state or config changes: upgrading from 0.2.x
or 0.3.x needs nothing. From 0.1.x, see "Upgrading from 0.1.x" in the
README.

### Added

- **`roadmap check`** runs the SessionStart drift check and prints it as
  plain text, for agents other than Claude Code, git hooks and shells. It
  makes the same decisions as the Claude Code hook (silent when clean, the
  same throttle, the same once-only messages) because it runs that hook in
  a new `--text` mode rather than copying its logic. `--state` works as it
  does for the board.
- **The README explains how to use `roadmap` from other agents** (Cursor,
  Codex, Gemini CLI and others): install by cloning and symlinking
  `bin/roadmap` onto `PATH`, a ready-to-paste instructions block for
  `AGENTS.md`-style files, and where `roadmap check` fits.

### Fixed

- **The drift check can no longer go silent on the wrong Python.** The hook
  ran `roadmap` through its `#!/usr/bin/env python3` line, so on a machine
  whose default `python3` is older than 3.11 the inner run failed open and
  the check never spoke, which looks exactly like a clean board. It now runs
  `roadmap` with the same interpreter that started the hook.

- **A symlinked `roadmap` knows where it lives.** `roadmap --version`
  resolved its own location without following symlinks, so installing it
  with `ln -s <clone>/bin/roadmap ~/.local/bin/roadmap` (the install for
  agents other than Claude Code) reported `version unknown` and the link's
  path. It now follows the link to the real copy.

## [0.3.0] — 2026-09-22

Adds `roadmap --version`, so you can tell which build you are running.
No state or config changes: upgrading from 0.2.x needs nothing. From 0.1.x,
see "Upgrading from 0.1.x" in the README.

### Added

- **`roadmap --version`** (and `/roadmap --version`) prints the plugin
  version and the path of the `roadmap` that answered, e.g.
  `roadmap 0.2.1 (/path/to/bin/roadmap)`. It reads the version from the
  plugin's own `.claude-plugin/plugin.json`, so releases still bump only the
  two manifests, and it works without a `roadmap.toml`. If the manifest
  can't be read it prints `version unknown` with the reason and still exits 0.

### Fixed

- **The self-test no longer passes without running.** On Python older than
  3.11 it printed `roadmap`'s own "unavailable" line and exited 0 with no
  checks run, because loading the tool triggered the tool's deliberate
  fail-open exit. It now exits 1 with `FAIL: roadmap-selftest did not run`,
  and any exit while loading the tool is treated as a failure. The
  `roadmap` command itself still fails open, as before.

### Documentation

- **The README now explains day-to-day use:** every command, how to read
  each section of the board, the common tasks (put an issue in a version,
  plan a version, ship one, accept scope growth, script against `--json`)
  and what the SessionStart hook prints and when.
- The README's "Requirements" section now documents the `bd` read 0.2.1
  actually performs (`--status=open,in_progress,blocked,deferred`) and the
  `status` field it reads. It still described the pre-0.2.1 read.

## [0.2.1] — 2026-09-22

Three fixes on top of 0.2.0. No state or config changes: upgrading from
0.2.0 needs nothing. From 0.1.x, see "Upgrading from 0.1.x" in the README.

### Fixed

- **In-progress, blocked and deferred issues are no longer invisible.**
  `roadmap` read only `--status=open` and `--status=closed`, and bd's status
  filter is an exact match, so an issue moved to `in_progress` dropped out of
  its release's open count as though it were done. It now reads
  `open,in_progress,blocked,deferred`. **Deferred is split by view:** a
  deferred issue in a release still counts as unfinished work in that
  release, but it is left out of the hotfix queue, the unscheduled list and
  `roadmap plan` candidates, because deferring it means "not now". Expect
  `unscheduled_count` to rise by any blocked or in-progress features and
  epics.

- **`compute_throughput(cfg=...)` now governs the human-authored filter too.**
  It resolved its cfg but called `is_human_authored` without it, so the module
  config (not the one passed in) decided which closed issues counted as
  auto-filed. Latent: the CLI never passes an explicit cfg, so the two always
  agreed in practice.
- **The self-test's decoupling scan checks what git would ship, not
  everything on disk.** Inside a git checkout it now lists tracked plus
  untracked-but-not-ignored files, so an ignored local file (such as
  `.claude/settings.local.json`) no longer fails the suite. Outside git it
  still scans every file.

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
