# Samantha

A proof-of-concept exploring whether locally-deployed LLMs can reliably route laboratory workflow.  The short answer: yes, with the right prompt design and model selection, a 32B-parameter model running on local hardware achieved 99.7% state routing accuracy across 111 routing steps, without any model fine-tuning.

This is a research project, not a product.  The workflow covers breast cancer histology specimen processing (accessioning through resulting), and the system evaluates how well various LLM models predict the correct next step given an order's current state and a new event.

**The model is a workflow traffic cop, not a diagnostician.**  It routes orders between steps and identifies issues.  All clinical decisions require pathologist approval.

## Why "Samantha"?

A name associated with humans, gender-neutral, with options for abbreviation (Sam, Sammy).  Also, one of my favorite characters from the television series ER was [Samantha Taggart](https://en.wikipedia.org/wiki/Samantha_Taggart), a badass nurse who really got things done.

## Key Findings

1. **Local LLMs can reliably route lab workflows.**  With skills-based prompting, locally-deployed 32B-class models achieve 99%+ accuracy on structured workflow routing.  Patient data never leaves your network.

2. **The hybrid architecture is the right answer.**  38 of 40 workflow rules are fully deterministic (null checks, threshold comparisons, enum lookups).  A rules engine handles those with 100% accuracy.  The LLM adds value on the remaining 5% that require judgment, context interpretation, and explainability.

3. **Model selection matters more than model size.**  A 32B coder model (Qwen 2.5 Coder 32B) outperformed a 70B general-purpose model (Llama 3.3 70B).  A 27B model (Gemma 3 27B) achieved 100% accuracy on multi-step workflows at 15x the speed.

4. **How you structure information for the model matters more than the model itself.**  The journey from 62% to 99.7% accuracy happened entirely through prompt engineering, no fine-tuning.  The single biggest lever was restructuring a monolithic rule catalog into individual "skill" documents.

5. **Quantization works.**  A 32B model quantized to 4-bit delivers 98.5% routing accuracy on hardware accessible to most labs.

For the full writeup, see the companion article: [LLMs and Laboratory Workflow](https://chenryventures.substack.com/) (Substack).

## What's in This Repo

```
src/                    # Python source code
  evaluation/           # Test harness, metrics, reporting
  models/               # Model adapters (llama.cpp, OpenRouter, Ollama)
  prediction/           # Prompt templates and skill loader
  rag/                  # Vector indexing and retrieval (ChromaDB)
  server/               # FastAPI web application
  simulator/            # Order/event generation and scenario loading
  workflow/             # State machine, validation
knowledge_base/         # The domain knowledge the LLM reads
  skills/               # Individual rule documents (the key innovation)
  sops/                 # Standard operating procedures
  rules/                # Reference rule definitions
config/                 # Model definitions and evaluation parameters
scenarios/              # 100+ test scenarios across 6 categories
tests/                  # Unit tests and red team tests
scripts/                # Evaluation and utility scripts
docs/                   # Technical and workflow documentation
```

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- For local models: [llama.cpp](https://github.com/ggerganov/llama.cpp) with `llama-server`
- For cloud models (optional): an [OpenRouter](https://openrouter.ai/) account and API key

### 1. Clone and install dependencies

```bash
git clone https://github.com/ChrisHenryOC/samantha-public.git
cd samantha-public
uv sync
```

### 2. Install llama.cpp

Samantha uses [llama.cpp](https://github.com/ggerganov/llama.cpp) to run models locally.  You need the `llama-server` binary.

**macOS (Homebrew):**
```bash
brew install llama.cpp
```

**Build from source (Linux/macOS):**
```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
cmake -B build
cmake --build build --config Release
# The binary is at build/bin/llama-server
```

Verify it's installed:
```bash
llama-server --version
```

### 3. Download a model

Models are GGUF-format files hosted on HuggingFace.  The download script pulls all models defined in `config/models.yaml`:

```bash
# See what would be downloaded (no actual download)
./scripts/download_models.sh --dry-run

# Download all configured models
./scripts/download_models.sh
```

To get started quickly with a single model, you can skip the script and download one directly.  Qwen 2.5 Coder 32B (Q4 quantization) is the top performer and a good starting point:

```bash
llama-server \
  -hf bartowski/Qwen2.5-Coder-32B-Instruct-GGUF:Q4_K_M \
  --gpu-layers 99 --port 8080
```

The first run will download the model (~19GB for Q4) and cache it locally.  Subsequent runs load from cache.

For a smaller model that runs on more modest hardware, Gemma 3 27B is fast (2.8s per decision) and performs well on multi-step workflows:

```bash
llama-server \
  -hf bartowski/google_gemma-3-27b-it-GGUF:Q4_K_M \
  --gpu-layers 99 --port 8080
```

### 4. Build the RAG index

This indexes the knowledge base documents into a ChromaDB vector store for retrieval:

```bash
./scripts/build_rag_index.sh
```

### 5. Run the evaluation harness

With llama-server running in one terminal, open another and run:

```bash
# Smoke test: run 1 scenario against each configured model
./scripts/smoke_test_models.sh

# Run a specific evaluation
uv run python -m src.evaluation --model "Qwen 2.5 Coder 32B" --scenarios scenarios/rule_coverage/
```

Results are written to `results/` (gitignored).

### 6. Start the web server

```bash
./scripts/start_server.sh
```

The server runs at `http://localhost:8000` and provides a web interface for submitting orders and viewing routing decisions.  It expects llama-server to be running on port 8080 (configurable in `config/server.yaml`).

### Using cloud models instead (optional)

If you don't have local GPU hardware, you can run evaluations through [OpenRouter](https://openrouter.ai/), a cloud API gateway.  Set your API key:

```bash
export OPENROUTER_API_KEY="your-key-here"
```

Models with `provider: openrouter` in `config/models.yaml` will use this key.  Note that cloud models are included for benchmarking, not as a production deployment target for labs handling PHI.

## Documentation

- **Workflow domain:** [overview](docs/workflow/workflow-overview.md), [rule catalog](docs/workflow/rule-catalog.md), [accessioning logic](docs/workflow/accessioning-logic.md), [pathologist review](docs/workflow/pathologist-review-panels.md)
- **Technical design:** [architecture](docs/technical/architecture.md), [data model](docs/technical/data-model.md), [evaluation metrics](docs/technical/evaluation-metrics.md), [technology stack](docs/technical/technology-stack.md)
- **Test design:** [scenario design](docs/scenarios/scenario-design.md), [event contracts](docs/scenarios/event-data-contracts.md)

## Models Tested

| Model | Parameters | State Accuracy | Notes |
|-------|-----------|---------------|-------|
| Qwen 2.5 Coder 32B | 32B | 99.7% | Best overall screening accuracy |
| Qwen3 32B | 32B | 99.1% | 100% rule accuracy, fastest top performer |
| Llama 3.3 70B | 70B | 97.6% | Larger but slower and less accurate |
| Gemma 3 27B | 27B | 89.2% screening, 100% accumulated state | Fastest (2.8s), best at multi-step |
| Cloud ceiling (Claude) | n/a | 95.0% | Benchmark only, not for production use |

## Running Tests

```bash
uv run pytest tests/ -v
```

The test suite includes unit tests and red team tests (adversarial inputs, type confusion, schema validation).

## License

MIT.  See [LICENSE](LICENSE).

## Contact

If you're in the lab informatics space and this work resonates, I'd love to hear from you.  See the [Substack article](https://chenryventures.substack.com/) for full context and discussion.
