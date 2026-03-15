# Barbooks AI

An AI agent backend for validating trivia answers in physical books. Users scan QR codes on book pages to reach a chat interface where they can ask the agent to verify their answers.

## Quick Start

**Prerequisites:** Python 3.10+, [Ollama](https://ollama.com) running locally, [Task](https://taskfile.dev)

```bash
# Install dependencies
poetry install

# Run API + UI together
task dev

# Or run separately
task api   # FastAPI backend on :8000
task ui    # Streamlit frontend
```

## Further Reading

- [Product Requirements](product-requirements.md) — what the app does and why
- [Architecture](architecture.md) — technical design and implementation details
