# Integración Odysseus → Jarvis (Fases 0–3)

Plan de integración de capacidades de **Odysseus** (`odysseus-dev/odysseus`, AGPL-3.0)
en Jarvis. Alcance acordado: **Fases 0–3** — Tool Registry, Deep Research, Compare y
capacidades dentro de la cognición.

## Naturaleza de la integración

Odysseus es una **aplicación web autohospedada** (backend FastAPI + frontend web), no
una librería. No es un `pip install` y no se incrusta su runtime de app ni su frontend.
Se aprovechan **módulos autocontenidos y reutilizables** (deep research, search,
evaluación de modelos) como **adaptadores en el borde** de Jarvis.

La regla de oro: cada capacidad entra detrás de un **Protocol de dominio** en Jarvis,
siguiendo el patrón ya probado por `ExternalSource`/`AgentReachSource`
(`src/jarvis/infrastructure/agent_reach_source.py`):

- Protocol de dominio + adapter en `infrastructure`
- red/AGPL en el borde, transporte inyectable (tests deterministas y offline)
- `build_*_source()` devuelve `None` cuando el paquete no está → Jarvis funciona igual
  (D8, D7, D6)

## Restricciones de arquitectura que se respetan

- **D1** — Jarvis no es un agente autónomo exterior. El Tool Registry habilita
  *herramientas invocables*; la decisión de `cuándo` usar sigue en el núcleo (Vision §34).
- **D6** — El LLM extrae evidencia candidata; la síntesis/juicio vive en el dominio.
- **D7** — Red/AGPL solo en `infrastructure`, nunca en el dominio.
- **D8** — Tests de la suite por defecto offline y deterministas; integraciones opt-in.
- **D9** — La UI no es cognición; las decisiones ocurren en el núcleo primero.
- **D12** — Sin abstracciones genéricas (`Manager`/`Orchestrator`/`Engine`) sin
  responsabilidad de dominio clara.

## Licencia

Los módulos reutilizados de Odysseus se copian/adaptan con compatibilidad **AGPL-3.0**.
Cada archivo llevará el encabezado `# Reused from odysseus-dev/odysseus (AGPL-3.0)`
y se documenta aquí. Jarvis solo queda afectado por AGPL en esas piezas del borde.

---

## Fase 0 — Tool Registry interno de Jarvis (pre-requisito)

Jarvis hoy **no** ejecuta herramientas: `docs/claude/prompts/06_TOOLS_AGENCY.md` es solo
diseño. Odysseus aporta el modelo maduro de agencia (permisos + approval), no su runtime.

**Reutilizar como referencia de diseño** (AGPL): `task_action_policy.py`,
`tool_approvals.py`, `tool_approval_scopes.py`, `tool_parsing.py` de `src/`.

**Implementar en Jarvis** (dominio, sin LLM) — **✅ completo en esta iteración**:

```
src/jarvis/domain/enums/permission_level.py   # READ/WRITE/EXECUTE/EXTERNAL/DESTRUCTIVE
src/jarvis/domain/value_objects/tool_spec.py  # qué es una herramienta y su permiso
src/jarvis/domain/value_objects/tool_call.py  # registro inmutable de una invocación
src/jarvis/domain/value_objects/tool_call_result.py  # resultado con éxito/error
src/jarvis/domain/events/tool_events.py       # ToolCallRecorded (observabilidad)
src/jarvis/domain/tools/tool.py               # Tool Protocol
src/jarvis/domain/tools/tool_policy.py        # aprobación de destructivas/externas
src/jarvis/domain/tools/tool_registry.py      # selección→permiso→ejecución→observación
src/jarvis/infrastructure/echo_tool.py        # herramienta de demostración (EXECUTE)
src/jarvis/infrastructure/filesystem_tool.py  # lectura/escritura encajonada y testeable
```

- **Observabilidad**: cada llamada registra herramienta, args relevantes, resultado,
  error, duración, nivel de permiso — sin secrets (se integra con `EpisodeTrace` y la
  NervousSystem ya existentes).
- **Sin autonomía**: son herramientas invocables; Jarvis no dispara acciones por sí solo.

**Verificación**: suite de `06_TOOLS_AGENCY.md` — herramienta válida/inexistente/args
inválidos/permiso insuficiente/error/timeout/destructiva/confirmación.

## Fase 1 — Deep Research — ✅ completo

Extiende la integración web que Jarvis ya tiene (`ExternalSource`). Los documentos ya
vuelven como `RetrievedDocument` con procedencia (Vision §8).

**Encuentro material con el código real de Odysseus:** `src/deep_research.py`
(`DeepResearcher`) no es un módulo suelto — es un bucle async **LLM-driven** que genera
queries, decide cuándo parar y sintetiza el reporte entero con el LLM, acoplado al
runtime de la app (`src.llm_core`, `services.search`, `src.scraping`, `httpx`/`bs4`).
Incrustarlo tal cual violaría D6/D9: el LLM decidiría/juzgaría en lugar de Jarvis.

**Decisión (acordada):** Seam `ResearchSource` + adaptador SearXNG propio en el borde.
Se reutiliza de Odysseus **el protocolo de búsqueda SearXNG JSON API**
(`services/search/providers.py::searxng_search_api`, AGPL-3.0) — reimplementado como
adaptador autocontenido, sin acoplar la app de Odysseus a Jarvis (D7, D8). El
razonamiento, la síntesis y cuándo parar quedan en el núcleo de Jarvis (D6).

**Nuevo seam de dominio:**

```
src/jarvis/domain/retrieval/research_source.py     # ResearchSource Protocol
   deep_research(query, *, depth) -> ResearchReport
src/jarvis/domain/value_objects/research_report.py # VO: summary + documentos citados
src/jarvis/infrastructure/odysseus_search_source.py  # adapter SearXNG (transporte inyectable)
   build_odysseus_search_source() -> None sin SEARXNG_INSTANCE
```

- `ResearchReport` = valor inmutable con `RetrievedDocument` citados → Jarvis razona
  sobre él como evidencia con procedencia. El summary del adapter es una descripción
  honesta y mecánica de la recuperación, **nunca una conclusión** (D6).
- `build_odysseus_search_source()` devuelve `None` sin instancia (offline normal, D8).
- Superficie `Jarvis`: `research_source` property, `set_research_source()`,
  `deep_research(query, depth)`; `persistent()` lo cablea *si hay instancia*.
- Superficie Command Center: comando `research` (junto a `external` / `channels`).

## Fase 2 — Compare (evaluación ciega de modelos) — ✅ completo

Jarvis ya tiene ~14 providers (`OpenAiCompatibleModel` + registry). Compare = prompt a
N modelos + síntesis ciega. No requiere red nueva.

**Reutilizar de Odysseus** (AGPL, como referencia): `model_capabilities.py`,
`model_discovery.py`, `model_capability_readers/` (normalizar capacidades por modelo).
En el código real, `model_discovery` sería descubrimiento por red local (Tailscale/ports);
para la evaluación ciega de modelos basta **el registry de LLM ya existente en Jarvis**
(`language_model_registry.py`), que expone ~14 providers vía `LanguageModel`.

**Seam de dominio:**

```
src/jarvis/domain/services/model_compare.py       # ModelComparator Protocol + ModelRun
   compare(prompt, *, models=None) -> tuple[ModelRun, ...]
src/jarvis/infrastructure/model_compare_source.py # RegistryModelComparator sobre el registry
   build_model_compare_source(models) -> None sin modelos configurados
```

- `ModelRun` = VO inmutable (`model`, `response`) con procedencia por modelo — la
  respuesta es **evidencia candidata** para el núcleo (D6: el LLM extrae, no juzga).
- El adapter solo **recoge**: no rankea, no elige "mejor", no sintetiza. Un modelo
  que falla o no existe se reporta con error claro (nunca se fabrica).
- La síntesis final la razona Jarvis; sin cara a cara con las creencias.
- Superficie `Jarvis`: `model_compare` property, `set_model_compare()`,
  `compare_models(prompt, models=...)` (opt-in, offline por defecto, D8).
- Superficie Command Center: comando `compare` (junto a `external` / `research`).

---

## Orden de ejecución

| Paso | Trabajo | Verificación | Estado |
|---|---|---|---|
| 0a | Tool Registry dominio (Protocol, policy, permiso) | `pytest tests/domain/test_tool_registry.py` | ✅ hecho |
| 0b | Tool impls en borde (filesystem, echo) | `pytest tests/infrastructure/test_tools.py` | ✅ hecho |
| 0c | Observabilidad tool calls | `pytest tests/test_jarvis_tools.py` | ✅ hecho |
| 1a | `ResearchSource` Protocol + `ResearchReport` VO | `pytest tests/domain/test_research_report.py` | ✅ hecho |
| 1b | adaptador SearXNG (`odysseus_search_source`) | `pytest tests/infrastructure/test_odysseus_search_source.py` | ✅ hecho |
| 1c | Superficie Jarvis + comando `research` | `pytest tests/test_command_center.py` | ✅ hecho |
| 2a | `ModelComparator` + `ModelRun` | `pytest tests/domain/test_model_compare.py` | ✅ hecho |
| 2b | adapter sobre registry LLM | `pytest tests/infrastructure/test_model_compare_source.py` | ✅ hecho |
| 3a | `KnowledgeSource` Protocol + procedencia en el episodio | `pytest tests/test_knowledge_source.py` | ✅ hecho |
| 3b | adaptadores research/compare + guardas en el executive | `pytest tests/infrastructure/test_knowledge_source_adapters.py` | ✅ hecho |

Al cierre: `pytest` (suite completa), `ruff check src`, `pyright src` (strict) — sin
errores, como exige el repo.

---

## Segunda pasada (auditoría de Fases 0–2) — ✅ completo

Auditoría post-integración (2026-09-02) y los dos hallazgos que se resolvieron:

- **A — Gate "earned" uniforme para research/compare:** `external` exigía
  `can_do` (cap. adquirida + provider, §28) pero `research`/`compare` solo
  verificaban el cableo. Ahora ambos pasan por el mismo gate: `build_default_registry`
  registra `ResearchCapability`/`ModelCompareCapability` cuando el seam está cableado
  (`set_research_source`/`set_model_compare` reconstruyen el auto-registry), y el
  command center distingue *not wired* de *not earned* vía `_capability_not_ready`.
  El scout ganó los templates `deep research` y `compare language models`, así el
  flujo completo scout → acquire → use existe de extremo a extremo.
- **B — Superficie UI para herramientas:** nuevo comando `tool` en el command
  center (`list` / `run`), ejecutando detrás del gate de política (external/
  destructivas exigen `approved: true`). El resultado vuelve como outcome, nunca
  como veredicto (D6).

Limpieza de los hallazgos menores (C/D/F):
- **C —** `depth` acotado en `SearXNGResearchSource` (`_MAX_DEPTH = 10`): un depth
  hostil nunca pide un result-set ilimitado; docstrings aclaran que `depth` escala
  resultados por ronda, no rondas.
- **D —** `capability notice` etiqueta sus brechas como `SYSTEM_OBSERVATION`
  (no `USER_STATEMENT`): un gap que Jarvis se observa a sí mismo pesa
  `0.6 × peso`, nunca como una afirmación del companion.
- **F —** `FileSystemTool` valida `operation`: un typo nunca escribe silenciosamente.

---

## Fase 3 — Capacidades dentro de la cognición (consulta deliberada) — ✅ completo

Hasta Fase 2, las capacidades Odysseus eran **invocables a demanda** (comandos
`research` / `compare`): la superficie pregunta, el núcleo espera. Fase 3 cierra la
hélice: que el propio núcleo **decida** cuándo consultarlas como evidencia de
entrada, del mismo modo deliberado con que decide recordar o razonar (Vision §37).

**Seam de dominio** (`KnowledgeSource`, espejo de `Reasoner`/`MemoryRetriever`, D7):

```
src/jarvis/domain/services/knowledge_source.py   # KnowledgeSource Protocol
   kind: str                                     # etiqueta de procedencia ("deep research")
   gather(question) -> Evidence | None           # evidencia candidata, o None honesto
src/jarvis/infrastructure/knowledge_source.py    # adaptadores sobre los edges Odysseus
   ResearchKnowledgeSource(research)             # reporte -> EXTERNAL_SOURCE (0.4)
   CompareKnowledgeSource(comparator)            # réplicas ciegas -> INFERENCE (0.5)
```

**Dónde y cuándo (todo en el executive, `ExecutiveController`):**

- Guardas iguales a las del razonamiento (Vision §37): la creencia sin
  fundamento real, sin recall fuerte (relevance ≥ 0.6), y **una sola** consulta por
  episodio. Corre **antes** de razonar: si lo reunido fundamenta la creencia, el
  episodio no pide una inferencia innecesaria.
- El borde solo **recoge** (D6): la confianza se sigue derivando de la evidencia;
  `None` es un consultar honesto "no hay nada" y el episodio sigue igual.
- Procedencia en el episodio: `CognitiveEpisode.consulted` + `record_consult(kind)`
  (Vision §26) — un trace puede decir *qué* edge se preguntó y qué volvió.
- Fuentes honestas de la evidencia: research → `EXTERNAL_SOURCE` (débil, de fuera,
  no verificada por los sentidos de Jarvis); compare → `INFERENCE` (texto candidato
  de modelos, la fuente más débil; nunca supera una observación real, Vision §33).
- Un edge que falla o no encuentra nada devuelve `None`, nunca una afirmación (D6, D8).

**Superficie `Jarvis`:** param/property/setter `knowledge_source` (opt-in). No se
cablea en `persistent()`: consultar un edge es una decisión explícita del operador.

**Verificación:** suite completa (825 passed), `ruff`, `pyright src` (strict).
Tests: `tests/test_knowledge_source.py` (protocolo + guardas + procedencia) y
`tests/infrastructure/test_knowledge_source_adapters.py` (adapters + end-to-end
offline por Jarvis), 19 tests nuevos.
