# scripts/

Utility scripts for running evaluations, managing the server, and generating
data.

## Server

| Script | Purpose |
|--------|---------|
| `start_server.sh` | Start the live web UI server (validates provider, seeds DB if needed) |
| `seed_demo_data.sh` | Seed the live database with 30 demo orders |

## Evaluation Runs

| Script | Purpose |
|--------|---------|
| `run_routing_baseline.sh` | Run routing evaluation (baseline, no RAG) |
| `run_routing_rag.sh` | Run routing evaluation with RAG context |
| `run_query_baseline.sh` | Run query evaluation (baseline) |
| `run_query_tool_use.sh` | Run query evaluation with tool use |
| `run_query_rag.sh` | Run query evaluation with RAG context |
| `run_new_scenarios.sh` | Run evaluation on newly added scenarios only |
| `benchmark_models.py` | Benchmark model inference speed |
| `benchmark_quantization.py` | Compare quantization levels for local models |

## Data Generation

| Script | Purpose |
|--------|---------|
| `generate_accessioning_scenarios.py` | Generate accessioning test scenarios |
| `generate_scenario_docs.py` | Generate markdown review docs from scenario JSON |
| `build_rag_index.sh` | Build the ChromaDB vector index from `knowledge_base/` |

## Utilities

| Script | Purpose |
|--------|---------|
| `inspect_scenario.py` | Pretty-print a scenario JSON file |
| `regenerate_summary.py` | Regenerate evaluation summary from raw results |
| `generate_rag_comparison.sh` | Generate comparison report between RAG and baseline |
| `test_connectors.py` | Test model provider connectivity |
| `chat_scenario.py` | Interactive chat with a scenario for debugging |
