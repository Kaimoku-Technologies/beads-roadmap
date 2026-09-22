---
description: Show the product roadmap — versions, hotfix queue, unscheduled work
---

Run the roadmap board and report it.

- No argument → `roadmap`
- `init` → `roadmap init` — probes the layout, prints
  what it found, and writes `roadmap.toml` into the current directory. Run
  this once per workspace before anything else. A repo with no semver `v*`
  tags yet gets a WARNING and the file is still written. It REFUSES, writing
  nothing, only on a genuinely ambiguous layout — no `.git`, or release labels
  that are absent from the board or span more than one namespace; write the
  file by hand in that case.
- `hotfix` → `roadmap hotfix` (full severity queue)
- `unscheduled` → `roadmap unscheduled` (everything
  with no version)
- `plan` → `roadmap plan` (or `plan v1.2.0`) —
  proposes what should go in a version, drawn from the unversioned work
  descending from that version's gating epics, ranked, capped at 7 with the
  true total shown. Emits a paste-ready `bd label add` block. An EMPTY
  proposal is a result, not a blank — but **read which result it printed**,
  because there are two and they are different claims. With gating epics
  present, "nothing descends from them" means the version looks ready to cut;
  report that verdict. With NO gating epic, the tool says so explicitly and
  disclaims a readiness verdict — it cannot check descent against anything,
  which is the default state for a board whose epic hierarchy has not formed
  yet. Relay whichever one it printed; never upgrade the second into the
  first.
- A version like `v1.2.0` → `roadmap v1.2.0`
- `pin <version>` → `roadmap pin <version>`, which
  re-baselines that version's scope-creep snapshot. Only run this when the
  growth has been accepted deliberately — it discards the evidence of what
  was added.

Arguments: $ARGUMENTS

Report the output verbatim. Do not apply any label yourself: the board prints
the exact `bd label add` command, and **the label goes LAST** — with the label
first, `bd label add` prints an error and **exits 0**, so it reads as success
while nothing was applied.
