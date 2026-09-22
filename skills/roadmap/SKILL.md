---
name: roadmap
description: Use when asked what should ship next, what is in a version, whether anything is unscheduled, whether a fix should be a hotfix, or to show the product roadmap — renders a derived roadmap over a beads board (versions, hotfix queue, unscheduled work, scope creep) and proposes what to put in a version. Triggers on "what should we ship next", "what's in v1.2", "is anything unscheduled", "should this be a hotfix", "show the roadmap", "plan the next version", "roadmap".
---

# Roadmap

Everything is DERIVED from the beads board on each render. The tool never
writes to bd, so there is no state to migrate and no tag to keep in sync.

## Commands

- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap` — the board
- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap hotfix` — the full severity queue
- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap unscheduled` — everything with no version
- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap plan` (or `plan v1.2.0`) — proposes what
  should go in a version
- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap v1.2.0` — one version in detail
- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap pin v1.2.0` — re-baseline that version's
  scope-creep snapshot
- `${CLAUDE_PLUGIN_ROOT}/bin/roadmap init` — write `roadmap.toml` (once per
  workspace)

## Reading the output

**An EMPTY `plan` proposal is a RESULT, not a blank — but there are TWO such
results and they are different claims.** Read which one it printed.

- **Gating epics exist and nothing unversioned descends from them** → the
  version looks ready to cut. Report that verdict; do not treat it as an
  error.
- **No gating epic at all** → the tool says so and explicitly disclaims a
  readiness verdict. It has nothing to check descent against, so unversioned
  work may still belong in that version. This is the default state for a board
  whose epic hierarchy has not formed yet.

Never report the second as the first. The tool distinguishes them precisely so
the answer is not invented.

**`roadmap: unavailable: …` on stderr is not an empty board.** The tool fails
open so it can never break a session, but it says why. With `--json` the
reason is under the `unavailable` key. An exit of 0 does not mean the board
was read.

## Applying a label

The board prints the exact command. Run it as printed — **the label goes
LAST**:

    bd label add <id> release:<ns>-v1.2.0

With the label first, `bd label add` prints an error and **exits 0**, so a
chained call reads as success while nothing was applied.
