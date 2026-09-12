---
title: Benchmark failure modes found during the H1 pilot
date: 2026-09-13
tags: [benchmark, methodology, integrity, failure-modes]
status: final
type: experiment-record
---

# Benchmark failure modes found during the H1 pilot

Every phase of this work passed through an independent read-only gate (Codex CLI, GPT-6 Astra) with
no authority to change code and no role in scoring. It blocked nine times.

> [!note]
> **The block count is not the point and is not a contribution.** Nine blocks do not show that nine
> gates are necessary, and they do not make the negative result stronger. What is reusable is the
> set of concrete failure modes below: each one produced a measurement that looked correct, each is
> reproducible, and each would have silently corrupted a comparison that any similar harness could
> attempt.

Each case gives the symptom, why the existing checks missed it, how it was reproduced, and what
replaced it. The last column of every fix is the same idea: **stop enumerating the ways something
can go wrong and check the invariant that actually has to hold.**

---

## 1. Cross-arm contamination through a host plugin hook

**Symptom.** Every arm scored 6/6 on the canaries. The fixture looked saturated.

**Actual cause.** The host's user settings loaded a plugin whose `SessionStart` hook injects a saved
session summary. Each benchmark arm therefore started with the **previous arm's** summary in
context: A → B → C → D. The arms were not independent, and the apparent saturation was the leak.

**Why the harness missed it.** It controlled everything it created — prompts, assets, hook settings,
environment variables — and never asked what the host contributed to a session it did not create.

**Reproduction.** In a pre-control run, `turn-00.jsonl` for arm B contains a `SessionStart:startup`
hook result whose `additionalContext` begins `Previous session summary:` and names
`Project: fixture-v3-A-…`. Arms C and D name B and C respectively.

**Fix.** `--setting-sources project` on every invocation, which excludes user settings without
touching authentication. Isolation is then **verified per run rather than assumed**:
`host_surface_observed` records the plugin/skill/MCP counts the session actually loaded, and
`unexpected_hooks` records any hook execution the fixture did not install. A run with either is
invalid.

**Generalisable.** A benchmark that runs an agent on a developer machine inherits that machine's
configuration. Record what the session loaded, not what you intended it to load.

---

## 2. Isolation deleted the treatment it was protecting

**Symptom.** After fixing (1), arms B and C had a `WORKING_STATE.md` file but **zero** canaries in
it. The manipulation check failed.

**Actual cause.** `.claude/` is a built-in sensitive path. Excluding host settings also removed the
permission posture that had been allowing the write, so the model tried to save state and was
refused. The transcript says so directly: *"I don't have permission to write to that file — it's
flagged as sensitive."*

**Why it matters.** The arms were now properly isolated **and** unable to exhibit the behaviour
under test. A contamination fix had quietly removed the treatment.

**Reproduction.** With `--setting-sources project` alone, and additionally with `acceptEdits`,
`dontAsk`, and explicit `permissions.allow` rules for the path, the write is refused. Only
`--permission-mode auto` allows it.

**Fix.** `--permission-mode auto` on every arm — the posture the host had been supplying implicitly,
now declared explicitly, applied identically everywhere, and deliberately not `bypassPermissions`.

**Generalisable.** After tightening an environment, check that the thing being measured can still
happen. A manipulation check is what catches this; without one, the run would have produced clean,
meaningless numbers.

---

## 3. Retrieval masquerading as recall

**Symptom.** None. This was found by inspection, not by a failing run.

**Actual cause.** The post-compaction probe was described as "tools disabled" but was implemented as
a denylist. `TaskOutput` — which retrieves persisted task output — was not on it. A probe could
fetch the canaries instead of remembering them and score 1.0.

**Why the harness missed it.** A denylist cannot be complete. New tools ship with new releases, and
the list was written against the tools that existed when it was written.

**Reproduction.** A synthetic probe response containing one `TaskOutput` retrieval scored 1.0 and
the run remained valid.

**Fix.** The enforced invariant is behavioural, not nominal: `probe_tool_uses` and
`semantic_probe_tool_uses` are recorded per run and **must both be zero**. Any tool use during a
probe invalidates the run, whatever the tool was. An unrecorded count is also rejected — absent
evidence is not evidence of a clean probe. The denylist remains as a first line of defence.

**Generalisable.** If a measurement depends on the subject *not* doing something, check that it
didn't, rather than listing the ways it could have.

---

## 4. Four ways to reread protected material undetected

**Symptom.** None observed in a real run; all four found by inspection.

The fixture forbids rereading marker-bearing documents in the final eight turns before the
compaction boundary. Detection failed four separate times, each in a different way:

| # | evasion | why it worked |
|---|---|---|
| a | `Grep` over `docs/contract.md` | detection inspected only `Read.file_path` and `Bash.command` |
| b | `cd .claude/context-guard && head WORKING_STATE.md` | serialising the tool input appended `"}`, so an `endswith()` check stopped matching |
| c | `cd docs && cat contract.md` | needles were path-qualified (`docs/contract.md`), so a bare filename after a directory change missed |
| d | `rg -n external_id .` | the input names no document and the output contains no canary — but the hits **are** the document's content |

**Fix.** Detection no longer depends on knowing which tool was used or how the path was spelled. It
searches the **entire serialised input of every tool call** and the **text every tool returned**,
matching four marker documents by bare filename declared in a single tuple. Echo detection searches
the whole event stream, including tool results.

One subtlety worth recording: the scripted prompts themselves name those documents, in order to
forbid reopening them. Searching the whole event stream indiscriminately would have invalidated
every valid run. Prompt text is therefore excluded, and a regression pins that distinction.

**Generalisable.** (d) is the interesting one. Three of these are spelling variations; the fourth is
categorically different, because what the agent asked for and what it received are different
objects. Inspecting only requests misses contamination that arrives in responses.

---

## 5. A decision rule that could hide an adverse result

**Symptom.** None — found in the pre-registration before any scored run.

**Actual cause.** Section 4 forbade a secondary-only GO, while section 5 handed the decision to the
secondary endpoint whenever the primary saturated. A primary result of B=1.0, C=0.0 — a clear
result **against** the treatment — would have been declared inconclusive, and the secondary endpoint
could then have produced GO.

**Fix.** The primary endpoint always decides; the secondary is descriptive. Saturation requires
**both** arms at the extreme, since a high `mean(B)` with a different `mean(C)` is a measurable
contrast, not a ceiling. Rules are evaluated in a fixed order with `d < 0` **before** saturation, so
an adverse contrast can never be reported as inconclusive.

**Verification.** The gate enumerated 5,766 aggregate/count combinations and confirmed every
non-positive contrast selects the adverse rule and every GO satisfies both registered thresholds.

**Generalisable.** A fallback path in a decision rule is a place where the answer can change without
the evidence changing. Enumerate the outcomes the rule can produce before running anything.

---

## 6. Optional retries as result-dependent sampling

**Symptom.** None — found in the pre-registration before any scored run.

**Actual cause.** Invalid runs *could* be replaced but were not *required* to be. The operator could
therefore see the results and then decide whether to re-run.

**Reproduction.** The gate constructed a case where replacing an invalid run flips the decision from
GO to STOP, and the choice of whether to replace was left to the operator.

**Fix.** Replacement is mandatory and immediate — executed before the next scheduled run and before
anything is aggregated — capped at two, with a third exclusion ending the pilot as a hard blocker.

**Generalisable.** "May" in a protocol is a degree of freedom. If a step is allowed, specify when it
is required.

---

## 7. Errors in the write-up itself

Three blocks in the final phase were mistakes in how I described the completed result, not in the
result. Two of them would have made the finding look stronger than it is:

- the excluded run was reported as scoring 6/6; it scored **0/6**. That inverts the meaning of the
  exclusion: because the run scored zero, removing it **raised** the treatment arm's mean, from
  0.833 to 1.0, and the contrast from 1/30 to 1/5. The sensitivity analysis now in
  [[h1-pilot-results]] exists because of this correction;
- the deviation record claimed executing from the pinned commit was *impossible*. It was not — the
  registered per-run command existed at that commit. Writing an orchestration script was a choice,
  and it moved execution off the pin;
- tool-call totals counted scripted turns only (590 rather than 663).

**Generalisable, and uncomfortable.** The measurement was sound before these errors and after them.
The write-up was not, and the errors ran in the direction that favoured the project. An independent
reader who checks numbers against stored records catches this; self-review did not.

---

## What this record supports

- these seven failure modes are reproducible and reusable by anyone building a similar harness;
- the H1 result is bounded by its fixture and stated in [[h1-pilot-results]];
- **not supported**: that rehydration is redundant in general, that this review process is superior
  to others, or that the number of blocks measures anything.

Raw runs remain local under a gitignored directory. Sharing them would be a prerequisite for anyone
independently reproducing the cases above.
