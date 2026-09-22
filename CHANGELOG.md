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
