# Technology Stack

This document lists the tools, libraries, and runtime environment used by the evaluation system.

## Components

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Local LLM runtime | llama.cpp (llama-server) |
| Cloud LLM APIs | OpenRouter (OpenAI-compatible), openai, google-generativeai SDKs |
| RAG embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector store | ChromaDB (preferred; evaluate during Phase 3) |
| RAG orchestration | LlamaIndex (preferred; evaluate during Phase 3) |
| Test runner | pytest or custom harness |
| Results storage | SQLite |
| Reporting | pandas + matplotlib/plotly for comparison charts |

## Runtime Environment

- macOS 26.2
- Apple M4 MacBook Air, 32GB RAM
- Python virtual environment

## Project Structure (Proposed)

```text
samantha2/
├── README.md
├── pyproject.toml
├── config/
│   ├── models.yaml          # Model definitions and connection params
│   └── settings.yaml         # RAG settings, evaluation parameters, etc.
├── knowledge_base/
│   ├── workflow_states.yaml   # State machine definition
│   ├── sops/
│   │   ├── accessioning.md
│   │   ├── sample_prep.md
│   │   ├── he_staining.md
│   │   ├── ihc_staining.md
│   │   └── resulting.md
│   └── rules/
│       ├── breast_ihc_panels.md
│       └── fixation_requirements.md
├── src/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract model interface
│   │   ├── llamacpp_adapter.py # Local models via llama-server
│   │   ├── openrouter_adapter.py
│   │   ├── openai_adapter.py
│   │   └── google_adapter.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── indexer.py         # Document indexing
│   │   ├── retriever.py       # Query and retrieval
│   │   └── chunker.py         # Section-aware chunking
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── state_machine.py   # Workflow state definitions and validation
│   │   └── validator.py       # Ground-truth evaluation
│   ├── simulator/
│   │   ├── __init__.py
│   │   ├── order_generator.py # Synthetic order creation
│   │   └── event_generator.py # Event sequence generation
│   ├── prediction/
│   │   ├── __init__.py
│   │   ├── engine.py          # Prediction pipeline (RAG + prompt + model)
│   │   └── prompt_template.py # Standardized prompt
│   └── evaluation/
│       ├── __init__.py
│       ├── harness.py         # Test runner
│       ├── metrics.py         # Accuracy, FP rate, reliability calculation
│       └── reporter.py        # Comparison report generation
├── scenarios/
│   ├── rule_coverage/
│   ├── multi_rule/
│   ├── accumulated_state/
│   └── unknown_inputs/
├── results/                   # Output from evaluation runs
└── notebooks/                 # Analysis notebooks (optional)
```

## Related Documents

- [Architecture](architecture.md) — how these technologies fit together
