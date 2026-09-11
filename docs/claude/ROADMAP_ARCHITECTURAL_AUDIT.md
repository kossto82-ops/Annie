# Jarvis — Plan de Arquitectura Post-Auditoría

> Generado a partir de la auditoría arquitectónica profunda (2026-09-11).
> **Este es un plan, NO implementación.** Ningún archivo se modifica aquí.

---

## Resumen Ejecutivo

La auditoría reveló que Jarvis tiene un dominio sólido y una epistemología genuina, pero sufre de
cuatro cuellos de botella arquitectónicos que impiden alcanzar la visión de "compañero cognitivo
a largo plazo":

1. **`jarvis.py` es un God Object de 3336 líneas** — composition root, API pública, router de
   conversación, gestor de metas, learner de acciones, motor de curiosidad, orquestador del
   ciclo reflexivo, sistema de introspección, y fábrica de persistencia.
2. **La recuperación de memoria es plana** — token overlap / cosine similarity. Sin consultas
   temporales, relacionales o estructuradas.
3. **No existe mecanismo de abstracción** — los episodios se registran pero nunca se sintetizan
   en conocimiento de mayor nivel.
4. **No existe knowledge graph** — no hay entidades, relaciones ni traversabilidad.

El plan se organiza en **5 fases** incrementales, cada una con entregables verificables.
Cada fase es un incremento independiente que puede completarse y validarse antes de pasar a la
siguiente.

---

## Fase 0: Deuda Arquitectónica Crítica (God Object Split)

**Objetivo:** Eliminar el cuello de botella de mantenibilidad sin cambiar comportamiento.

**Justificación:** `jarvis.py` (3336 líneas) es el composition root Y la API pública AND el
router de conversación AND el gestor de metas AND el learner de acciones AND el motor de
curiosidad AND el orquestador reflexivo AND el sistema de introspección AND la fábrica de
persistencia. Cada método es individualmente limpio, pero el archivo viola responsabilidad
única. Cualquier cambio futuro crea conflictos de merge y dificulta el razonamiento sobre
el código.

### Entregables

| # | Archivo nuevo | Responsabilidad | Líneas estimadas |
|---|---------------|-----------------|------------------|
| 0.1 | `src/jarvis/cognitive.py` | `think()`, `perceive()`, `perceive_all()`, `consider()`, `reason()`, `reason_stream()`, `confirm()`, `resolve()`, `ask_about()` — la superficie cognitiva pura | ~400 |
| 0.2 | `src/jarvis/companion.py` | `observe_companion()`, `perceive_about_companion()`, `explain_companion()`, `companion` property — modelo del compañero | ~200 |
| 0.3 | `src/jarvis/goals.py` | `mark_goal_reached()`, `recurring_goals()`, `sub_goals()`, `goal_progress()`, `stuck_goals()`, `ask_for_help()`, `receive_help()`, `reflection_effort()` — gestión de metas | ~400 |
| 0.4 | `src/jarvis/actions.py` | `act()`, `record_outcome()`, `belief_about_action()`, `recommend_action()`, `recommend_action_by_description()` — aprendizaje de acciones | ~200 |
| 0.5 | `src/jarvis/curiosity.py` | `feel_curious()`, `pursue()`, `connections()`, `reflect()`, `hypothesise()`, `challenge()`, `learn_from_reflection()`, `act_on_insight()`, `reflect_cycle()`, `refute()` — curiosidad y ciclo reflexivo | ~500 |
| 0.6 | `src/jarvis/introspection.py` | `observe_self()`, `observe_overconfidence()`, `observe_prediction_accuracy()`, `self_beliefs()`, `introspect()`, `state_summary()` — auto-observación | ~200 |
| 0.7 | `src/jarvis/persistence.py` | `persistent()`, `database()` — fábricas de persistencia | ~150 |
| 0.8 | `src/jarvis/jarvis.py` (refactorizado) | Clase `Jarvis` como fachada delgada que delega a los módulos anteriores; conserva `__init__` (composition root) y métodos de orquestación | ~800 |

### Criterios de aceptación

- [ ] Todos los tests existentes pasan sin modificación
- [ ] `jarvis.py` queda ≤ 1000 líneas
- [ ] Ningún método público cambia de firma
- [ ] El composition root (`__init__`) permanece en `jarvis.py`
- [ ] Cada módulo nuevo es independiente y testeable
- [ ] `ruff check .` y `pyright --strict` pasan sin errores

### Orden de implementación

1. Extraer `persistence.py` (sin dependencias cognitivas)
2. Extraer `introspection.py` (solo lectura de estado)
3. Extraer `actions.py` (depende de beliefs store)
4. Extraer `goals.py` (depende de beliefs store + episodes)
5. Extraer `companion.py` (depende de CompanionModel)
6. Extraer `cognitive.py` (depende de executive + perception + reasoner)
7. Extraer `curiosity.py` (depende de self_beliefs + reflective cycle)
8. Refactorizar `jarvis.py` como fachada

---

## Fase 1: Memoria Semántica (P0)

**Objetivo:** Transformar experiencias individuales en conocimiento de mayor nivel.

**Justificación:** Los episodios se registran como `EpisodeRecord` pero nunca se sintetizan.
El ciclo reflexivo detecta patrones de evidencia compartida pero no crea abstracciones,
categorías o principios generales. Jarvis no puede aprender "los usuarios que prefieren
simplicidad tienden a preferir UIs minimalistas" de observaciones específicas múltiples.

### 1.1 — Modelo de Memoria Semántica

**Archivo nuevo:** `src/jarvis/domain/entities/semantic_memory.py`

```python
@dataclass(slots=True, eq=False)
class SemanticMemory:
    """Un patrón o abstracción derivado de múltiples episodios/experiencias."""
    id: str                          # UUID
    pattern: str                     # "Los usuarios que X tienden a Y"
    source_episode_ids: list[str]    # episodios que originaron este patrón
    source_belief_ids: list[str]     # creencias que contribuyeron
    confidence: Confidence           # derivada del soporte
    stability: TemporalStability     # derivada de la distribución temporal
    formed_at: datetime
    last_reinforced_at: datetime | None
    reinforcement_count: int
    _evidence: list[Evidence]        # evidencia que soporta el patrón
    _pending_events: list[CognitiveEvent]
```

**Propiedades derivadas (sin setter):**
- `confidence` → `derive_confidence(_evidence, policy)`
- `stability` → `derive_stability(_evidence)`

**Invariante:** La confianza de una memoria semántica NUNCA excede la evidencia que la soporta.
Exactamente la misma regla que `Belief`.

### 1.2 — Servicio de Abstracción

**Archivo nuevo:** `src/jarvis/domain/services/abstraction.py`

```python
def abstract_patterns(
    episodes: list[EpisodeRecord],
    beliefs: list[Belief],
    min_sources: int = 3,
) -> list[SemanticMemory]:
    """Detecta patrones recurrentes en episodios y creencias y genera
    memorias semánticas. Cada patrón debe tener al menos `min_sources`
    fuentes independientes."""
```

**Algoritmo propuesto:**
1. Clusterizar episodios por subject (usa la misma lógica que `detect_capability_gaps`)
2. Para cada cluster con ≥ `min_sources` episodios:
   a. Extraer el tema común (subject words en intersección)
   b. Buscar creencias relacionadas (por overlap de evidencia)
   c. Crear `SemanticMemory` con evidencia de cada fuente
   d. Derivar confianza y estabilidad de la evidencia combinada
3. Retornar patrones ordenados por confianza descendente

### 1.3 — Repositorio de Memoria Semántica

**Protocolo nuevo:** `src/jarvis/domain/repositories/semantic_memory_repository.py`

```python
class SemanticMemoryRepository(Protocol):
    def get_by_pattern(self, pattern: str) -> SemanticMemory | None: ...
    def save(self, memory: SemanticMemory) -> None: ...
    def all_memories(self) -> tuple[SemanticMemory, ...]: ...
    def search(self, query: str, limit: int = 5) -> tuple[SemanticMemory, ...]: ...
```

**Implementaciones:**
- `InMemorySemanticMemoryStore` (tests)
- `SqliteSemanticMemoryStore` (persistencia)
- `JsonSemanticMemoryStore` (legacy)

### 1.4 — Integración con Recuperación

**Modificar:** `src/jarvis/infrastructure/memory_candidates.py`

Agregar `SemanticMemory` como fuente de candidates en `gather_candidates()`:

```python
# Después de world_beliefs, episodes, companion_traits, goals:
for memory in semantic_memories:
    candidates.append(Candidate(
        match_text=memory.pattern,
        content_to_show=memory.pattern,
        kind=MemoryKind.SEMANTIC,  # nuevo valor de enum
        provenance="semantic pattern",
        confidence=memory.confidence.value,
    ))
```

**Modificar:** `src/jarvis/domain/enums/memory_kind.py`

Agregar `SEMANTIC = "semantic"` al enum.

### 1.5 — Integración con Ciclo Reflexivo

**Modificar:** `src/jarvis/curiosity.py` (o el módulo equivalente post-Fase 0)

Después del paso `Learn` en `reflect_cycle()`, ejecutar:

```python
new_patterns = self._abstract_patterns()
# Cada patrón nuevo se registra como episodio de tipo ABSTRACTION
```

### 1.6 — Integración con Persistencia

**Modificar:** `src/jarvis/infrastructure/sqlite_database.py`

Agregar tabla `semantic_memories` al `build_sqlite_repositories()`.

**Modificar:** `src/jarvis/jarvis.py` (o `persistence.py` post-Fase 0)

`Jarvis.persistent()` y `Jarvis.database()` wiring el nuevo repositorio.

### Entregables

| # | Archivo | Acción |
|---|---------|--------|
| 1.1 | `domain/entities/semantic_memory.py` | Crear |
| 1.2 | `domain/services/abstraction.py` | Crear |
| 1.3 | `domain/repositories/semantic_memory_repository.py` | Crear |
| 1.4 | `infrastructure/in_memory_semantic_memory_store.py` | Crear |
| 1.5 | `infrastructure/sqlite_semantic_memory_store.py` | Crear |
| 1.6 | `infrastructure/json_semantic_memory_store.py` | Crear |
| 1.7 | `domain/enums/memory_kind.py` | Modificar (agregar SEMANTIC) |
| 1.8 | `infrastructure/memory_candidates.py` | Modificar (agregar source) |
| 1.9 | `infrastructure/sqlite_database.py` | Modificar (agregar tabla) |
| 1.10 | Tests: `tests/domain/test_semantic_memory.py` | Crear |
| 1.11 | Tests: `tests/domain/test_abstraction.py` | Crear |
| 1.12 | Tests: `tests/infrastructure/test_sqlite_semantic_memory_store.py` | Crear |
| 1.13 | Tests: `tests/test_semantic_recall.py` | Crear |

### Criterios de aceptación

- [ ] `abstract_patterns()` genera `SemanticMemory` desde 3+ episodios relacionados
- [ ] La confianza de la memoria semántica es derivada (no setteada)
- [ ] Las memorias semánticas persisten y sobreviven reinicios
- [ ] `MemoryRetriever.recall()` incluye memorias semánticas en los resultados
- [ ] El ciclo reflexivo genera abstracciones después de `Learn`
- [ ] Todos los tests existentes siguen pasando
- [ ] `ruff check .` y `pyright --strict` pasan

---

## Fase 2: Razonamiento Temporal (P0)

**Objetivo:** Consultar, razonar y recuperar por tiempo.

**Justificación:** El sistema no puede responder "¿de qué hablamos hace varios meses sobre X?"
No puede distinguir "Raúl creía X en enero" de "Raúl cree X ahora" más allá de timestamps
individuales en evidencia.

### 2.1 — Extender EpisodeRecord con Timestamps de Creencia

**Modificar:** `src/jarvis/domain/value_objects/episode_record.py`

Agregar campos:
```python
belief_formed_at: datetime | None     # cuándo se formó la creencia trabajadora
belief_confidence_at_end: Confidence  # confianza al final del episodio
```

### 2.2 — Índice Temporal en Repositorios

**Modificar:** `src/jarvis/domain/repositories/episode_repository.py`

```python
class EpisodeRepository(Protocol):
    # ... existente ...
    def history_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[EpisodeRecord, ...]: ...
    def history_about(
        self, subject: str, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[EpisodeRecord, ...]: ...
```

**Implementar en:**
- `SqliteEpisodeStore` (con query SQL temporal)
- `JsonEpisodeStore` (con filtro en memoria)
- `InMemoryEpisodeStore` (con filtro en memoria)

### 2.3 — Extender BeliefRepository con Consultas Temporales

**Modificar:** `src/jarvis/domain/repositories/belief_repository.py`

```python
class BeliefRepository(Protocol):
    # ... existente ...
    def beliefs_formed_between(
        self, start: datetime, end: datetime
    ) -> tuple[Belief, ...]: ...
    def beliefs_about(
        self, subject_pattern: str
    ) -> tuple[Belief, ...]: ...
```

### 2.4 — Memoria Retriever Temporal

**Modificar:** `src/jarvis/domain/retrieval/memory_retriever.py`

```python
class MemoryRetriever(Protocol):
    def recall(
        self,
        query: str,
        limit: int = 5,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[RecalledMemory, ...]: ...
```

**Modificar:** `src/jarvis/domain/value_objects/recalled_memory.py`

Agregar:
```python
observed_at: datetime | None  # cuándo ocurrió el recuerdo
```

### 2.5 — Modificadores de Tiempo en RecalledMemory

**Modificar:** `src/jarvis/infrastructure/memory_candidates.py`

Cuando `since` o `until` se proporcionan, filtrar candidates por `observed_at`.

### 2.6 — Integración con ConversationContext

**Modificar:** `src/jarvis/domain/conversation/conversation_context.py`

Persistir conversación (opcional) para soportar "¿de qué hablamos ayer?":

```python
class ConversationContext:
    # ... existente ...
    def history_range(
        self, start: datetime, end: datetime
    ) -> tuple[Turn, ...]: ...
```

### Entregables

| # | Archivo | Acción |
|---|---------|--------|
| 2.1 | `domain/value_objects/episode_record.py` | Modificar |
| 2.2 | `domain/repositories/episode_repository.py` | Modificar |
| 2.3 | `domain/repositories/belief_repository.py` | Modificar |
| 2.4 | `domain/retrieval/memory_retriever.py` | Modificar |
| 2.5 | `domain/value_objects/recalled_memory.py` | Modificar |
| 2.6 | `infrastructure/memory_candidates.py` | Modificar |
| 2.7 | `infrastructure/sqlite_episode_store.py` | Modificar |
| 2.8 | `infrastructure/json_episode_store.py` | Modificar |
| 2.9 | `infrastructure/in_memory_episode_store.py` | Modificar |
| 2.10 | Tests: `tests/test_temporal_recall.py` | Crear |
| 2.11 | Tests: `tests/test_temporal_belief_queries.py` | Crear |

### Criterios de aceptación

- [ ] `history_in_range(start, end)` retorna episodios en el rango
- [ ] `history_about("X", since=meses_atras)` retorna episodios sobre X en ese período
- [ ] `recall(query, since=..., until=...)` filtra por tiempo
- [ ] `RecalledMemory` lleva `observed_at`
- [ ] Consultas temporales funcionan en SQLite, JSON, e in-memory
- [ ] Todos los tests existentes siguen pasando

---

## Fase 3: Knowledge Graph Ligero (P1)

**Objetivo:** Modelar entidades y relaciones para razonamiento relacional.

**Justificación:** No hay entidades que representen personas, proyectos, conceptos o decisiones
con relaciones explícitas. `CompanionModel` almacena creencias como traits planos. No hay
traversabilidad ni inferencia relacional.

### 3.1 — Modelo de Grafo

**Archivo nuevo:** `src/jarvis/domain/entities/knowledge_node.py`

```python
@dataclass(slots=True, eq=False)
class KnowledgeNode:
    """Un nodo en el grafo de conocimiento: persona, proyecto, concepto, decisión."""
    id: str                          # UUID
    kind: NodeKind                   # PERSON, PROJECT, CONCEPT, DECISION, EVENT
    name: str                        # nombre legible
    description: str | None
    properties: dict[str, str]       # atributos libres
    created_at: datetime
    _evidence: list[Evidence]        # evidencia que soporta la existencia/propiedades
    _pending_events: list[CognitiveEvent]
```

**Archivo nuevo:** `src/jarvis/domain/entities/knowledge_edge.py`

```python
@dataclass(slots=True, eq=False)
class KnowledgeEdge:
    """Una relación entre dos nodos."""
    id: str                          # UUID
    source_id: str                   # nodo origen
    target_id: str                   # nodo destino
    relation: str                    # "works_on", "knows", "decided", "caused", etc.
    weight: Confidence               # fuerza de la relación (derivada)
    created_at: datetime
    _evidence: list[Evidence]
    _pending_events: list[CognitiveEvent]
```

**Archivo nuevo:** `src/jarvis/domain/enums/node_kind.py`

```python
class NodeKind(Enum):
    PERSON = "person"
    PROJECT = "project"
    CONCEPT = "concept"
    DECISION = "decision"
    EVENT = "event"
```

### 3.2 — Repositorio de Grafo

**Protocolo nuevo:** `src/jarvis/domain/repositories/knowledge_graph_repository.py`

```python
class KnowledgeGraphRepository(Protocol):
    # Nodos
    def get_node(self, node_id: str) -> KnowledgeNode | None: ...
    def get_node_by_name(self, name: str, kind: NodeKind | None = None) -> KnowledgeNode | None: ...
    def save_node(self, node: KnowledgeNode) -> None: ...
    def all_nodes(self) -> tuple[KnowledgeNode, ...]: ...

    # Aristas
    def get_edge(self, edge_id: str) -> KnowledgeEdge | None: ...
    def save_edge(self, edge: KnowledgeEdge) -> None: ...
    def edges_from(self, node_id: str) -> tuple[KnowledgeEdge, ...]: ...
    def edges_to(self, node_id: str) -> tuple[KnowledgeEdge, ...]: ...
    def edges_between(self, source_id: str, target_id: str) -> tuple[KnowledgeEdge, ...]: ...

    # Traversal
    def neighbors(
        self, node_id: str, relation: str | None = None, depth: int = 1
    ) -> tuple[KnowledgeNode, ...]: ...
    def path_between(
        self, source_id: str, target_id: str, max_depth: int = 4
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]] | None: ...
```

### 3.3 — Extracción Automática de Entidades

**Archivo nuevo:** `src/jarvis/domain/services/entity_extraction.py`

```python
def extract_entities(
    belief: Belief,
    existing_nodes: tuple[KnowledgeNode, ...],
) -> tuple[tuple[KnowledgeNode, ...], tuple[KnowledgeEdge, ...]]:
    """Extrae entidades y relaciones de una creencia.
    Retorna nodos nuevos y aristas nuevas."""
```

**Algoritmo:**
1. Analizar el `statement` de la creencia y el contenido de su evidencia
2. Detectar nombres propios (heurística: mayúsculas, contexto)
3. Detectar relaciones verbales ("trabaja en", "conoce", "decidió")
4. Emparejar con nodos existentes por nombre
5. Crear nodos nuevos para entidades no reconocidas
6. Crear aristas para relaciones detectadas

### 3.4 — Integración con Ciclo Reflexivo

**Modificar:** Después de `Learn` en el ciclo reflexivo, extraer entidades de la creencia
aprendida y actualizar el grafo.

### 3.5 — Integración con Recuperación

**Modificar:** `memory_candidates.py`

Los vecinos de un nodo relacionado con el query se agregan como candidates.

### 3.6 — Persistencia SQLite

**Archivo nuevo:** `src/jarvis/infrastructure/sqlite_knowledge_graph_store.py`

Tablas:
```sql
CREATE TABLE knowledge_nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    properties TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL      -- serialización completa
);

CREATE TABLE knowledge_edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
    target_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
    relation TEXT NOT NULL,
    weight REAL NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_edges_source ON knowledge_edges(source_id);
CREATE INDEX idx_edges_target ON knowledge_edges(target_id);
CREATE INDEX idx_nodes_name ON knowledge_nodes(name);
```

### Entregables

| # | Archivo | Acción |
|---|---------|--------|
| 3.1 | `domain/entities/knowledge_node.py` | Crear |
| 3.2 | `domain/entities/knowledge_edge.py` | Crear |
| 3.3 | `domain/enums/node_kind.py` | Crear |
| 3.4 | `domain/repositories/knowledge_graph_repository.py` | Crear |
| 3.5 | `domain/services/entity_extraction.py` | Crear |
| 3.6 | `infrastructure/sqlite_knowledge_graph_store.py` | Crear |
| 3.7 | `infrastructure/in_memory_knowledge_graph_store.py` | Crear |
| 3.8 | Tests: `tests/domain/test_knowledge_node.py` | Crear |
| 3.9 | Tests: `tests/domain/test_knowledge_edge.py` | Crear |
| 3.10 | Tests: `tests/domain/test_entity_extraction.py` | Crear |
| 3.11 | Tests: `tests/infrastructure/test_knowledge_graph_store.py` | Crear |

### Criterios de aceptación

- [ ] Nodos y aristas se crean, persisten y recuperan
- [ `neighbors(node_id)` retorna vecinos a profundidad N
- [ ] `path_between(a, b)` encuentra caminos
- [ ] Extracción automática detecta entidades en creencias
- [ ] El grafo se actualiza durante el ciclo reflexivo
- [ ] La recuperación usa el grafo para enriquecer resultados

---

## Fase 4: Memoria de Conversación Persistente (P1)

**Objetivo:** Preservar el historial de conversación entre sesiones.

**Justificación:** `ConversationContext` y `ReasoningSpan` se pierden en reinicios. El sistema
no puede responder "¿de qué hablamos la última vez?" ni mantener contexto multi-turno
después de un reinicio.

### 4.1 — Modelo de Turn Persistido

**Archivo nuevo:** `src/jarvis/domain/value_objects/persisted_turn.py`

```python
@dataclass(frozen=True, slots=True)
class PersistedTurn:
    """Un turno de conversación persistido."""
    speaker: str              # "companion" | "jarvis"
    text: str
    timestamp: datetime
    intent: ConversationIntent | None
    turn_id: str              # UUID
```

### 4.2 — Repositorio de Conversación

**Protocolo nuevo:** `src/jarvis/domain/repositories/conversation_repository.py`

```python
class ConversationRepository(Protocol):
    def record_turn(self, turn: PersistedTurn) -> None: ...
    def recent_turns(self, limit: int = 20) -> tuple[PersistedTurn, ...]: ...
    def turns_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[PersistedTurn, ...]: ...
    def turns_about(
        self, subject: str, limit: int = 10
    ) -> tuple[PersistedTurn, ...]: ...
```

### 4.3 — Integración con ConversationContext

**Modificar:** `ConversationContext.record()` también persiste al repositorio.

### 4.4 — Integración con MemoryRetriever

**Modificar:** `memory_candidates.py`

Turnos de conversación pasados se agregan como candidates con `MemoryKind.CONVERSATION`.

### 4.5 — Persistencia SQLite

**Archivo nuevo:** `src/jarvis/infrastructure/sqlite_conversation_store.py`

```sql
CREATE TABLE conversation_turns (
    turn_id TEXT PRIMARY KEY,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    intent TEXT,
    payload TEXT NOT NULL
);

CREATE INDEX idx_turns_timestamp ON conversation_turns(timestamp);
```

### Entregables

| # | Archivo | Acción |
|---|---------|--------|
| 4.1 | `domain/value_objects/persisted_turn.py` | Crear |
| 4.2 | `domain/repositories/conversation_repository.py` | Crear |
| 4.3 | `infrastructure/sqlite_conversation_store.py` | Crear |
| 4.4 | `infrastructure/in_memory_conversation_store.py` | Crear |
| 4.5 | Integración con `ConversationContext` | Modificar |
| 4.6 | Integración con `memory_candidates.py` | Modificar |
| 4.7 | Tests: `tests/test_persisted_conversation.py` | Crear |

---

## Fase 5: Reflexión de Segundo Orden (P2)

**Objetivo:** Notar patrones en cómo se conoce, no solo en qué se conoce.

**Justificación:** El ciclo reflexivo actual es de primer orden: detecta evidencia compartida
entre creencias. No notael sistema sobre sus propias estrategias cognitivas, no adapta su
propia forma de razonar, y no crea reglas generales a partir de experiencias específicas.

### 5.1 — Meta-Observación Cognitiva

**Archivo nuevo:** `src/jarvis/domain/services/meta_observation.py`

```python
def observe_reasoning_effectiveness(
    episodes: list[EpisodeRecord],
    beliefs: list[Belief],
) -> MetaObservation | None:
    """Observa qué estrategias de razonamiento produjeron conclusiones mejor fundamentadas.
    Retorna una observación si hay suficiente historial."""

def observe_retrieval_quality(
    episodes: list[EpisodeRecord],
    recalled: list[RecalledMemory],
) -> MetaObservation | None:
    """Observa si la recuperación de memoria está siendo relevante o ruidosa."""

def observe_attention_allocation(
    episodes: list[EpisodeRecord],
) -> MetaObservation | None:
    """Observa si la asignación de atención (FULL/BRIEF) es apropiada."""
```

### 5.2 — Modelo de Meta-Conocimiento

**Archivo nuevo:** `src/jarvis/domain/entities/meta_knowledge.py`

```python
@dataclass(slots=True, eq=False)
class MetaKnowledge:
    """Conocimiento sobre el propio proceso cognitivo."""
    id: str
    kind: MetaKnowledgeKind       # REASONING_STRATEGY, RETRIEVAL_QUALITY, ATTENTION_PATTERN
    statement: str                # "Mis conclusiones son mejores cuando..."
    confidence: Confidence        # derivada
    evidence: list[Evidence]
    formed_at: datetime
```

### 5.3 — Integración con Self-Observation

**Modificar:** `self_observation.py`

Agregar observers adicionales:
- `observe_reasoning_effectiveness()`
- `observe_retrieval_quality()`
- `observe_attention_allocation()`

### 5.4 — Integración con Curiosidad

**Modificar:** El sistema de curiosidad también considera meta-conocimiento como fuente
de impulsos: "no sé qué estrategia de razonamiento funciona mejor para X".

### Entregables

| # | Archivo | Acción |
|---|---------|--------|
| 5.1 | `domain/services/meta_observation.py` | Crear |
| 5.2 | `domain/entities/meta_knowledge.py` | Crear |
| 5.3 | `domain/enums/meta_knowledge_kind.py` | Crear |
| 5.4 | Integración con `self_observation.py` | Modificar |
| 5.5 | Integración con curiosidad | Modificar |
| 5.6 | Tests: `tests/domain/test_meta_observation.py` | Crear |

---

## Resumen de Prioridades

```
FASE 0  ─── Deuda Crítica (God Object Split)          ~2-3 días
  │
  ├── FASE 1  ── Memoria Semántica (P0)                ~3-4 días
  │     │
  │     └── FASE 2  ── Razonamiento Temporal (P0)      ~2-3 días
  │
  ├── FASE 3  ── Knowledge Graph Ligero (P1)           ~4-5 días
  │
  ├── FASE 4  ── Conversación Persistente (P1)         ~2-3 días
  │
  └── FASE 5  ── Reflexión Segundo Orden (P2)          ~3-4 días
```

**Total estimado:** 16-22 días de desarrollo incremental.

**Orden recomendado:** 0 → 1 → 2 → 3 → 4 → 5

**Cada fase es independiente** y puede completarse y validarse antes de pasar a la siguiente.
Las fases 1 y 2 son P0 (fundamentales). Las fases 3 y 4 son P1 (importantes). La fase 5 es
P2 (valiosa).

---

## Protecciones Arquitectónicas

Las siguientes decisiones de la auditoría deben preservarse en CADA fase:

1. **La confianza NUNCA se settea imperativamente** — siempre se deriva de evidencia
2. **Las contradicciones son eventos de primer nivel** — no se borran, no se ignoran
3. **La estabilidad temporal es un eje independiente** de la confianza
4. **Las memorias semánticas heredan la misma invariante** que las creencias
5. **El LLM propone, Jarvis decide** — el LLM nunca modifica el estado cognitivo directamente
6. **Inyección de dependencias en todas partes** — `Jarvis()` sigue siendo offline y determinista
7. **Los seams son Protocolos** — cualquier implementación es reemplazable
8. **Los tests verifican comportamiento cognitivo**, no operaciones CRUD
9. **El grafo de conocimiento es opcional** — sin wiring, el sistema funciona sin él
10. **La persistencia serializa evidencia, re-deriva confianza** — "memoria no es verdad"

---

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| God Object split rompe tests existentes | Extraer módulos uno a uno, ejecutar tests después de cada extracción |
| Memoria semántica genera patrones falsos | `min_sources=3` como mínimo; confianza derivada; revisión manual posible |
| Knowledge graph crece sin control | Límite de nodos; pods born con evidencia; pods sin evidencia se decaen |
| Persistencia de conversación crece mucho | Límite de turnos persistidos (últimos N días); archivado automático |
| Meta-observación crea bucles infinitos | Límite de meta-conocimiento; umbral de confianza para actionabilidad |
| Complejidad del grafo afecta rendimiento | Índices SQLite; traversal limitado a profundidad 4; cache de vecinos |

---

## Criterios de Validación Global

Después de CADA fase, verificar:

```bash
python -m pytest -q          # todos los tests pasan
python -m ruff check .       # lint limpio
python -m pyright            # type check strict, 0 errores
```

Después de la Fase 5 (todas las fases completas):

```bash
python -m pytest -q --tb=short    # suite completa
python -m ruff check .            # lint
python -m pyright                 # strict, 0 errores
```

Y verificar manualmente:

- [ ] `Jarvis()` sigue siendo offline y determinista
- [ ] `Jarvis.persistent()` y `Jarvis.database()` sobreviven reinicios
- [ ] La confianza siempre se deriva (no hay setters)
- [ ] Las contradicciones son eventos de primer nivel
- [ ] El LLM nunca modifica estado cognitivo directamente
- [ ] El grafo de conocimiento es opcional (sin wiring, funciona)
- [ ] La memoria semántica aparece en recuperación
- [ ] Las consultas temporales funcionan
- [ ] La conversación persiste entre sesiones
- [ ] La meta-observación alimenta curiosidad
