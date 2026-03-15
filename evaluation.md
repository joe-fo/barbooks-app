# Pydantic AI Evaluation

**Question:** Does `pydantic-ai` add value beyond what we already get from plain Pydantic + httpx + Ollama?

**Verdict: Skip for now — revisit if we add tool-calling or need structured LLM observability.**

---

## Current Stack Summary

| Concern | Current approach |
|---|---|
| Input validation | Pydantic `Field(max_length=150)` on `ChatRequest` |
| LLM abstraction | Custom `LLMPort` / `OllamaAdapter` (hexagonal pattern) |
| Ollama transport | `httpx` → `/api/chat` with `num_predict: 50`, `temperature: 0.0` |
| Output safety | Mechanical token cap (`num_predict: 50`) + strict system prompt |
| Observability | Python `logging` (request received, LLM called, errors) |
| Agent pattern | Single-turn Q&A; no tool-calling, no multi-turn |

---

## Areas Evaluated

### 1. Monitoring / Observability

**What pydantic-ai offers:** First-class [Logfire](https://logfire.pydantic.dev/) integration. One `logfire.configure()` call instruments every `Agent.run()` invocation with structured spans: model name, message content, token counts (prompt + completion), latency, and retry count. Without Logfire, `pydantic-ai` also emits structured events to Python's standard logging.

**What we currently have:** Plain `logger.info` / `logger.error` calls. We log that an LLM call happened and surface errors, but we capture no token counts, no latency breakdown, and no prompt/response content in a queryable form.

**Assessment:** Logfire would be genuinely useful for debugging bad answers or unexpected prompt injection bypasses — it makes the LLM "black box" transparent. However, it is an external SaaS dependency. For a PoC running locally, the value doesn't justify the setup overhead. If this graduates from PoC to production and answer quality becomes a pain point, Logfire is the right tool to add then.

**Verdict:** Pass for now. Revisit at production.

---

### 2. Safety / Guardrails

**What pydantic-ai offers:** `result_validators` — async or sync functions that run after every LLM response. They receive the raw output and can raise `ModelRetry(message)` to re-prompt the model up to a configurable retry limit. Also supports structured (Pydantic model) result types, where the library forces the model to emit parseable JSON matching a schema.

**What we currently have:**
- Input: Pydantic `max_length=150` blocks oversized prompts before any LLM call.
- Output: `num_predict: 50` is a *mechanical* token cap enforced by Ollama itself — the model physically cannot produce more tokens regardless of what the system prompt says. Combined with `temperature: 0.0`, responses are deterministic and short.

**Assessment:** Our current approach is actually harder to accidentally bypass than validator hooks. `num_predict` is enforced at the inference engine level, not in application code where a bug could skip it. `result_validators` add power (semantic checks, retry loops) but also complexity and non-determinism (retries mean variable latency, variable cost). For our use case — a tightly constrained trivia bot with a strict system prompt — the mechanical approach is more reliable.

If we wanted to enforce that answers always start with "Yes", "No", or "Correct!", a result validator could do that cleanly. But the system prompt + short token budget already handles this well in practice.

**Verdict:** Pass. Our mechanical guardrails are simpler and more reliable for this workload.

---

### 3. Agent Orchestration

**What pydantic-ai offers:** An `Agent` class that manages system prompt composition, tool (function) registration, multi-turn conversation history, result validation, and retry loops. Tools are Python functions the model can call during a response.

**What we currently have:** Pure single-turn Q&A. Each request is independent: build system prompt, call Ollama, return answer. No tool-calling, no history.

**Assessment:** pydantic-ai's agent model would fit naturally if we ever added tools — for example, a "lookup stats" tool that queries the spreadsheet store, or a "check answer" tool for the deterministic layer. Right now we have zero tools, so the agent orchestration machinery buys us nothing and adds indirection.

If we move to multi-turn (e.g., a user asks a follow-up question in the same session), pydantic-ai's `agent.run(message_history=...)` pattern is cleaner than maintaining message lists manually.

**Verdict:** Pass for now. If tool-calling or multi-turn lands on the roadmap, adopt then.

---

### 4. Ollama Compatibility

**What pydantic-ai offers:** An `OllamaModel` backend (added in `pydantic-ai >= 0.0.14`) that wraps Ollama's OpenAI-compatible endpoint (`/v1/chat/completions`). Usage:

```python
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel

agent = Agent(OllamaModel("llama3.2"), system_prompt="...")
result = await agent.run(user_message)
```

This would replace our entire `OllamaAdapter` class (~40 lines of httpx boilerplate).

**What we currently have:** A custom `OllamaAdapter` using `httpx` directly against `/api/chat`. Clean code, but ~40 lines that pydantic-ai would handle for free. Our hexagonal `LLMPort` ABC is a better long-term abstraction (swap backends by swapping the adapter), but pydantic-ai's model system provides the same swap point.

**Assessment:** This is the strongest case for pydantic-ai. The `OllamaModel` backend is well-tested and handles retry logic, timeout config, and response parsing. However, our `OllamaAdapter` is already thin and correct. Switching would save code but add a dependency and lose the explicit `LLMPort` contract that makes our hexagonal architecture self-documenting.

One practical note: `pydantic-ai`'s Ollama backend uses the `/v1/chat/completions` (OpenAI-compat) endpoint rather than `/api/chat`. Both work with Ollama, but `/api/chat` is Ollama-native and supports Ollama-specific parameters (e.g., `num_predict`) more directly. Switching would require verifying that token limits still apply correctly.

**Verdict:** Marginal benefit. Not worth the churn unless we're also adopting pydantic-ai for other reasons.

---

### 5. Logfire Integration

**What pydantic-ai offers:** `logfire.instrument_pydantic_ai()` enables full distributed tracing for every model call — spans appear in the Logfire dashboard with message content, token usage, and timing. This is opt-in and requires a Logfire account (free tier available).

**Assessment:** Powerful for production debugging. For a local PoC where all developers can `docker logs` directly, it's premature. Worth bookmarking for when the app handles real user traffic and we need to diagnose why specific queries get wrong answers.

**Verdict:** Pass for now.

---

## Summary Table

| Feature | pydantic-ai offers | Current approach | Adopt? |
|---|---|---|---|
| Structured LLM telemetry | Logfire spans, token counts | Basic Python logging | No — PoC scope |
| Output validation | `result_validators`, retry loops | `num_predict: 50` mechanical cap | No — mechanical is simpler |
| Input validation | Pydantic result types | `Field(max_length=150)` | Already covered |
| Agent / tool-calling | `Agent`, tools registry | N/A (single-turn) | No — no tools yet |
| Ollama transport | `OllamaModel` backend | Custom `httpx` adapter | No — marginal benefit |
| Logfire observability | First-class integration | N/A | No — PoC scope |

---

## Recommendation

**Skip pydantic-ai for the current PoC.**

The existing stack covers all active requirements cleanly:
- Pydantic validates inputs.
- The `LLMPort` / `OllamaAdapter` pattern provides backend decoupling.
- Mechanical token limits and a strict system prompt are the right safety primitives for a tightly scoped trivia bot.

**Revisit pydantic-ai when any of the following become true:**

1. **We add tool-calling** (e.g., structured lookups during a response) — `Agent` + tools registry is the right pattern.
2. **Multi-turn conversation** — pydantic-ai's message history management is cleaner than rolling it manually.
3. **Answer quality debugging becomes painful** — Logfire observability is the right solution; add it then.
4. **We need structured (JSON) output from the LLM** — pydantic-ai's typed result models enforce this robustly.

None of these apply to the current single-turn trivia Q&A PoC.
