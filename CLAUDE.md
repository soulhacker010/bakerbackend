<!-- verity-memory:start -->
## Project Memory

This project has a knowledge graph maintained at `.verity/memory/`. Before starting
non-trivial work, scan `.verity/memory/index.md` for decisions, gotchas, and patterns
that may apply to the change you are about to make. Open specific node files via
the Read tool when the title or scope suggests relevance.

The graph is auto-maintained by Verity. Files at `.verity/memory/_archive/` are
superseded — ignore them unless investigating history.

## Quality gate: accepted risks

When the Verity pre-commit/pre-push gate FAILs, fix the findings — that is the
default. Use `verity waive <pattern-id> --file <path> --reason "…"` ONLY to relay
a risk a human has explicitly accepted: a named code-review finding, an ADR, or
the user saying so in this conversation. The --reason must cite that source.

Never waive on your own judgment, to get past a block, or pre-emptively. A waive
binds to the file's current bytes and voids automatically when the file changes,
and every waive is recorded in the run ledger. For a pattern-level false positive
use `verity feedback finding <run-id> <pattern-id> false_positive` instead.

> Durable, hand-curated guidance goes in the preserve region below (it survives
> regeneration) or anywhere OUTSIDE these markers. Everything else between the
> markers is tool-owned and overwritten on each run.

## Housekeeping Turns

When a turn will be pure housekeeping — pulling, installing dependencies,
rebasing, a formatting sweep you are not authoring — declare it BEFORE doing it:

```bash
verity ignore --turn --agent --reason "pulling latest before starting"
```

This skips the review for that turn, which saves the turn Verity would
otherwise spend saying it had nothing to say. Use `--for 30m` instead of
`--turn` when a single piece of housekeeping spans several turns.

**It is a claim about the turn, not a way to silence review.** The declaration
is checked against what the turn actually did: if anything is authored — by you,
by a subagent, or by a shell command that can write files — it voids, the review
runs anyway, and the broken declaration is reported. So declare housekeeping you
are about to do, never work you have already done, and never as a way to get past
a finding. Declarations are budgeted per session and every one is recorded with
its reason.

<!-- verity-memory:preserve -->
<!-- Add binding, hand-curated guidance here; it survives Verity regeneration. -->
<!-- /verity-memory:preserve -->
<!-- verity-memory:end -->
