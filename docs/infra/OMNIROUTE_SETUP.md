# OmniRoute — Model Infrastructure Setup & Handoff

> **Status:** work in progress (Phase 4b of a phased rollout).
> **Purpose:** give Jarvis a provider-agnostic model gateway (routing + fallback across
> multiple LLM providers) with a **$0 cost target**, without coupling Jarvis to any provider.
>
> This document is the source of truth for reproducing the OmniRoute infrastructure on a new
> machine. **Nothing here contains secrets** (no API keys, no passwords). The actual secrets
> live only in machine-local files that are **not** in this repo (see "What does NOT transfer").

---

## 1. Target architecture

```
        JARVIS  (domain / cognition — never knows the provider)
              │
              ▼
        LanguageModel  (existing Protocol seam — unchanged)
              │
              ▼
        OpenAiCompatibleModel  (existing adapter — unchanged)
              │   base_url = http://127.0.0.1:20128/v1
              ▼
        ┌──────────────── OMNIROUTE ────────────────┐
        │  19 routing strategies + 3-layer fallback  │
        └──────┬───────────┬───────────┬────────────┘
               ▼           ▼           ▼
            Groq        Gemini      NVIDIA ...   (whatever is connected)

        [separate line — NOT through OmniRoute]
        Jarvis embeddings (JARVIS_EMBED_*) ──► local Ollama :11434 (bge-m3)
```

Jarvis already has the full provider-agnostic seam (`LanguageModel`, `OpenAiCompatibleModel`,
the provider registry, `ProviderSettings`, `JARVIS_LLM_*` env config). **OmniRoute integration is
config, not code** — Jarvis points at OmniRoute's OpenAI-compatible endpoint as "just another
`base_url`". No refactor of `domain/`, `executive/`, or the `LanguageModel` protocol is needed.

**Layer separation (no overlap):** Jarvis *selects* a model endpoint (config); OmniRoute *decides
which real provider serves it* and does runtime fallback on rate-limit/error — something Jarvis's
own registry does not do.

---

## 2. Current state (as of this commit)

| Component | State |
|---|---|
| OmniRoute | Installed globally via npm — **v3.8.49** |
| Native deps | `better-sqlite3` repaired via `omniroute repair`; keytar/onnxruntime prebuilt |
| Server | Runs on **port 20128**, OpenAI-compatible `GET /v1/models` → HTTP 200 (115 routing models) |
| Data dir | `~/.omniroute/` (storage.sqlite + its own `.env` with an auto-generated encryption key) |
| Providers connected | Gemini (`gemini-web`) + Grok (`grok-cli`), both active — connected via dashboard |
| Jarvis integration | **Verified end-to-end** (Phase 7): `Jarvis → LanguageModel → OmniRoute → Grok → reply`, real non-cached round-trip returns content. Config-only; one 1-line adapter hardening (see §8). |

---

## 3. What transfers vs. what does NOT

**Does NOT transfer via git (machine-local — must be redone on the new PC):**
- The global npm package (`npm install -g omniroute`).
- `~/.omniroute/` — OmniRoute config, provider connections, keys, SQLite DB, encryption key.
- Any `JARVIS_LLM_*` values written to the repo-local `.env` (git-ignored by design).

**Transfers via git:**
- This document.
- (Later, Phase 7) The Jarvis composition-root/config wiring, if any code is added — currently none.

> Provider connections and API keys are stored encrypted in `~/.omniroute/storage.sqlite`. They are
> **not portable** as-is. On the new PC you re-run the setup and re-connect providers.

---

## 4. Reproduce on a new PC

Prerequisites: Node.js (tested on v26) and npm. (Docker NOT required.)

```bash
# 1. Install OmniRoute globally
npm install -g omniroute

# 2. Repair native deps (npm often skips install scripts; this fixes better-sqlite3)
omniroute repair

# 3. Verify the install
omniroute doctor

# 4. Start the gateway (background). Run from your home dir so it uses ~/.omniroute,
#    not the Jarvis repo's .env.
omniroute serve      # listens on http://127.0.0.1:20128

# 5. Confirm the OpenAI-compatible endpoint (use 127.0.0.1, NOT localhost — see Gotchas)
curl http://127.0.0.1:20128/v1/models
```

Then connect a provider via the **dashboard** (see §6) and change the default password (§7).

---

## 5. Server control

| Action | Command |
|---|---|
| Start | `omniroute serve` |
| Stop | `omniroute stop` |
| Restart | `omniroute restart` |
| Status | `omniroute status` |
| Health | `omniroute health` |
| Diagnose install | `omniroute doctor` |
| Repair native deps | `omniroute repair` |
| Dashboard (browser) | `omniroute dashboard` → http://127.0.0.1:20128 |

---

## 6. Connecting providers (must be done in the dashboard)

The **CLI cannot write provider config** against the running server (management calls return
HTTP 404 unless done through the authenticated dashboard session). So provider connection is a
**dashboard** task:

1. `omniroute dashboard` → log in (default user `admin`, default password `CHANGEME` — change it, §7).
2. **Providers → Add**.
3. This build's api-key catalog has **6 providers**: `openai`, `anthropic`, `google` (Gemini),
   `openrouter`, `groq`, `mistral`. (**Ollama is not in this build's api-key catalog.**)
4. **$0 recommendation:** connect **Groq** (free tier, no credit card) or **Google AI / Gemini**
   (free tier). Create the key on the provider's site, paste it into the dashboard.
   - Groq keys: https://console.groq.com → API Keys
   - Gemini keys: https://aistudio.google.com/apikey
5. **API key field must be non-empty** — OmniRoute rejects an empty provider key
   (`Provider API key is required`).

> If a future build exposes an "Ollama" or "Custom / OpenAI-compatible" provider, connect local
> Ollama with base URL `http://127.0.0.1:11434/v1` and any dummy key. Not available in v3.8.49's
> api-key catalog.

---

## 7. Security notes

- **Change the default dashboard password.** On first run OmniRoute sets the management password to
  the well-known default `CHANGEME`. It is localhost-only, but change it in the dashboard **Settings**.
- **No secrets in git.** The repo `.env` is git-ignored. `~/.omniroute/.env` (with its encryption key)
  is outside the repo. Never commit API keys or passwords.
- Jarvis's own secret rule stands: the LLM API key lives only in `JARVIS_LLM_*` env / repo `.env`,
  never in source.

---

## 8. Gotchas / findings (save yourself the debugging)

- **Use `127.0.0.1`, not `localhost`.** PowerShell `Invoke-WebRequest` hangs on
  `localhost:20128` (IPv6/proxy quirk); `curl.exe` to `127.0.0.1:20128` works. Point Jarvis and
  Claude Code at `http://127.0.0.1:20128/v1`.
- **`omniroute repair` is usually required** after `npm install -g` because npm skips install
  scripts (`better-sqlite3` native binary).
- **`--api-key` flag collision:** `omniroute setup --add-provider --api-key ...` fails
  (`Provider API key is required`) because a **global** `--api-key` option (OmniRoute *server* key)
  shadows the subcommand flag. Connect providers via the dashboard instead.
- **Catalog is 6 providers, not "350".** The "350 providers" figure includes OAuth/free providers
  not present in this build's api-key catalog.
- **Run `serve` from your home dir**, otherwise OmniRoute also loads the Jarvis repo `.env` (it
  ignores unknown vars, but keep the secret files separate).
- **Adapter must send `stream: false` explicitly.** OmniRoute's Grok route returns an **SSE body**
  when the `stream` field is absent, which the non-streaming `complete()` path cannot parse
  (`json.loads` fails → empty reply). Fixed in `src/jarvis/infrastructure/openai_compatible_model.py`
  by always sending `stream` (true/false) instead of only when true. Universally correct; harmless
  for providers that already default to non-stream (Groq direct, OpenAI).

---

## 9. Remaining plan

- **Phase 4b (done):** Gemini + Grok connected via dashboard; real chat at $0 cost verified.
- **Phase 7 (done):** Jarvis routes through OmniRoute (config-only + the §8 `stream:false` fix),
  verified with a fresh non-cached round-trip. Runtime config used:
  `JARVIS_LLM_PROVIDER=openai-compatible`, `JARVIS_LLM_BASE_URL=http://127.0.0.1:20128/v1`,
  `JARVIS_LLM_MODEL=auto` (embeddings still direct to Ollama).
- **Phase 6 (done):** Claude Code routes through OmniRoute via a **reversible launcher**
  (`docs/infra/claude-omniroute.ps1`) — env-only, global config/OAuth untouched. Verified with a
  non-interactive one-shot returning content through OmniRoute → Grok. See §10.
- **Phase 4c (done):** NVIDIA added; connected lineup (all free): cerebras, deepseek, grok,
  gemini, github-models, openai, nvidia — with 3-layer fallback across them.
- **Phase 5 (done):** routing uses OmniRoute's built-in `auto/*` combos (no custom config needed;
  custom combos require dashboard auth). See §11.
- **Phase 7:** point Jarvis at OmniRoute — **config only**, no refactor:
  ```
  JARVIS_LLM_PROVIDER = openai-compatible
  JARVIS_LLM_BASE_URL = http://127.0.0.1:20128/v1
  JARVIS_LLM_MODEL    = auto
  JARVIS_LLM_API_KEY  = <OmniRoute server key, if required; else empty>
  ```
  Embeddings stay direct to local Ollama (`JARVIS_EMBED_*` → `http://127.0.0.1:11434/v1`, `bge-m3`).
  Optionally register a named endpoint: `register_endpoint("omniroute", "http://127.0.0.1:20128/v1")`.
- **Phase 9:** real end-to-end test `Jarvis → LanguageModel → OmniRoute → provider → response`.
- **DeerFlow:** out of scope for now. Would fit later as a multi-step agent/research layer *above*
  Jarvis, not inside the model infrastructure.

---

---

## 10. Claude Code through OmniRoute (Phase 6)

Claude Code (the CLI engine, not the desktop UI) reads `ANTHROPIC_BASE_URL` + an auth token from
the environment, and OmniRoute exposes an **Anthropic-compatible** surface at `/v1/messages` (it
translates to whatever provider is connected). So Claude Code can be pointed at OmniRoute **without
touching global config or the OAuth login**.

**Reversible launcher:** `docs/infra/claude-omniroute.ps1` (also kept at
`~/.claude/omniroute/claude-omniroute.ps1`). It sets env vars **only for the process it starts**:

```powershell
powershell -ExecutionPolicy Bypass -File docs/infra/claude-omniroute.ps1
```

What it sets (per-process, not persisted):
- `ANTHROPIC_BASE_URL = http://127.0.0.1:20128`
- `ANTHROPIC_AUTH_TOKEN = sk-omniroute-local` (dummy; OmniRoute accepts localhost without a real key)
- `ANTHROPIC_MODEL = auto`, `ANTHROPIC_SMALL_FAST_MODEL = auto` (bare `claude-*` ids are "ambiguous"
  to OmniRoute; `auto` lets it route + fall back across connected providers)
- `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT = 1` (silences the cosmetic "auto not
  recognized" context-window warning)

**Safety:** the current `settings.json` was backed up to `~/.claude/settings.json.bak-phase6`
before any Phase-6 work. The launcher modifies **no** existing file. To stop routing, close that
session and use Claude Code normally.

**Findings:**
- Claude Code binary lives at `~/AppData/Roaming/Claude/claude-code/<version>/claude.exe` (the
  launcher discovers the newest version automatically).
- A leftover `[claude-code:unrecognized_model] {"model":"auto"}` stderr line is harmless; to remove
  it fully, map `auto` in Claude Code's `modelOverrides` setting.

---

---

## 11. Routing strategy (Phase 5)

OmniRoute routing is expressed as **combos** (a strategy + a provider set). It always runs a
3-layer fallback (circuit breaker → cooldown → model lockout) across connected providers.

**What we use — built-in `auto/*` combos** (no configuration needed, verified routing at $0):

| Request model id | Meaning | Observed route |
|---|---|---|
| `auto` | balanced 15-factor scorer (default) | picks a healthy provider |
| `auto/best-coding` | coding-optimized | e.g. openai/gpt-4o |
| `auto/best-reasoning` | reasoning-optimized | reasoning-tier model |
| `auto/best-fast` | cheap/fast | e.g. openai/gpt-4o-mini |

These already optimize cost + quality + latency + availability with fallback, which is exactly the
conservative goal. Consumers select by model id:
- **Claude Code launcher** (`claude-omniroute.ps1`): main = `auto/best-coding`, small/fast = `auto/best-fast`.
- **Jarvis**: `JARVIS_LLM_MODEL=auto` (balanced) — or `auto/best-reasoning` for heavier cognition.

**Custom combos (optional, dashboard-only).** Creating an explicit combo — e.g. `cost-optimized`
(cheapest-first) or `priority` with a fixed free-first order — is a **dashboard** action; the CLI
`combo create` returns HTTP 401 (management writes need the authenticated dashboard session). Do it
in the dashboard's Routing/Combos section only if you need ordering beyond what `auto/*` gives.

**Preview without spending tokens:** `omniroute simulate "<prompt>" --combo <name> --explain`
(dry-run; shows the selected provider + fallback tree). Requires a configured combo.

---

*Kept secret-free on purpose. If you add operational detail, keep keys and passwords out of this file.*
