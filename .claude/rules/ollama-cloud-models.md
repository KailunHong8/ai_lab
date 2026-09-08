# Ollama Cloud — Free Tier Models

**Trigger:** Model selection, API configuration, frontend UI updates for Agent page, OLLAMA_CLOUD_MODELS constant

## Free Tier (No Subscription Required)

The free tier of Ollama Cloud (https://ollama.com, API key in `OLLAMA_API_KEY`) supports these models without a paid subscription:

- `gpt-oss:120b` — OpenAI's open-source GPT model, 120B params
- `gemma4:31b` — Google Gemma 4, 31B params

## Requires Paid Subscription

**Do not add to UI:**
- `deepseek-v4-flash`
- `kimi-k2.6`
- `minimax-m2` / `minimax-m3`
- `qwen3.5:397b`
- `cogito-2.1:671b`
- `deepseek-v3.1:671b-cloud`
- `glm-5.2:cloud`

## Frontend Integration

The frontend `OLLAMA_CLOUD_MODELS` constant in `frontend/src/pages/Agent.tsx` should only contain free-tier models.
