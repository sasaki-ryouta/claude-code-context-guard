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

**Why.** The pre-registration contained an internal contradiction that was not noticed when it was
written: `ca5e677` is the commit at which the *fixture* was frozen, but it does not contain
`run_pilot.py` or `aggregate_pilot.py` — those were written afterwards, deliberately committed
before any scored run so the schedule and decision rules could not be adjusted later. Executing the
registered pilot from the registered commit was therefore impossible. The pin named the wrong
object: it should have pinned the fixture *inputs*, not the repository tip.

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
at the commit the document named. The hashes establish the narrower claim that the treatment,
prompts, canaries, scoring, and arm construction were identical to the frozen fixture, so the
deviation does not give any arm an advantage and does not change what was measured.

**Fix for future pilots.** Pin the fixture-input tree hash, not a repository commit, and record
both the input hash and the execution commit per run.

## Deviation 2 — cost accounting omitted two registered fields

**Registered.** Section 11 lists "number of scripted turns and tool calls" among the per-run cost
measurements.

**What happened.** The first `cost.json` omitted both. They were added from the stored run records
after the gate pointed this out. Cost accounting is explicitly descriptive and feeds no decision
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
