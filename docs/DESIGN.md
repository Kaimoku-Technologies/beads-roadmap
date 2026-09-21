# Design

## Derived, not stored

Every render of `roadmap` recomputes from the current state of a
[beads](https://github.com/steveyegge/beads) (`bd`) issue board. It reads
`bd list --json` and the git tags in `tag_repo`, builds an in-memory model,
and prints from that. It writes nothing back to `bd` — no label, no comment,
no field.

This is deliberate, not an omission. A tool that *wrote* derived state (for
example, tagging the hotfix queue onto issues automatically) would need a
reconciliation story: what happens when an issue is closed, reprioritized, or
relabeled out from under a stale tag? By recomputing on every run instead,
there is no cache to invalidate and no drift between what the board says and
what the tool reports — the two facts are the same fact, read twice.

The only state the tool keeps at all is a small local file (`--state`,
`~/.claude/roadmap-cadence-state.json` by default) holding four fields, none
of them authoritative over `bd` — each exists only to be compared against a
fresh read:

- `last_reported_at` — when the SessionStart hook last spoke. Governs its
  throttle (default: at most once every 3 days, except for bypass
  conditions).
- `convention_start` — the date the release-label convention began for this
  install. Governs the 14-day warm-up that suppresses condition 3 (off-plan
  share) until the convention is old enough for an on-plan claim to mean
  anything.
- `baselines` — per-version pinned snapshots of which issue ids were in scope
  at the last `roadmap pin` (or at the moment a version first became
  in-flight, if never pinned). What condition 2 (scope creep) compares the
  current set against.
- `last_cut` — the most recently seen cut tag. Comparing it against the
  current cut tag on each run is how condition 6 (a tag was cut) detects
  that a version shipped since the tool last ran.

Deleting the file resets the throttle and drops creep history back to "no
baseline yet." It does *not* make condition 6 fire on the next run: an
absent `last_cut` is treated as "first run ever," which silently records the
current cut as the new reference point rather than treating it as an advance
— the same cold-start bias `baselines` itself has (condition 2 cannot fire
on a version the tool has never seen before either). Condition 6 only fires
on a run where `last_cut` was already recorded from a *previous* run and the
current cut differs from it.

## The SessionStart hook and its six conditions

A roadmap that must be visited to matter will not be visited once a board has
any real size. `hooks/roadmap-cadence.py` runs `roadmap --json` at session
start and, when the render surfaces one or more of six conditions, prints a
short report into the session's context. When there is nothing to report, it
prints nothing — silence is the default outcome, not a fallback.

The six conditions `evaluate()` can raise, in order:

1. **Horizon empty** — nothing is tagged above the version in flight (or
   above the last cut tag, if nothing is in flight). There is no plan beyond
   "now."
2. **Scope creep** — the in-flight version has grown since it was last
   pinned: issues now in scope that weren't at baseline, excluding anything
   that qualifies as a hotfix (those are expected to land opportunistically).
3. **Off-plan share** — over the last 14 days, fewer than 40% of
   human-authored closes carried a release label. Suppressed during a
   14-day warm-up after the release-label convention starts, so a fresh
   install isn't scored against a convention it just adopted.
4. **Unscheduled P0/P1** — a severe (priority 0 or 1) feature or epic carries
   no version. Treated as a planning bug, not a backlog item.
5. **Hotfix queue** — one or more priority-0/1 bugs, or security-marked
   priority-0/1/2 issues, carry no version and are cuttable independently of
   whatever is in flight.
6. **A tag was cut since the last run** — fires once, the run immediately
   after a version ships, while the next version is still an open question
   and planning it is cheap.

Each condition is either **throttled** (reported at most once every N days,
default 3) or marked **bypass** (repeats every session regardless of
throttle). Conditions 1, 4, and 6 always bypass, because each names a state
that shouldn't be sat in: no plan, an unscheduled severe issue, or a
just-cut version with nothing queued behind it. Condition 5's bypass is
**conditional on what's in the queue**: it bypasses whenever the queue holds
a priority-0/1 issue, and is plain-throttled — like conditions 2 and 3 —
when everything in it is P2-security-only. A P0/P1 hotfix repeats every
session until it is either versioned or downgraded; a P2-security-only queue
gets the same at-most-once-every-3-days treatment as scope creep or
off-plan share.

## Fail-open, always

The hook and the underlying tool both fail open on every input failure — no
`roadmap.toml`, `bd` not on `PATH`, a `bd` or `git` subprocess that exits
non-zero or times out, unparseable JSON, a malformed config — meaning: exit
0, never raise, never break the caller. A SessionStart hook that could break
a session over a missing binary or a stale config would get disabled the
first time it did, taking the roadmap visibility with it.

Failing open is not the same as failing *silently*, and the two surfaces
differ here. Run `roadmap` directly against a broken or unconfigured install
and it is **not** silent: it prints `roadmap: unavailable: <reason>` to
stderr (and, under `--json`, sets an `unavailable` key) before returning
exit 0, so "empty board" and "board couldn't be read" are never the same
message to a human running it directly. The hook, by contrast, genuinely
says nothing on this path: it captures the CLI's stderr and discards it
unread, and an `unavailable`-only JSON payload (no `conditions` key) is
treated exactly like a clean board — silence, with the reason available only
if you run the CLI yourself.
