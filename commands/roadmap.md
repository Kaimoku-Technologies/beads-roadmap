---
description: Show the product roadmap — versions, hotfix queue, unscheduled work
---

Run the roadmap board and report it.

- No argument → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap`
- `init` → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap init` — probes the layout, prints
  what it found, and writes `roadmap.toml`. Run this once per workspace before
  anything else. It REFUSES an ambiguous layout rather than guessing; write
  the file by hand in that case.
- `hotfix` → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap hotfix` (full severity queue)
- `unscheduled` → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap unscheduled` (everything
  with no version)
- `plan` → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap plan` (or `plan v1.2.0`) —
  proposes what should go in a version, drawn from the unversioned work
  descending from that version's gating epics, ranked, capped at 7 with the
  true total shown. Emits a paste-ready `bd label add` block. An EMPTY
  proposal is a result, not a blank: it means no unversioned work is left
  under those epics, so the version looks ready to cut. Report that verdict,
  don't treat it as an error.
- A version like `v1.2.0` → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap v1.2.0`
- `pin <version>` → `${CLAUDE_PLUGIN_ROOT}/bin/roadmap pin <version>`, which
  re-baselines that version's scope-creep snapshot. Only run this when the
  growth has been accepted deliberately — it discards the evidence of what
  was added.

Arguments: $ARGUMENTS

Report the output verbatim. Do not apply any label yourself: the board prints
the exact `bd label add` command, and **the label goes LAST** — with the label
first, `bd label add` prints an error and **exits 0**, so it reads as success
while nothing was applied.
