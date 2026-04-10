# Implementation Todo

Work items in implementation order, organized by phase. Each item links to
its GitHub issue where one exists. Items within a phase are ordered by
dependency — earlier items unblock later ones.

**Legend:** R = Routing track, Q = Query track, B = Both tracks

**IDs and dependencies:** Each item has an ID used in the Blocked By column.
Items with GitHub issues use `GH-<number>`. Unfiled items use a
phase-prefixed letter (e.g., `3a` = Phase 3, first unfiled item).

## Phase 1: Foundation (Complete)

| ID | Track | Issue | Status |
|----|-------|-------|--------|
| GH-8 | B | [Project scaffolding](https://github.com/ChrisHenryOC/samantha/issues/8) | Done |
| GH-9 | B | [Define workflow state machine in YAML](https://github.com/ChrisHenryOC/samantha/issues/9) | Done |
| GH-10 | B | [Create knowledge base SOP documents](https://github.com/ChrisHenryOC/samantha/issues/10) | Done |
| GH-11 | B | [Create knowledge base rule catalog documents](https://github.com/ChrisHenryOC/samantha/issues/11) | Done |
| GH-12 | B | [Build data models and SQLite persistence layer](https://github.com/ChrisHenryOC/samantha/issues/12) | Done |
| GH-13 | B | [Implement workflow state machine and validation](https://github.com/ChrisHenryOC/samantha/issues/13) | Done |
| GH-21 | B | [Fix defects found by red-team testing](https://github.com/ChrisHenryOC/samantha/issues/21) | Done |
| GH-23 | B | [Document Phase 1 learnings, update docs for Phase 2](https://github.com/ChrisHenryOC/samantha/issues/23) | Done |

### Phase 1 — Deferred Findings

| ID | Track | Issue | Status |
|----|-------|-------|--------|
| GH-19 | B | [Deferred review findings from PR #18](https://github.com/ChrisHenryOC/samantha/issues/19) | Done |
| GH-36 | B | [Deferred review findings from PR #35](https://github.com/ChrisHenryOC/samantha/issues/36) | Done |

## Phase 2: Simulator

### Routing Scenarios

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-24 | R | [Scenario JSON schema, dataclasses, and file loader](https://github.com/ChrisHenryOC/samantha/issues/24) | Done | — |
| GH-25 | R | [Scenario validator (ground-truth consistency checker)](https://github.com/ChrisHenryOC/samantha/issues/25) | Done | — |
| GH-26 | R | [Order generator with synthetic patient data](https://github.com/ChrisHenryOC/samantha/issues/26) | Done | — |
| GH-27 | R | [Event sequence builder and workflow path templates](https://github.com/ChrisHenryOC/samantha/issues/27) | Done | — |
| GH-42 | R | [Add path templates for remaining 10 rule catalog entries](https://github.com/ChrisHenryOC/samantha/issues/42) | Done | — |
| GH-28 | R | [Author accessioning rule coverage scenarios (ACC-001..008)](https://github.com/ChrisHenryOC/samantha/issues/28) | Done | — |
| GH-29 | R | [Author sample prep rule coverage scenarios (SP-001..006)](https://github.com/ChrisHenryOC/samantha/issues/29) | Done | GH-42 |
| GH-30 | R | [Author H&E / pathologist review scenarios (HE-001..009)](https://github.com/ChrisHenryOC/samantha/issues/30) | Done | GH-42 |
| GH-31 | R | [Author IHC rule coverage scenarios (IHC-001..011)](https://github.com/ChrisHenryOC/samantha/issues/31) | Done | GH-42 |
| GH-32 | R | [Author resulting rule coverage scenarios (RES-001..005)](https://github.com/ChrisHenryOC/samantha/issues/32) | Done | GH-42 |
| GH-33 | R | [Author multi-rule, accumulated state, and unknown input scenarios](https://github.com/ChrisHenryOC/samantha/issues/33) | Done | GH-29 – GH-32 |
| GH-34 | R | [Scenario coverage report and Phase 2 integration tests](https://github.com/ChrisHenryOC/samantha/issues/34) | Done | GH-33 |

### Query Scenarios

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-45 | Q | [Document query evaluation track in spec docs](https://github.com/ChrisHenryOC/samantha/issues/45) | Done | — |
| GH-46 | Q | [Design query scenario schema and dataclasses](https://github.com/ChrisHenryOC/samantha/issues/46) | Done | GH-45 |
| GH-47 | Q | [Author worklist and order-status query scenarios (Tiers 1-2)](https://github.com/ChrisHenryOC/samantha/issues/47) | Done | GH-46 |
| GH-48 | Q | [Author complex reasoning query scenarios (Tiers 3-5)](https://github.com/ChrisHenryOC/samantha/issues/48) | Done | GH-46, GH-47 |

### Red-Team Testing

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-65 | Q | [Redteam: query scenario schema type confusion and boundary tests](https://github.com/ChrisHenryOC/samantha/issues/65) | Done | GH-46 |
| GH-66 | Q | [Redteam: query scenario loader robustness tests](https://github.com/ChrisHenryOC/samantha/issues/66) | Done | GH-46 |
| GH-67 | B | [Redteam: database layer robustness tests](https://github.com/ChrisHenryOC/samantha/issues/67) | Done | GH-12 |

### Phase 2 — Deferred Findings

| ID | Track | Issue | Status |
|----|-------|-------|--------|
| GH-56 | R | [Replace invalid "stat" priority with "rush" across scenarios](https://github.com/ChrisHenryOC/samantha/issues/56) | Done |

## Phase 3: Model Integration

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-76 | B | [Validate local model feasibility (RAM, speed)](https://github.com/ChrisHenryOC/samantha/issues/76) | Done | — |
| GH-77 | B | [Quantization impact check for constrained local models](https://github.com/ChrisHenryOC/samantha/issues/77) | Done | GH-76 |
| GH-78 | B | [Implement model config and abstraction layer](https://github.com/ChrisHenryOC/samantha/issues/78) | Done | — |
| GH-79 | B | [Build ollama adapter for local models](https://github.com/ChrisHenryOC/samantha/issues/79) | Done | GH-78 |
| GH-80 | B | [Build Anthropic adapter for cloud baseline](https://github.com/ChrisHenryOC/samantha/issues/80) | Done | GH-78 |
| GH-92 | B | [Build OpenRouter adapter for cloud Claude models](https://github.com/ChrisHenryOC/samantha/issues/92) | Done | GH-78 |
| GH-81 | R | [Implement routing prompt template](https://github.com/ChrisHenryOC/samantha/issues/81) | Done | GH-78 |
| GH-49 | Q | [Implement query prompt template](https://github.com/ChrisHenryOC/samantha/issues/49) | Done | GH-78, GH-46 |
| GH-82 | B | [Build prediction engine](https://github.com/ChrisHenryOC/samantha/issues/82) | Done | GH-78, GH-81 |
| GH-95 | R | [Add explicit state and flag vocabularies to routing prompt](https://github.com/ChrisHenryOC/samantha/issues/95) | Done | GH-81 |

## Phase 4: Full-Context Baseline

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-99 | B | [Build evaluation harness (run orchestration, result collection)](https://github.com/ChrisHenryOC/samantha/issues/99) | Done | GH-79, GH-80, GH-82 |
| GH-112 | B | [Evaluation runner: incremental writes, scenario limit, cost optimizations](https://github.com/ChrisHenryOC/samantha/issues/112) | Done | GH-99 |
| GH-113 | R | [Ground truth bugs: flag propagation + slide state not advanced](https://github.com/ChrisHenryOC/samantha/issues/113) | Done | GH-99 |
| GH-100 | R | [Run routing scenarios — all models, full context](https://github.com/ChrisHenryOC/samantha/issues/100) | Done | GH-99, GH-81 |
| GH-116 | R | [Add ACC-009 rule for null fixation time → MISSING_INFO_HOLD](https://github.com/ChrisHenryOC/samantha/issues/116) | Done | — |
| GH-117 | B | [Implement per-step early-abort for broken models](https://github.com/ChrisHenryOC/samantha/issues/117) | Done | GH-99 |
| GH-101 | R | [Routing baseline analysis and reporting](https://github.com/ChrisHenryOC/samantha/issues/101) | Done | GH-100, GH-116 |
| GH-50 | Q | [Implement query response validation and scoring](https://github.com/ChrisHenryOC/samantha/issues/50) | Done | GH-99, GH-49 |
| GH-97 | B | [Add integration test: vocabulary sections reduce hallucination failures](https://github.com/ChrisHenryOC/samantha/issues/97) | Done | GH-99 |
| GH-98 | B | [Add cross-module sync test: prompt vocabularies match validator sources](https://github.com/ChrisHenryOC/samantha/issues/98) | Done | GH-95 |
| GH-102 | Q | [Run query scenarios — all models, full context](https://github.com/ChrisHenryOC/samantha/issues/102) | Done | GH-50 |
| GH-127 | Q | [Fix query baseline issues before full evaluation runs](https://github.com/ChrisHenryOC/samantha/issues/127) | Done | GH-102 |
| GH-131 | Q | [Fix query scenario ground truth and prompt gaps from baseline analysis](https://github.com/ChrisHenryOC/samantha/issues/131) | Done | GH-102 |
| GH-103 | Q | [Query baseline analysis and reporting](https://github.com/ChrisHenryOC/samantha/issues/103) | Done | GH-127, GH-131 |
| GH-104 | B | [Combined baseline report (routing + query)](https://github.com/ChrisHenryOC/samantha/issues/104) | Done | GH-101, GH-103 |
| GH-121 | R | [Filter aborted runs from analysis calculations](https://github.com/ChrisHenryOC/samantha/issues/121) | Done | GH-101 |

## Phase 5: RAG Pipeline

PR [#139](https://github.com/ChrisHenryOC/samantha/pull/139) implements the
RAG pipeline: section-aware chunker, ChromaDB indexer, retrieval pipeline,
engine/harness integration, retrieval quality tests, and comparison report code.

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| PR-139a | B | Implement section-aware document chunker | Done (PR #139) | — |
| PR-139b | B | Build RAG indexer with ChromaDB | Done (PR #139) | PR-139a |
| PR-139c | B | Build retrieval pipeline | Done (PR #139) | PR-139b |
| PR-139d | B | Integrate RAG with prediction engine and prompt template | Done (PR #139) | PR-139c |
| PR-139e | B | Test retrieval quality | Done (PR #139) | PR-139c |
| PR-139f | B | Add RAG mode to evaluation harness | Done (PR #139) | PR-139d |
| PR-139g | B | RAG comparison report code | Done (PR #139) | PR-139f |
| GH-140 | R | [Run routing evaluation with RAG](https://github.com/ChrisHenryOC/samantha/issues/140) | Done | PR-139f, PR-139e |
| GH-141 | Q | [Run query evaluation with RAG](https://github.com/ChrisHenryOC/samantha/issues/141) | Done | PR-139f, PR-139e |
| GH-73 | B | [Document cancel-old-slides / insert-new pattern in update_slide](https://github.com/ChrisHenryOC/samantha/issues/73) | Open | PR-139b |
| GH-106 | R | [Add scenario linter: warn on flag accumulation inconsistencies](https://github.com/ChrisHenryOC/samantha/issues/106) | Done | — |

## Phase 6: Evaluation and Iteration

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-154 | B | [Fix Phase 5 RAG summary.json files from per-run data](https://github.com/ChrisHenryOC/samantha/issues/154) | Done | GH-140, GH-141 |
| GH-155 | B | [Document Phase 5 RAG evaluation results](https://github.com/ChrisHenryOC/samantha/issues/155) | Done | GH-154 |
| GH-157 | B | [Create evaluation results index and migrate Phase 4 docs](https://github.com/ChrisHenryOC/samantha/issues/157) | Done | — |
| GH-156 | B | [Generate RAG vs baseline comparison report (Phase 6a)](https://github.com/ChrisHenryOC/samantha/issues/156) | Done | GH-154, GH-155 |
| GH-161 | R | [Diagnose rule accuracy collapse in RAG routing mode](https://github.com/ChrisHenryOC/samantha/issues/161) | Done | GH-156 |
| GH-162 | R | [Refine routing prompt template based on failure analysis (6b)](https://github.com/ChrisHenryOC/samantha/issues/162) | Done | GH-161 |
| GH-164 | Q | [Refine query prompt template based on failure analysis (6c)](https://github.com/ChrisHenryOC/samantha/issues/164) | Done | GH-156 |
| GH-163 | B | [Tune RAG retrieval parameters (6d)](https://github.com/ChrisHenryOC/samantha/issues/163) | Done | GH-161 |
| GH-165 | Q | [Expand query scenario coverage (6e — query track)](https://github.com/ChrisHenryOC/samantha/issues/165) | Open | — |
| GH-166 | R | [Add rule-citation routing scenarios (6e — routing track)](https://github.com/ChrisHenryOC/samantha/issues/166) | Open | — |
| GH-109 | B | [Harden runner.py output path validation and error handling](https://github.com/ChrisHenryOC/samantha/issues/109) | Done | — |
| GH-130 | Q | [Cache static state/flag reference text in query prompt renderer](https://github.com/ChrisHenryOC/samantha/issues/130) | Open | — |
| GH-147 | R | [H&E QC event incorrectly applied to IHC slides in harness](https://github.com/ChrisHenryOC/samantha/issues/147) | Open | GH-99 |

## Phase 7: Tool-Use Query Evaluation

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-176 | Q | [Tool definitions and executor](https://github.com/ChrisHenryOC/samantha/issues/176) | Done | — |
| GH-177 | Q | [Adapter chat interface for tool-calling](https://github.com/ChrisHenryOC/samantha/issues/177) | Done | — |
| GH-178 | Q | [Tool-use prediction engine](https://github.com/ChrisHenryOC/samantha/issues/178) | Done | GH-177 |
| GH-179 | Q | [Tool-use query harness](https://github.com/ChrisHenryOC/samantha/issues/179) | Done | GH-178 |
| GH-180 | Q | [Tool-use reporting and analysis](https://github.com/ChrisHenryOC/samantha/issues/180) | Done | GH-179 |

## Phase 8: Live Routing Loop & Chat Interface

Plan document: [phase8-plan.md](phase8-plan.md)

Track "B" below indicates these issues serve both routing and query
functionality in the live system (not the R/Q evaluation tracks from earlier
phases).

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-188 | B | [Routing service core](https://github.com/ChrisHenryOC/samantha/issues/188) | Done | — |
| GH-189 | B | [Live tool executor](https://github.com/ChrisHenryOC/samantha/issues/189) | Done | — |
| GH-190 | B | [FastAPI server and REST endpoints](https://github.com/ChrisHenryOC/samantha/issues/190) | Done | GH-188, GH-189 |
| GH-191 | B | [Order seeding and demo data](https://github.com/ChrisHenryOC/samantha/issues/191) | Done | GH-190 |
| GH-192 | B | [Chat service with streaming WebSocket](https://github.com/ChrisHenryOC/samantha/issues/192) | Done | GH-189, GH-190 |
| GH-193 | B | [Web frontend](https://github.com/ChrisHenryOC/samantha/issues/193) | Done | GH-190, GH-192 |
| GH-194 | B | [SSE updates, event bus, and launch script](https://github.com/ChrisHenryOC/samantha/issues/194) | Done | GH-190, GH-192, GH-193 |

## Follow-On

| ID | Track | Issue | Status | Blocked By |
|----|-------|-------|--------|------------|
| GH-128 | Q | [Add state_entered_at field to query scenario order data](https://github.com/ChrisHenryOC/samantha/issues/128) | Open | Phase 7 |
| GH-72 | B | [Investigate JSON serialization overhead in insert_decision](https://github.com/ChrisHenryOC/samantha/issues/72) | Open | GH-99 |

## Summary

Done counts track completed GitHub issues, not individual scenario files.

| Phase | Routing | Query | Both | Total | Done |
|-------|---------|-------|------|-------|------|
| 1 | — | — | 10 | 10 | 10 |
| 2 | 13 | 6 | 1 | 20 | 20 |
| 3 | 2 | 1 | 7 | 10 | 10 |
| 4 | 5 | 5 | 6 | 16 | 16 |
| 5 | 2 | 1 | 1 | 4 | 3 |
| 6 | 4 | 3 | 6 | 13 | 9 |
| 7 | — | 5 | — | 5 | 5 |
| 8 | — | — | 7 | 7 | 7 |
| Follow-on | — | 1 | 1 | 2 | 0 |
| **Total** | **26** | **22** | **39** | **87** | **80** |
