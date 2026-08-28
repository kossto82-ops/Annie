# Jarvis — Auditoría Arquitectónica (2026-08-28)

> Fase 1 del pipeline `docs/claude/prompts/01_AUDITORIA.md`. Solo análisis — no se modificó código durante la auditoría.
> Método: 4 agentes de exploración read-only (dominio, infraestructura/model-layer, orquestación/UI, tests/config) + verificación de suite y estado git.

## Estado actual (resumen)

Motor cognitivo DDD en Python, **stdlib-only (cero dependencias runtime)**, ~7.500 LOC, **574 tests verdes + 3 skips deliberados en 1,7s**, deterministas y offline. Disciplina alta: sin `NotImplementedError`, sin `TODO`/`FIXME`, sin stubs `pass` en el dominio. El invariante **"la confianza se deriva de la evidencia, nunca se asigna"** está implementado en código, no solo documentado. La documentación normativa (`AI_CONTEXT.md`, `ARCHITECTURE.md`, `STATUS.md`) es coherente con el código real.

## Arquitectura real (por componente)

| Área | Estado | Nota |
|---|---|---|
| Domain: Belief / Confidence / Evidence / TemporalStability | EXISTS | Confianza = `soporte/(soporte+contra+1)`; nunca alcanza 1.0; sin setter |
| Domain: CognitiveEpisode (máquina de estados) | EXISTS | `CREATED→REASONING→REFLECTING→DECIDING→COMPLETED/FAILED`, transiciones ilegales bloqueadas |
| Domain: Hypothesis/HypothesisSet | EXISTS | `leading()` devuelve `None` en empate — no colapsa incertidumbre |
| Domain: servicios (association, reflection, curiosity, action_advisor, goal_reflection, self_observation, hypothesis_generation) | EXISTS + USED | Usados y testeados; ninguno muerto |
| Domain: Reasoner / MemoryRetriever (seams) | EXISTS (protocol) | LLM solo propone; el core juzga |
| Executive: `ExecutiveController.run` | EXISTS (thin) | Ciclo de episodio ~50 líneas, delega al dominio |
| Executive: `_reflect` (fase Reflect de episodio normal) | STUB | No-op: `_ = belief`, "sin salida observable aún" |
| Infra: stores in-memory + JSON | EXISTS | Sin DB real; reescritura de archivo completo por escritura |
| Infra: EpisodeTrace | EXISTS (solo memoria) | Volátil — no persiste provenance entre reinicios |
| Infra: LanguageModel + registry + OpenAI-compatible adapter | EXISTS | Sin SDK de proveedor; 13+ proveedores + Ollama/LM Studio; transport inyectable |
| Interface: command center (handle/route/snapshot) | EXISTS (puro, testeable) | HTTP stdlib; voz y cara client-side |
| Tools / agencia en el mundo | MISSING (por diseño) | grep de `subprocess/os.system/requests/git/mcp` → 0 |
| DB real | MISSING (por diseño) | JSON files es el único sustrato durable |
| Forgetting / decay temporal | MISSING | Evidencia se acumula para siempre; confianza ciega a la edad |

## Traza de una interacción real

`POST /api/say → route → handle → _say_core`:
1. Confirmación (≤5 palabras sí/no) madura la respuesta provisional del episodio anterior (`confirm`).
2. Percepción: `perceive(text)` → `Evidence` (default `KeywordPerception`; LLM detrás del protocolo).
3. Canal relacional: segundo pase `note_companion` → rasgos del usuario. **Dos round-trips LLM por turno** (el código lo señala).
4. Seed de contexto desde `CompanionModel` → evidencia `SYSTEM_OBSERVATION`.
5. Recall de memoria (léxico por defecto, embeddings si hay embedder; umbral 0.2).
6. Reasoning (`_reason_into`): solo si no hay creencia fundada ni recall fuerte → `Inference` peso 0.2.
7. Tools: no existe esta etapa. Ninguna acción toca el mundo.
8. Decisión → string de conclusión por umbrales de confianza/estabilidad.
9. Persistencia inmediata a JSON + carga de energía.

Huecos: la fase Reflect de un episodio normal es un stub; no hay ejecución de herramientas; la percepción del companion es silenciosa sin LLM.

## Memory / Reasoning / Model layer / Tools / Testing

- **Memory**: 4 tipos por procedencia (`WORLD_BELIEF`, `EPISODE`, `COMPANION_TRAIT`, `GOAL`). Working = campos transitorios del episodio; semántica ≈ store de creencias; user-context = `CompanionModel`. Contradicción = información (baja confianza + evento), nunca sobrescritura. Sin forgetting.
- **Reasoning**: arquitectura de dominio real (máquina de estados + hipótesis competidoras + ciclo reflexivo con falsación `Challenge`/`refute`), no chain-of-thought del LLM. `EvidenceRequest` nombra el hueco concreto.
- **Model layer**: `Jarvis → LanguageModel (Protocol) → registry → provider`. Cero acoplamiento a proveedor, seam OmniRoute ya previsto. Live call opt-in (default `scripted` offline). Secretos solo en env/`.env`, por-proveedor, write-only.
- **Tools**: agencia nula en el mundo — por diseño (§28). `Action` solo registra intención; `recommend()` da stance (SUGGEST/ASK_FIRST/WITHHOLD).
- **Testing**: fuerte en dominio/infra/executive; débil en `nervous_system` y `server.py` (binding solo smoke opt-in). `test_examples.py` = e2e real de 6 ejemplos.

## Problemas / deuda técnica

1. **`reflect_cycle` docstring vs. cuerpo** (`jarvis.py:906`): dice "Connect → Reflect → …" pero no llama a `connections()` y omite Act. El ciclo de 7 fases solo existe como piezas sueltas.
2. **`ExecutiveController._reflect` es placeholder** — la fase Reflect del episodio ordinario no hace nada.
3. **JSON no atómico** en belief/episode stores (crash a mitad de `_flush` puede corromper); reescritura O(n) por save.
4. **EpisodeTrace volátil** — no hay provenance durable entre reinicios (fricción con §26).
5. **Doble round-trip LLM por turno** (coste/latencia).
6. **`Jarvis.persistent()` muerto respecto a la app** — el server recablea su propio wiring; pueden divergir.
7. **Matching ingenuo** (substring/exact) en `CompanionModel.relevant_to`, goals y ruteo de auto-preguntas.
8. **`fail()` no emite evento** `EpisodeFailed`.
9. **Seguridad**: `.env` tiene 2 API keys en texto plano, pero NO está trazado, está en `.gitignore` y nunca se comiteó. Riesgo limitado a la máquina local.

## Gap analysis vs. visión

| Capacidad | Estado |
|---|---|
| Construir/actualizar creencias con evidencia | IMPLEMENTED |
| Confianza derivada + contradicciones explícitas | IMPLEMENTED |
| Hipótesis competidoras sin colapsar | IMPLEMENTED |
| Memoria episódica/semántica/companion + persistencia | IMPLEMENTED (JSON) |
| Ciclo reflexivo (Remember→…→Learn) | PARTIAL (bundle salta Connect y Act; Reflect de episodio = stub) |
| LLM swappable / model-independence | IMPLEMENTED |
| Recall semántico (embeddings) | IMPLEMENTED (fallback léxico) |
| Reasoning multi-paso verificable | PARTIAL (falsación sí; verificación de resultados limitada) |
| Forgetting / decay temporal | MISSING |
| Provenance durable (trace persistido) | MISSING |
| Uso de herramientas / agencia | MISSING (por diseño, gated) |
| Autonomía controlada | PARTIAL (stances recomendados; sin ejecutor) |
| Personalidad coherente | PARTIAL (self-observation + tendencias; sin capa de personalidad) |

## Prioridades

- **P0 — Fundación crítica**: (a) resolver mismatch `reflect_cycle` docstring/cuerpo y decidir si Connect+Act entran; (b) persistencia JSON atómica (temp+`os.replace`).
- **P1 — Core**: implementar `ExecutiveController._reflect`; persistir EpisodeTrace; emitir `EpisodeFailed`.
- **P2 — Cognitivas**: forgetting/decay temporal con política inyectable; verificación de resultados en reasoning; matching semántico.
- **P3 — Agencia**: primer `Tool`/effector detrás de gate de confirmación + reversibilidad (solo-lectura primero), respetando §28.
- **P4 — Social/personalidad**: capa de personalidad coherente sobre self-observation.

## Capacidad recomendada como siguiente

Consolidar el ciclo reflexivo (P0/P1): alinear `reflect_cycle` con su contrato e implementar la fase Reflect del episodio. Cierra la brecha entre "las piezas existen" y "la cognición reflexiva end-to-end" — bajo riesgo, alto valor.
