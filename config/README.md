# config/

YAML configuration files for the evaluation harness and live server.

| File | Purpose |
|------|---------|
| `models.yaml` | Model definitions for evaluation: provider, model ID, tier, runs, and inference parameters |
| `settings.yaml` | Evaluation parameters (runs per model, timeout) and RAG pipeline settings (top_k, similarity threshold) |
| `server.yaml` | Live server configuration: model provider, database path, host, and port |

## Model Tiers

Tiers in `models.yaml` reflect deployable hardware targets:

- **Tier 1** — 16 GB VRAM (e.g., RTX 4060 Ti)
- **Tier 2** — 24 GB VRAM (e.g., RTX 4090)
- **Tier 3** — MoE models, fast inference on 24 GB
- **Ceiling** — Cloud models used as accuracy benchmarks (1 run each)
