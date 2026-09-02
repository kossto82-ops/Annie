# Integración Odysseus → Jarvis (Fases 0–2)

Plan de integración de capacidades de **Odysseus** (`odysseus-dev/odysseus`, AGPL-3.0)
en Jarvis. Alcance acordado: **Fases 0–2** — Tool Registry, Deep Research y Compare.

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

## Fase 2 — Compare (evaluación ciega de modelos)

Jarvis ya tiene ~14 providers (`OpenAiCompatibleModel` + registry). Compare = prompt a
N modelos + síntesis ciega. No requiere red nueva.

**Reutilizar de Odysseus** (AGPL, como referencia/adaptador): `model_capabilities.py`,
`model_discovery.py`, `model_capability_readers/` (normalizar capacidades por modelo).

**Seam de dominio:**

```
src/jarvis/domain/services/model_compare.py      # ModelComparator Protocol + ModelRun
src/jarvis/infrastructure/model_compare_source.py # adapter sobre el registry de LLM
```

- Cada respuesta es **evidencia candidata** para el núcleo (D6: el LLM extrae, no juzga).
- La síntesis final la razona Jarvis; sin cara a cara con las creencias.

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
| 2a | `ModelComparator` + `ModelRun` | `pytest tests/domain/test_model_compare.py` | ⏳ |
| 2b | adapter sobre registry LLM | tests con providers stub | ⏳ |

Al cierre: `pytest` (suite completa), `ruff check src`, `pyright src` (strict) — sin
errores, como exige el repo.
