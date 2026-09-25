# Jarvis — Claude Context Index

| File | Purpose | Load by default? |
|---|---|---|
| `CLAUDE.md` | Permanent Claude Code rules and pointers | Yes |
| `docs/claude/SYSTEM_TODAY.md` | **Source of truth**: how Jarvis works today, user input → reply | Tasks on cognition/memory/recall |
| `docs/claude/AI_CONTEXT.md` | Compact current project context + increment snapshots | Yes for context |
| `docs/claude/ARCHITECTURE.md` | Architecture, layer map, boundaries | Architecture tasks |
| `docs/claude/DECISIONS.md` | Non-negotiable architectural decisions (D1–D32) — **single decision authority** | Architecture tasks |
| `docs/claude/ROADMAP_TO_ZERO_FALLOUT.md` | Phased plan (F0–F8) closing every verified gap, each with an acceptance gate | "What's next"/gap work |
| `docs/claude/DEVELOPMENT.md` | Efficient coding/testing workflow | Development tasks |
| `docs/claude/CONTEXT_POLICY.md` | Context/token loading rules | Reference |
| `JARVIS_VISION.md` | Foundational vision | Major design/vision tasks |
| `STATUS.md` | Historical increment log + decision log | Historical questions only |
| `docs/claude/INTEGRACION_ODYSSEUS.md` | Odysseus plan (HISTORICAL — implemented, see ARCHITECTURE.md §Odysseus) | Historical |
| `docs/claude/INTERNET_AGENT_REACH.md` | Agent-Reach plan (HISTORICAL — implemented) | Historical |
| `docs/claude/MEMORY_AND_REASONING_ANALYSIS.md` | Pre-162 memory diagnosis (HISTORICAL — superseded) | Historical |
| `docs/claude/SEMANTIC_ATTENTION_AUDIT.md` | Attention-repair audit (HISTORICAL — implemented, Increments 163-165) | Historical |
| `docs/claude/SEMANTIC_COGNITION_IMPLEMENTATION.md` | Semantic cognition implementation (HISTORICAL — implemented) | Historical |
| `docs/claude/REMEDIATION_PLAN.md` | Memory-line remediation plan (HISTORICAL — implemented) | Historical |
| `docs/claude/REMEDIATION_REPORT.md` | Post-165 remediation report (HISTORICAL) | Historical |
| `docs/claude/ROADMAP_ARCHITECTURAL_AUDIT.md` | Architectural audit roadmap (HISTORICAL — completed Phases 0-5) | Historical |
| `docs/claude/IMPLEMENTATION_PLAN.md` | Implementation plan (HISTORICAL — completed) | Historical |
| `docs/claude/PLAN_COMMAND_CENTER.md` | Command-center plan (HISTORICAL — implemented) | Historical |

## Historical markers

Files marked HISTORICAL in `docs/claude/` are dated plans, audits, or remediation records that predate
Increments 162-170. They are kept for provenance, never as a description of the current system
(`SYSTEM_TODAY.md` / `ARCHITECTURE.md` are authoritative).

## Rule of thumb

If the task can be solved by reading one source file and one test, do not read five documents.