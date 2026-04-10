# Implementation Phases

This document outlines the phases of the project, from foundation through evaluation.

## Phase 1: Foundation (Complete)

Phase 1 deliverables:

- YAML state machine — 26 states, 40 rules, 5 flags
- Knowledge base SOPs and panel rule documents
- Data models with SQLite persistence (orders, slides, events, decisions, runs)
- State machine engine with prediction validator
- Comprehensive test suite (255+ passing tests, 14 xfailed)

## Phase 2: Simulator (Complete)

Phase 2 deliverables:

- Scenario schema with frozen dataclasses (ExpectedOutput, ScenarioStep, Scenario)
- Scenario file loader with JSON-to-dataclass mapping and validation
- Ground-truth scenario validator (10 consistency checks against state machine)
- Order generator with synthetic patient data
- Event builder for all 18 event types
- 104 test scenarios across 4 categories (rule_coverage, multi_rule,
  accumulated_state, unknown_input)
- Coverage report tool with gap detection
- 40/40 rules covered with 2+ scenarios each, all 5 flags exercised
- Integration test suite (9 tests) verifying corpus completeness

**Query track (planned — not yet complete):**

- Query scenario schema (database state snapshot + question + expected answer)
- 15 query scenarios across 5 tiers (simple lookup, order status, flag reasoning,
  prioritization, cross-order reasoning)
- Query scenario validator (verifies order IDs in expected output exist in database
  state, verifies states are valid)

## Phase 3: Model Integration

- **Validate local model feasibility first** — pull each candidate model in ollama,
  run a simple test prompt, and measure RAM usage and inference speed. If a model
  exceeds available memory (32GB) or too slow, substitute a
  smaller quantization or a different model before investing in adapter code.
- **Quantization impact check** — for models that require quantization to fit in
  memory (e.g., Llama 70B at Q4), run at full precision via a cloud API provider
  (Groq, Together) on a small set of test prompts. If the full-precision version
  scores significantly better, quantization is a meaningful degradation factor and
  alternative quantization levels (Q5, Q6) should be tested before proceeding.
- Implement model abstraction layer (config, base class, response dataclass)
- Build ollama adapter (local models)
- Build Anthropic adapter (cloud baseline — Haiku, Sonnet, Opus cover three
  capability tiers from a single SDK; OpenAI and Google deferred to post-Phase 6)
- Standardized prompt template (routing + query modes)
- Build prediction engine for full-context evaluation (prompt rendering + model
  call + response parsing; RAG integration deferred to Phase 5)

## Phase 4: Full-Context Baseline

- Stuff the entire knowledge base (SOPs + rule catalog) into the prompt context
- Run all routing scenarios against all models with full context
- **Query track**: stuff the database state snapshot + workflow reference into the
  prompt alongside the query. Run all 15 query scenarios against all models.
- This serves as a feasibility check and performance ceiling — if models fail with
  full context, RAG retrieval won't help
- If models succeed, this validates the task is achievable and provides a baseline
  to compare RAG against
- Analyze results before investing in RAG pipeline

## Phase 5: RAG Pipeline

- Index knowledge base documents
- Implement section-aware chunking
- Build retrieval pipeline
- Test retrieval quality (are the right chunks returned for each scenario type?)
- Re-run evaluation and compare against full-context baseline
- Key question: does RAG retrieval degrade performance vs full context, or does
  focused context help smaller models?

## Phase 6: Evaluation & Iteration

- Build test harness (if not already built in Phase 4)
- Generate comparison reports (full-context vs RAG, local vs cloud)
- ~~**Query track**: generate separate query evaluation reports by tier, analyze
  failure patterns (wrong order sets vs. wrong reasoning vs. query misinterpretation)~~
  **Done** (GH-103) — `src/evaluation/query_analysis.py`
- Refine prompt template based on failure analysis
- Adjust RAG retrieval parameters
- Add/modify scenarios based on findings

## Phase 7: Tool-Use Query Evaluation (Planned)

Give models callable tools instead of context-stuffing the entire
database state into the prompt. Rerun the same 27 query scenarios to
directly compare context-stuffing vs tool-use — targeting the T4
(prioritized list) ceiling at 0%.

See [Phase 7 plan](phase7-tool-use-plan.md) for the full design.
Issues: #176, #177, #178, #179, #180.

## Phase 8: Live Routing Loop & Chat Interface

Transition from offline evaluation to a live interactive system. Phase 8 builds
a FastAPI server with a live routing loop (event ingestion, LLM-based
next-state prediction, validation, DB update) and a streaming chat interface
where lab personnel can see their work queue and interact with the workflow
via a locally hosted LLM.

See [Phase 8 plan](phase8-plan.md) for the full design.
Issues: #188, #189, #190, #191, #192, #193, #194.

## Follow-On (Post Phase 8)

- **Prompt tuning per model** — after the standardized comparison is complete,
  explore per-model prompt optimization to measure how much headroom exists beyond
  the standardized baseline. Prerequisites: Phase 6 results with standardized prompts
  must be complete first.

## Related Documents

- [Architecture](../technical/architecture.md) — system design
- [Technology Stack](../technical/technology-stack.md) — tools and runtime
