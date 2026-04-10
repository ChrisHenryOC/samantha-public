# CLAUDE.md

## Project Context

This is a POC for evaluating LLM models on laboratory workflow routing for breast cancer specimens. The spec is split across focused documents in `docs/`:

- `docs/workflow/` — lab workflow domain: [workflow-overview.md](docs/workflow/workflow-overview.md), [rule-catalog.md](docs/workflow/rule-catalog.md), [accessioning-logic.md](docs/workflow/accessioning-logic.md), [pathologist-review-panels.md](docs/workflow/pathologist-review-panels.md)
- `docs/technical/` — system design: [data-model.md](docs/technical/data-model.md), [architecture.md](docs/technical/architecture.md), [evaluation-metrics.md](docs/technical/evaluation-metrics.md), [technology-stack.md](docs/technical/technology-stack.md)
- `docs/project/` — planning: [implementation-phases.md](docs/project/implementation-phases.md), [open-questions.md](docs/project/open-questions.md), [evaluation-results-index.md](docs/project/evaluation-results-index.md)
- `docs/scenarios/` — test design: [scenario-design.md](docs/scenarios/scenario-design.md)

## Key Concepts

- **Rule catalog**: Discrete rules with trigger conditions and prescribed actions, organized by workflow step. The model's job is to match rules, not invent behavior.
- **Persistence model**: SQLite with orders, slides, events, decisions, and runs tables. Events and order state are strictly separate.
- **Local models are the real candidates** — cloud models are ceiling benchmarks only. Labs won't send PHI to cloud APIs.
- **Variance matters as much as accuracy** — local models run 5x per scenario to measure consistency.

## Architecture

- `config/` — model definitions and evaluation parameters
- `docs/` — specification and design documents
- `knowledge_base/` — SOPs and rule catalog (RAG corpus)
- `src/` — Python source code
  - `models/` — model adapters (ollama, Anthropic, OpenAI, Google)
  - `rag/` — indexing, retrieval, chunking
  - `workflow/` — state machine, validation
  - `simulator/` — order and event generation
  - `prediction/` — prediction engine and prompt template
  - `evaluation/` — test harness, metrics, reporting
- `scenarios/` — test scenario definitions
- `results/` — evaluation run outputs

## Git Workflow

- **Never commit directly to main.** All changes go to a feature branch, then to main via a pull request.
- **Never chain `git commit` or `git push` with `&&` in a single Bash call.** Each must be a separate tool call so the permission system can prompt for approval. `git add` may be chained freely.
- Squash merges are disabled on this repo. Use standard merge commits.
- Branch naming: descriptive kebab-case (e.g., `feature/add-rag-pipeline`, `fix/accessioning-rules`).

## Slash Commands

- `/review-pr <number> [aspects]` — run multi-agent code review on a PR (optional: `tests`, `security`, `workflow`, `types`, etc.)
- `/fix-review <number>` — fix issues found by code review
- `/issue <number|next>` — analyze and fix a GitHub issue
- `/merge-pr <number>` — merge a PR and clean up branches

## Review Agents

All agents are in `.claude/agents/`. They run in parallel during `/review-pr`:

- **code-quality-reviewer** (sonnet) — clean code, error handling, Python standards
- **security-code-reviewer** (sonnet) — OWASP, API key management, data handling
- **silent-failure-hunter** (sonnet) — silent failures, inadequate error handling, unjustified fallbacks
- **test-coverage-reviewer** (sonnet) — coverage gaps, test quality, project-specific scenarios
- **workflow-logic-reviewer** (opus) — state machine correctness, rule catalog integrity, ground truth validation
- **performance-reviewer** (sonnet) — algorithmic complexity, RAG pipeline, evaluation harness efficiency
- **type-design-reviewer** (haiku) — dataclass invariants, type safety, making illegal states unrepresentable
- **documentation-accuracy-reviewer** (haiku) — docstrings, type hints, spec consistency
- **code-simplifier** (sonnet) — post-fix simplification pass, invoked by `/fix-review`

Model tiers: **opus** for domain-critical reasoning (workflow logic); **sonnet** for complex but pattern-based analysis; **haiku** for mechanical matching tasks.

All findings require confidence >= 76/100. Each finding includes a confidence score.

## Implementation Approach

- Before implementing any fix or feature, first read the relevant existing code to understand context, patterns, and dependencies.
- Do not assume which APIs, libraries, or patterns are in use — verify by reading the source files.
- For bug fixes, trace the code path that's failing before proposing a fix.

## Automated Hooks

Claude Code hooks in `.claude/settings.json` automate two checks:

- **mypy (PostToolUse)**: Runs `mypy` on each `.py` file after Edit/Write. Advisory only — prints errors but does not block. For a full cross-module check, run `uv run mypy src/` manually.
- **pytest (PreToolUse)**: Runs `uv run pytest` before any `git commit` command. Blocks the commit (exit 2) if tests fail.

These hooks require `jq` to be installed. Hook scripts are in `.claude/hooks/`.

## Conventions

- Python 3.12+
- All model outputs are structured JSON: `next_state`, `applied_rules`, `flags`, `reasoning`
- No retries on model failures — failures are scored as incorrect and categorized by type
- Scenario ground truth includes both expected state and expected rule IDs
- Use `uv` for dependency management
- Run tests: `uv run pytest` (also enforced by pre-commit hook)
- Lint code: `uv run ruff check src/ tests/`
- Lint documents: `markdownlint-cli2 --fix "**/*.md"`
- Type check: `uv run mypy src/` (per-file checks run automatically via hook; full project check is manual)

## Type-Safety Conventions

- Validate types before `set()` / `frozenset()` conversion — never pass a raw string where a list is expected.
- Validate list elements are strings before `Counter` / `set` operations.
- Use `__post_init__` validation in frozen dataclasses for type and value checks.

## Secrets

- **OpenRouter API key** is stored in `notes/openrouter-api-key.txt`. Load it from the file rather than hardcoding it — e.g. `OPENROUTER_API_KEY=$(cat notes/openrouter-api-key.txt)`.
- Never echo, print, or inline secret values in commands. Always read from the file at runtime.

## Markdown Conventions

These apply to every `.md` file written in this project, including review output, generated documents, and agent findings.

- Every fenced code block must have a language identifier. Use `text` when the content is not a specific language. `---` is not okay. `---text` is acceptable.
- After saving markdown files, run `markdownlint-cli2 --fix "<filename>"` on the new or updated file.
