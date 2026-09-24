# A release label in another namespace means "scheduled" — design

Issue: `github-478rk` · Status: approved 2026-09-23

## Problem

`roadmap plan` proposes "unversioned open work descending from the epics that
gate a version". Its filter is `not release_versions(i)`, and
`release_versions()` keeps only labels in the configured
`release_namespace`. So in a shared bd workspace an issue already tagged for
ANOTHER product's release counts as unversioned here.

Observed live 2026-09-23: five issues carried a sibling product's
`release:<site>-v0.4.0`, yet `roadmap plan v0.18.0` run from the mail
product's workspace listed all five in its top 7 and emitted a
`bd label add <id> release:<mail>-v0.18.0` line for each. Pasting that
block double-tags website work with a wrong release; and because the list is
capped at 7, already-placed issues crowd out the real candidates.

## Premise check

`bin/roadmap` (0.4.0): `_candidates()` filters `not release_versions(i)`; so
do the hotfix queue and the unscheduled list in `build_model()`. All three are
"take this on now / schedule this" surfaces with the same bug: a P1 bug tagged
for another product's release shows in this product's hotfix queue as
unscheduled.

## Decision

On those three surfaces, "already scheduled" means **any** release label,
whatever the namespace — `release_labels(i)`, which already exists. The
question they answer is "has anyone scheduled this yet?", and a foreign
release is a yes.

Unchanged, deliberately: every COUNT (version leaves, throughput,
`in_release_*`) stays namespace-filtered through `release_versions()` —
github-kkq4a M9 made that choice for counts, and a foreign release must not
inflate this product's version or throughput.

Not in scope: attributing *unlabelled* issues to a product (github-7jn0v).

## Plan

1. Selftest (RED): a descendant of a gating epic carrying only a
   foreign-namespace release label is NOT a plan candidate (must-miss); an
   unlabelled sibling still is (must-hit). Same pair for the hotfix queue and
   the unscheduled list. Run it and watch the new checks fail.
2. `bin/roadmap` (GREEN): `release_versions(i)` → `release_labels(i)` in
   `_candidates()`, the hotfix queue and the unscheduled list; note the rule
   in the `is_deferred` docstring's neighbour so the next reader knows counts
   and surfaces differ on purpose.
3. CHANGELOG `[Unreleased]` entry.
4. Full selftest + hook tests; live `roadmap plan v0.18.0` from the checkout
   binary (must-miss: the five foreign-tagged issues gone; must-hit: the count drops by 5
   and other candidates remain).
5. Release 0.4.1 per the plugin release procedure, update the install, and
   re-verify with the installed binary.
