# Deployment Security Assessment: Dockerfile + Cloudflare Tunnel

**Date:** 2026-03-16
**Scope:** FastAPI + Streamlit in Docker, exposed via Cloudflare Tunnel
**Status:** Pre-launch PoC — not yet serving real users

---

## 1. Dockerfile Hardening

### Current State

```dockerfile
FROM python:3.11-slim          # floating tag — changes silently
RUN apt-get install -y curl    # curl left in production image
RUN poetry install --no-root   # dev deps may be included
EXPOSE 8000 8501               # both ports declared
# No USER directive → runs as root
```

### Findings

**CRITICAL: Container runs as root.**
No `USER` directive is present. If the application or any dependency has an RCE vulnerability, the attacker has root inside the container. Adding a non-root user is a single-line fix with broad impact.

**HIGH: Base image uses floating `latest`-style tag (`python:3.11-slim`).**
Without pinning to a SHA digest, the image can silently change between builds, introducing regressions or supply-chain risk. The fix is one line: append `@sha256:<digest>` to the `FROM` statement.

**MEDIUM: `curl` remains in the production image.**
`curl` is installed to bootstrap Poetry, then stays in the final layer. This expands the attack surface (curl + libssl = many CVEs historically). A multi-stage build eliminates this: build stage installs Poetry and dependencies; runtime stage copies only the virtualenv and application code.

**MEDIUM: Dev dependencies likely included.**
`poetry install --no-root` installs all dependency groups unless `--only=main` (or `--without=dev`) is specified. Dev tooling (pytest, mypy, etc.) adds unnecessary packages to the production image. Confirm `pyproject.toml` groups and add `--only=main` if dev extras exist.

**LOW: No `.dockerignore`.**
Files like `eval_models.py`, `books/`, `tests/`, and any local `.env` files could be inadvertently copied into the image via a broad `COPY . .` if that pattern is ever introduced.

### Recommended Dockerfile skeleton

```dockerfile
# --- build stage ---
FROM python:3.11-slim@sha256:<pinned-digest> AS build

ENV POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only=main --no-root

# --- runtime stage ---
FROM python:3.11-slim@sha256:<pinned-digest>

RUN useradd --system --uid 1001 --no-create-home appuser

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app/ ./app/
COPY ingest.py ./

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8000

USER appuser
EXPOSE 8000 8501
```

### Secrets handling

No secrets are currently baked into the image — `OLLAMA_URL` and `API_URL` are passed via `docker-compose.yml` environment blocks. This is correct. Confirm `ADMIN_PASSWORD` (see §3) follows the same pattern when set.

---

## 2. Cloudflare Tunnel Exposure

### What is reachable

The Caddy reverse proxy routes traffic as follows:

| Path | Target | Notes |
|------|--------|-------|
| `/api/*` | FastAPI (port 8000) | All API endpoints including `/api/v1/admin/*` |
| `/*` | Streamlit (port 8501) | Full UI |

Both services are co-located behind a single domain. Cloudflare Tunnel connects to Caddy on port 80.

**Ollama is NOT directly exposed** — it runs on the host and is accessed via `host.docker.internal:11434`. However, if the host firewall is not configured to block external access on port 11434, Ollama could be reached from outside the container (see §3).

### Single tunnel vs. separate subdomains

For a PoC, co-locating UI and API under one subdomain (e.g. `barbooks.example.com`) is acceptable. The Caddyfile path-based routing handles separation cleanly.

For a hardened deployment, separating them provides defence-in-depth:
- `barbooks.example.com` → Streamlit UI only
- `barbooks-api.example.com` → FastAPI, protected by Cloudflare Access service token (machine-to-machine only, not user-facing)

This prevents direct browser access to API endpoints and reduces the prompt-injection surface.

### Cloudflare Access (authentication gate)

**RECOMMENDATION: Enable Cloudflare Access before any real users are invited**, even for a PoC.

Without it, the full application — including the admin panel at `/admin` — is publicly accessible to anyone who discovers the tunnel URL. Cloudflare Access supports:
- **One-time PIN (email OTP):** Zero friction for invited testers; no Google account required.
- **Google SSO:** Good for teams; free on the zero-trust tier.

Suggested configuration: apply an Access policy to the entire tunnel (`*`) requiring email OTP. This adds one click for legitimate users and completely blocks anonymous access.

### Rate limiting

The `/api/v1/chat` endpoint proxies to a local LLM. Each inference takes ~1–5 seconds of CPU. Without rate limiting, a single automated client can saturate the host.

**Recommended Cloudflare rate limit rules (WAF → Rate Limiting):**

| Rule | Threshold | Window | Action |
|------|-----------|--------|--------|
| Chat endpoint | 20 req | 60 s | Block 10 min |
| Admin endpoints | 5 req | 60 s | Block 1 h |
| Global per IP | 100 req | 60 s | Challenge |

These thresholds are conservative for a trivia game — legitimate users rarely send more than a few questions per minute.

---

## 3. Application-Level Risks

### 3a. Prompt injection on `/api/v1/chat`

**Risk: MEDIUM (constrained by local model scope).**

The `/api/v1/chat` endpoint accepts `user_message` as free text and passes it directly to the LLM system prompt. There are currently no input length limits, no sanitization, and no injection filters.

The system prompt (`llm_service.py:_build_system_prompt`) does include grounding instructions:
> "Answer using ONLY the ranked list below. NEVER invent or assume facts not in the list."

This reduces the risk substantially, but is not a security boundary — it is a quality instruction. A motivated attacker can still inject instructions to make phi3:mini output arbitrary text, leak the system prompt, or cause unexpected behavior.

**Mitigations to apply before live traffic:**
1. **Input length cap:** Enforce `max_length=500` on `user_message` at the Pydantic model level. Trivia questions are never longer than a sentence.
2. **Request validation:** Reject inputs containing obvious injection markers (e.g. `\nSystem:`, `\nAssistant:`, `<|im_start|>`) at the schema layer.
3. **Output length already capped:** `num_predict: 150` is in place — good. Keep it.

The local-model architecture limits the blast radius: phi3:mini has no internet access, no tool use, and no persistent memory. Prompt injection cannot exfiltrate external secrets or perform external actions.

### 3b. Answer reveal (`REVEAL` intent)

**Decision (2026-03-16): REVEAL is unrestricted by default, gated via env var.**

The `BARBOOKS_ALLOW_REVEAL` environment variable (default: `true`) controls whether
users can request the full answer key via "show me the answers" / REVEAL intent.

- **`BARBOOKS_ALLOW_REVEAL=true` (default):** Full answer key returned. Appropriate for
  self-serve PoC testing where users interact individually and self-spoiling is acceptable.
- **`BARBOOKS_ALLOW_REVEAL=false`:** REVEAL returns `"Answers are only revealed by the
  host. Keep guessing!"` — no answer key is exposed. Use this for hosted trivia games
  where a human host controls when answers are revealed.

The gate is implemented in `main.py` in the REVEAL intent branch. The flag defaults to
`true` so no configuration change is needed for the current PoC. Before a live hosted
game, set `BARBOOKS_ALLOW_REVEAL=false` in `docker-compose.yml`.

See also: `question_patterns.py` — REVEAL is classified as a dedicated intent (not UNKNOWN),
which is what enables the gate to fire before the LLM is called.

### 3c. Admin routes — unauthenticated by default

**CRITICAL: The admin form at `/admin` is fully unprotected.**

The `admin_form()` route at `GET /admin` has no password check whatsoever — it serves the HTML form to anyone. The downstream routes (`/api/v1/admin/preview` and `/api/v1/admin/add-page`) check `ADMIN_PASSWORD` only if the variable is set:

```python
def _check_password(pw: str) -> None:
    expected = ADMIN_PASSWORD          # os.getenv("ADMIN_PASSWORD", "")
    if expected and pw != expected:    # ← empty string is falsy → bypass
        raise HTTPException(...)
```

If `ADMIN_PASSWORD` is not set in the environment (its default is `""`), authentication is completely skipped. Any user can call `POST /api/v1/admin/add-page` with an arbitrary URL and write a new row to the spreadsheet.

**Before going live:**
1. **Set `ADMIN_PASSWORD` in `docker-compose.yml`** via an environment variable from the host (never hardcode it).
2. **Add a password check to `GET /admin`** — currently it serves the form unconditionally.
3. **Consider blocking `/admin*` paths in Cloudflare Access** with a stricter policy than the general app, or use the Caddyfile to restrict `/admin` to a specific IP range.

### 3d. Ollama port exposure

Ollama is not inside the Docker network — it runs on the host machine and is accessed via `host.docker.internal:11434`. The `api` and `ui` containers use `extra_hosts: host.docker.internal:host-gateway` to resolve this.

**Verify that port 11434 is NOT accessible from outside the host:**
```bash
# On the deployment host:
ss -tlnp | grep 11434
# Should show: 127.0.0.1:11434 (loopback only), NOT 0.0.0.0:11434
```

By default, Ollama binds to `127.0.0.1`. If it has been configured with `OLLAMA_HOST=0.0.0.0` (a common debugging change), it will be accessible from the internet if the host has a public IP. This would expose the raw Ollama API (no auth, model pull/run/generate) to the world.

**Mitigation:** Confirm Ollama binds to loopback only. Add a firewall rule to block TCP 11434 from any external interface as a belt-and-suspenders measure.

### 3e. No sensitive admin endpoints on FastAPI besides `/admin`

A review of `main.py` and `admin.py` confirms there are no other admin-style endpoints. The `page_info` endpoint at `GET /api/v1/page/{book_id}/{page_id}` is read-only and serves display metadata only. No delete, update, or configuration endpoints exist outside of admin.

---

## 4. Pre-Launch Checklist

### CRITICAL (must fix before accepting any real user traffic)

- [ ] **Add non-root USER to Dockerfile** — run the app as uid 1001, not root
- [ ] **Set `ADMIN_PASSWORD` environment variable** — and apply to the `GET /admin` form route, not just the POST endpoints
- [ ] **Enable Cloudflare Access** on the tunnel (email OTP minimum) — prevents public access to the admin form and raw API
- [ ] **Verify Ollama binds to 127.0.0.1 only** — confirm with `ss -tlnp | grep 11434` on the deployment host

### HIGH (fix before inviting external testers)

- [ ] **Add input length cap to `user_message`** — enforce `max_length=500` in the Pydantic model
- [ ] **Pin base image to a SHA digest** — prevents silent image changes between builds
- [ ] **Remove `curl` from production image** — use multi-stage build
- [ ] **Add Cloudflare rate limits** — 20 req/min per IP on `/api/v1/chat`, 5 req/min on `/admin` endpoints
- [ ] **Add `--only=main` to `poetry install`** — exclude dev dependencies from production image

### MEDIUM (address before public launch)

- [x] **Document REVEAL intent policy** — `BARBOOKS_ALLOW_REVEAL` env var added; defaults to `true` for PoC, set to `false` for hosted games (see §3b)
- [ ] **Restrict `/admin` to internal/allowlisted IPs in Caddyfile or Cloudflare Access** — even with a password, the admin form should not be browsable from public internet
- [ ] **Add `.dockerignore`** — exclude `tests/`, `eval_models.py`, `*.md`, `.git`, `books/` from build context
- [ ] **Consider separate API subdomain** — prevents direct browser access to FastAPI; reduces prompt-injection surface

### LOW (good hygiene, not blocking)

- [ ] **Add basic prompt injection markers filter** — reject inputs containing `\nSystem:`, `\nAssistant:` etc.
- [ ] **Log admin actions with caller IP** — `admin.py` logs the book/page written but not the source IP; add `request: Request` param and log `request.client.host`
- [ ] **Confirm no dev port exposure** — ensure ports 8000 and 8501 are NOT directly bound to `0.0.0.0` on the host (they should only be reachable via the Caddy container on port 80)
