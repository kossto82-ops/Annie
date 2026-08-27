# Graphify in Jarvis

Graphify is an **external, dev-time code-navigation tool**. It turns this
repository into a local, queryable code graph so that Claude Code (and other
assistants) can *locate* the relevant parts of Jarvis before reading files —
instead of loading large amounts of source into context.

It is **not** part of Jarvis's runtime, and it is **not** Jarvis's memory.
See [What Graphify is NOT](#what-graphify-is-not).

---

## 1. What it is

- Local, deterministic **AST parser** (tree-sitter) over the repo. No embeddings,
  no vector store, no database, no network for code extraction.
- Produces a code graph (`graphify-out/graph.json`) of nodes (classes, functions,
  files, tests) and typed edges (`calls`, `imports`, `uses`, `inherits`, …).
- Every edge is tagged `EXTRACTED` (explicit in source) or `INFERRED` (derived) —
  the same evidence/provenance discipline Jarvis values.
- Exposes the graph to Claude Code as an **MCP server** with small, targeted
  query tools.

Apache-2.0. Package: `graphifyy` (the `graphify` name is being reclaimed upstream;
the CLI command is `graphify`).

## 2. Install (already done on this machine)

```bash
pip install --user "graphifyy[mcp]"
```

- Installed at user level on purpose — it is a **tool**, never a Jarvis
  dependency. It is deliberately absent from `pyproject.toml`.
- Requires the `[mcp]` extra for the MCP server (pulls in the `mcp` SDK).
- CLI/scripts land in `…\AppData\Roaming\Python\Python314\Scripts` (Windows);
  the MCP server is invoked as `python -m graphify.serve`, so PATH is irrelevant.

## 3. Build / refresh the graph (deterministic, no LLM)

```bash
graphify update .
```

- "no LLM needed" — pure AST re-extraction. ~8 s for this repo
  (≈1900 nodes, ≈4400 edges). Fully offline.
- **Do not** use `graphify extract` for the default flow — that path adds
  *semantic* (LLM) extraction and needs an API key. We intentionally stay on the
  deterministic `update` path (see [Decisions](#7-decisions)).
- Optionally keep it fresh automatically: `graphify watch .` (rebuilds on code
  changes). Git-hook auto-rebuild (`graphify hook install`) is available but is
  **opt-in** and left uninstalled by default.

Artifacts land in `graphify-out/` and are **git-ignored** and **`.claudeignore`d**.

## 4. Query from the CLI

```bash
graphify god-nodes --top 10            # architectural hubs
graphify explain "ExecutiveController" # a node + its neighbours (file:line)
graphify path "Jarvis" "Evidence"      # shortest path between two concepts
graphify affected "Belief" --depth 1   # what depends on / is impacted by X
graphify query "what connects perception to belief" --budget 800
```

Typical footprints measured on this repo: `god-nodes` ~0.25 KB, `explain`
~2 KB, `path` ~0.2 KB. `query` (broad BFS) and `affected` on hub nodes can reach
several KB — see [Token impact](#6-token-impact).

## 5. Use from Claude Code (MCP)

Wired via project-scoped [`.mcp.json`](../.mcp.json):

```json
{ "mcpServers": { "graphify": {
  "command": "python",
  "args": ["-m", "graphify.serve", "graphify-out/graph.json"]
} } }
```

Claude Code picks this up on start (approve the server once when prompted).
Ten MCP tools are exposed; the seven that matter for navigation:

| Tool | Use for |
|------|---------|
| `god_nodes` | Find the core abstractions / hubs first |
| `get_node` | Full details for one symbol (neighbours, file:line) |
| `get_neighbors` | Direct dependencies of one symbol |
| `shortest_path` | How two concepts connect |
| `query_graph` | Broad "what connects A to B" BFS (has a token budget) |
| `get_community` | Everything in one cluster/module |
| `graph_stats` | Graph summary |

(`list_prs` / `get_pr_impact` / `triage_prs` are GitHub-PR helpers; not needed
for code navigation and require a GitHub token.)

### When Claude should query Graphify vs. read files

- **Query Graphify first** to *locate* and *scope*: "what depends on X?",
  "where is Y used?", "what connects A to B?", "which files are about memory?".
  The answer is a small set of `file:line` pointers.
- **Then read the specific files** the query pointed to. Graphify tells you
  *which* 2–3 files to open; it does not replace reading them.
- **Skip Graphify** for a symbol you already know the location of, or for a
  one-file change — just read the file.

## 6. Token impact

What we did to keep it cheap:

- `graph.json` is ~2.6 MB (~660k tokens). It is in **`.claudeignore`** and
  **`.gitignore`**, so Claude never reads it directly and it never gets
  committed. Claude reaches the data **only** through MCP query results.
- Targeted tools (`get_node`, `shortest_path`, `god_nodes`) return well under
  1 KB. A locate-then-read cycle typically costs a few hundred tokens of graph
  output plus the one or two files you actually open — instead of grepping and
  opening many files to reconstruct relationships.

What we **cannot** guarantee:

- `query_graph` on a broad question or `affected` on a hub node (e.g. `Belief`,
  135 edges) can return several KB. The tools self-report their token cost and
  suggest narrowing (`get_node` / a `context_filter`). Prefer the targeted
  tools; treat broad `query_graph` as a fallback.
- Net token savings depend on usage. Graphify pays off when it *prevents*
  multi-file exploration; it is not free if used to dump broad subgraphs.

## 7. Decisions

- **Dev-time tool, not runtime.** Graphify is not imported by Jarvis and is not
  in `pyproject.toml`. Removing it changes nothing about Jarvis's behaviour.
- **Deterministic path only.** We use `graphify update` (AST, no LLM). No API
  key, no semantic extraction, no community *labelling* by an LLM. This honours
  Jarvis's offline/deterministic principle (see `DECISIONS.md` D8).
- **No new infrastructure.** No Neo4j / Postgres / Redis / Elasticsearch. The
  graph is a local JSON file served over stdio MCP.
- **`graphify claude install` deliberately NOT run.** That command would edit
  `CLAUDE.md` and add a `PreToolUse` hook that could auto-inject graph context on
  every tool call — a token risk we chose to avoid. Integration is manual,
  explicit, and reviewable (`.mcp.json`, this doc, a short pointer in
  `DEVELOPMENT.md`).
- **Decoupled from Jarvis's future graph layer.** If Jarvis ever gains a graph
  *retrieval* capability of its own, it goes behind a domain-owned interface with
  Graphify as one swappable adapter — never a direct dependency. See below.

## 8. What Graphify is NOT

- **Not Jarvis's memory.** Jarvis's memory is episodic/semantic/belief state with
  evidence and provenance, owned by the domain and persisted via repositories.
  Graphify indexes *source code*, not cognition. It has no beliefs, no evidence
  weighting, no contradictions, no temporal stability.
- **Not a semantic retriever.** No embeddings. It answers structural questions
  ("what calls what"), not meaning-similarity questions.
- **Not a decision-maker.** Like an LLM in Jarvis, at most it *surfaces
  candidates* (here: code locations). It never judges.
- **Not authoritative state.** `graphify-out/` is a disposable, regenerable
  cache. The source code is the source of truth.

## 9. Future seam — Graph Retrieval for Jarvis (design only, not implemented)

If — and only if — Jarvis later needs a graph-retrieval capability *inside*
cognition (e.g. relating concepts across long-term memory), it should follow the
same boundary pattern as `PerceptionSource` / `LanguageModel` / repositories:

```
Jarvis (domain)  ──uses──▶  GraphRetriever   (Protocol, domain — no SDKs)
                                   ▲
                                   │ implements
                            GraphifyAdapter   (infrastructure — may shell out
                                                to graphify / read graph.json)
```

Proposed domain-side contract (copy-paste-ready; **do not add to `src/` until a
real consumer exists** — an unused abstraction would be drift, cf. `DECISIONS.md`
D10/D12):

```python
# domain/retrieval/graph_retriever.py  (FUTURE — not yet created)
from typing import Protocol, Sequence
from dataclasses import dataclass

@dataclass(frozen=True)
class GraphHit:
    identifier: str          # symbol / concept id
    location: str | None     # e.g. "src/…/belief.py:L188" when code-derived
    relation: str            # "calls" | "uses" | "relates_to" | …
    provenance: str          # "EXTRACTED" | "INFERRED" — never lose this
    weight: float            # caller derives confidence; retriever only reports

class GraphRetriever(Protocol):
    def neighbours(self, concept: str, *, depth: int = 1) -> Sequence[GraphHit]: ...
    def path(self, source: str, target: str) -> Sequence[GraphHit]: ...
    def impacted_by(self, concept: str, *, depth: int = 1) -> Sequence[GraphHit]: ...
```

Key rules for that future work (not now):

- The Protocol lives in the **domain**; the Graphify-specific adapter lives in
  **infrastructure** and is the only place that knows about `graph.json` / the
  `graphify` CLI. Swapping Graphify out means writing one new adapter.
- Graph hits are **candidates carrying provenance**, exactly like `Evidence`.
  Confidence stays *derived* by the domain — the retriever never asserts belief.
- It would sit alongside a future *semantic* retriever (embeddings), not replace
  episodic/semantic/belief memory. Retrieval augments cognition; it is not the
  store of truth.

Until a concrete consumer exists, this stays a design, not code.
