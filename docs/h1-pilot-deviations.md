---
title: H1 pilot deviations from pre-registration
date: 2026-09-13
tags: [benchmark, preregistration, deviation, h1]
status: final
type: experiment-record
---

# Deviations from the H1 pilot pre-registration

Recorded rather than corrected. A pre-registration that is edited after results exist stops being
a pre-registration, so [[h1-pilot-preregistration]] is left exactly as it was when the first scored
run started, and every departure from it is listed here.

## Deviation 1 — execution commit differs from the pinned fixture commit

**Registered.** Section 12 pins `FIXTURE_COMMIT = ca5e677b1a448c1a91ac0bbd2f02644404d45855`, and
section 13 says runs execute "from a clean checkout at the frozen fixture commit".

**What happened.** All 13 runs recorded `fixture_source_commit = 5f00aa7e40bbf5b63cfd7c6a10440cf7f09c2f75`.

**Why — corrected.** An earlier version of this record claimed that executing the registered pilot
from the registered commit was *impossible*. That was wrong, and the gate was right to reject it.
Section 13 registers the per-run command as `python -m benchmarks.fixture_v3.run_arm --arm <ARM>`,
and that entry point already existed at `ca5e677`. The registered protocol could have been executed
from the registered commit by invoking it twelve times in the registered order.

What actually happened is a choice, not a necessity: I wrote `run_pilot.py` and
`aggregate_pilot.py` to automate the schedule, the mandatory-replacement policy, and the decision
rules, committed them so they could not be adjusted after results appeared, and ran the pilot from
the resulting commit. The automation is defensible on its own terms — a hand-driven sequence would
have made the replacement policy depend on operator discipline — but it was not required by the
registration, and choosing it moved execution off the pinned commit. The pin should have named the
fixture inputs rather than a repository tip, and I should have noticed the conflict before running.

**Evidence that fixture behaviour was unchanged.** The tree of every input that determines what a
run does — `prompts.json`, `markers.json`, `semantic_answers.json`, `seed/`, `arm_assets/`,
`score_markers.py`, `evaluate_hidden.py`, `materialize.py`, and `run_arm.py` — is byte-identical
across the two commits:

```text
ca5e677  cf41223bde5a4aeda9c7e2cd801121f50900cfae7d3f48464045b5a61cfb4aba
5f00aa7  cf41223bde5a4aeda9c7e2cd801121f50900cfae7d3f48464045b5a61cfb4aba
```

`git diff ca5e677 5f00aa7` over those paths is empty. What changed between the two commits is the
pilot runner, the aggregator, their tests, the pre-registration document itself, the freeze
metadata in `manifest.json`, and prose in the fixture spec.

**Assessment.** The deviation is real and is not waved away by the hashes: the run did not happen
at the commit the document named, and it could have. The hashes establish the narrower claim that
the treatment, prompts, canaries, scoring, and arm construction were identical to the frozen
fixture, so the deviation does not give any arm an advantage and does not change what was measured.
It does mean the pilot was executed under an orchestration layer that did not exist at registration
time, and that layer's behaviour — schedule, replacement policy, aggregation — is therefore part of
what a reader has to trust, rather than being reducible to the frozen fixture.

**Fix for future pilots.** Pin the fixture-input tree hash, not a repository commit, and record
both the input hash and the execution commit per run.

## Deviation 2 — the excluded run's effect was favourable to the treatment arm

**Registered.** Section 9 excludes runs solely on the machine validity checks, and states that
validity is never judged by looking at the score.

**What happened.** That was followed: the exclusion fired on the frozen reread detector, which does
not see scores. But the excluded arm-C run had scored 0/6, so removing it raised mean(C) from 0.833
to 1.0 and the contrast from 1/30 to 1/5.

**Assessment.** Not a protocol violation, and not something the protocol could have avoided — but
reporting the headline contrast without this would overstate its robustness. A sensitivity analysis
is included in [[h1-pilot-results]]: counting the excluded run gives the same decision by a
different registered rule, so the outcome does not depend on the exclusion even though the effect
size does.

An earlier version of the results document stated that the excluded run had scored 6/6. That was a
misreading of `state_markers_before_compact` — six canaries present in the state *file* — as the
survival score. Corrected.

## Deviation 3 — cost accounting omitted two registered fields

**Registered.** Section 11 lists "number of scripted turns and tool calls" among the per-run cost
measurements.

**What happened.** The first `cost.json` omitted both. They were added from the stored run records
after the gate pointed this out, and the first corrected version undercounted tool calls at 590 by
counting scripted turns only; the figure covering every phase — scripted turns, compact, both
probes, and the resume — is 663. Cost accounting is explicitly descriptive and feeds no decision
rule, so adding these fields cannot change the pilot's outcome.

## Not deviations

For completeness, these were checked and found compliant:

- run order matched the registered schedule, position for position;
- the single excluded run was replaced immediately, before the next scheduled run and before any
  aggregate, using one of the two permitted replacements;
- the exclusion fired on the frozen validity check (final-eight marker-material reread), not on the
  run's score — that run had scored 6/6;
- every run recorded `scored: true`, the pinned model, and the pinned Claude Code version;
- the decision rule that fired is the one the registered ordering selects;
- the rule-ordering amendment landed before the first scored run, not during the pilot.
