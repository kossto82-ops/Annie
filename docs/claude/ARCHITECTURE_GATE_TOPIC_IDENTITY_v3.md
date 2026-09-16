# ARCHITECTURE GATE — TOPIC IDENTITY v3

**Date:** 2026-09-15
**Scope:** Read-only architectural decision — no code, no tests, no repo modifications
**Question:** Should a Topic's identity persist across the Attention Window, and how?

---

## Executive Verdict

La hipótesis preferente se sostiene **con una corrección importante**: Jarvis debe tener identidad de tópico **histórica** (derivada de toda la historia externa, anclada cronológicamente, inmutable bajo acréscimo) y atención **temporal en ventana** (las señales count/unresolved/revised/recency sobre las últimas 50 externas). La falsificación parcial exitosa es esta: la versión fuerte "A→B y B→A producen la MISMA identidad" es **inalcanzable e indeseable** bajo el modelo actual de anclaje por fundador — y perseguirla obligaría a canónicas como "intersección del conjunto de miembros", que **mutan la identidad bajo acréscimo** (un miembro más estrecho renombraría el tópico), rompiendo la estabilidad nominal que ya el §10 exige. Lo correcto es **estabilidad de crónica** (invarianza bajo evicción/acréscimo, monotone anchor) y NO invarianza de permutación. Con esa matización, "identidad histórica + atención en ventana + sin BD de tópicos" es coherente, mínimo y verificable — no encontré contradicción que lo rompa (§28: la hipótesis zafa; solo se afila).

## Decision

```
B — MODIFY
```

El modelo actual (Modelo A: tópicos locales-a-la-ventana) tiene *un* defecto CRITICAL y *un* defecto HIGH, ambos reproducidos en vivo y ambos corregibles dentro de `topic_resolution.py` + `attention_priority.py`, sin nuevas abstracciones, sin persistencia de tópicos, sin cambios de esquema. No es un rediseño (C): "tópico = firma conceptual con anclaje cronológico y preservación de ambigüedad" es el concepto correcto; lo equivocado es que la ventana de atención defina simultáneamente *qué es un tópico* y *qué tan saliente es*.

## What a Topic Means

> Un **Topic** es una familia derivada, anclada cronológicamente, de episodios **externos** cuyas firmas canónicas de conceptos son *nested-compatible* (comparten ≥ 2 conceptos y una contiene a la otra), **identificada por una firma canónica inmutable** — la firma del episodio fundador dentro de la crónica inalterable — que **no depende de la confianza, de las creencias, de los scores de atención ni de la ventana temporal**, y que arrastra proveniencia derivada (ids de episodios miembros, triggers, conteo externo histórico).

## What a Topic Is NOT

- **No es una Belief**: no es una aserción de verdad; "supplier failed / succeeded / failed to deliver" es el mismo tópico (la firma ignora polaridad y negación: `"did not fail"` y `"failed"` comparten firma — herejía correcta para *aboutness*, la contradicción vive en la evidencia, no en la identidad).
- **No es un SemanticMemory**: la memoria semántica es un almacén persistido de patrones *acerca del* tópico (evidence-derived); la identidad es derivación read-only sobre episodios.
- **No es un AttentionPriority**: la prioridad es un número `[0,1]` ventaneado que puede ir 0.9→0.1 sin tocar la identidad.
- **No es el `representative_trigger`** (display/re-engagement únicamente).
- **No es un registro de BD**: ni tabla, ni índice autoritativo, ni campo con autoridad epistémica.
- **No es una categoría/etiqueta** elegida por alguien.

## Current Model

```
episodes.history() (todo origen)
   │ head[-50:]
   ▼
records = [r for r in head[-50:] if origin is COMPANION]   ← ventana define el universo
   ▼
resolve_episodes(records, window=50)                        ← IDENTIDAD local-ventana
   • bootstrap = primer episodio en la ventana; canónica = firma del bootstrap
   • absorción SOLO si canonical ⊆ nueva_firma   (una sola dirección)
   • ≥2 candidatos compatibles → tópico NUEVO (regla de ambigüedad)
   ▼
por tópico (solo miembros de la ventana): count/unresolved/revised/recency → score
   ▼
ordenar → top → wake() si ≥ 0.40 → impulse(target_topic_id=top.topic, representative=última trigger)
   ▼
pursue → CognitiveEpisode(origin=CURIOSITY, target_topic_id) → EpisodeRecord
```

**Reconstrucción (§4, desde el código real):**
1. **Qué crea un tópico:** la firma conceptual de un episodio externo que no es compatible con ningún tópico existente *dentro de la ventana* (topic_resolution.py:112-128).
2. **Qué lo identifica:** `canonical_signature` = firma del episodio que lo fundó en la ventana; `topic_id` = firma ordenada unida `"DELIVER > FAIL"` (o el trigger crudo si la firma es vacía).
3. **Qué lo destruye:** nada explícito — *se evapora* cuando su episodio fundador sale de los últimos 50 externos (resolución recomputada desde cero por lectura).
4. **¿Puede cambiar de identidad?** Sí — por evicción (probe: `[A,B,C]`→1 tópico `DELIVER > FAIL`; `[B,C]`→2 tópicos; el miembro C deja de pertenecer a la familia) y por desplazamiento de bootstrap.
5. **¿Pueden fusionarse dos tópicos?** Sí, por absorción unidireccional cuando llega una firma que contiene la canónica (genérico→detalle fusiona; detalle→genérico NO).
6. **¿Puede escindirse?** Sí — el caso (5) inverso: una repetición genérica del mismo asunto funda un segundo tópico (probe narrowing: 2 tópicos).
7. **¿Identidad persistida?** No. Solo episodios (P1). `target_topic_id` se escribe SOLO en episodios CURIOSITY (json_episode_store.py:47, sqlite: payload) y **nunca se lee** por resolución/atención — provenance display.
8. **¿Identidad derivada?** Sí — pura, por lectura, determinista por snapshot.
9. **Información histórica requerida:** solo los triggers (firmas) + origen de los últimos-50-externos, en orden de llegada.
10. **¿Afecta la ventana a la identidad?** Sí — define el universo y el bootstrap (§7: la respuesta actual al experimento es "SÍ cambia", la requerida es "NO").
11. **¿La ventana afecta solo señales?** No — hoy afecta identidad Y señales (conflación).
12. **¿Puede la cognición auto-generada crear/alterar tópicos?** No puede *fundar recurrencia externa*: filtro `origin is COMPANION` en los tres puntos (attention_priority.py:80, abstraction.py:372). Un episodio CURIOSITY sí aparece en `history()`, pero jamás en resolución/abstracción/atención. (Verificado: 5× wake→pursue → ranking byte-idéntico.)

    *Excepción honesta:* el episodio CURIOSITY **sí crea/altera la Belief** (herramienta legítima — sabe sobre sí mismo), pero eso es memoria/belief, no tópico.
13. **¿Puede la revisión de creencia alterar la identidad?** No — la firma ignora confianza/polaridad; `belief_confidence_at_end` solo alimenta la señal `revised` (attention_priority.py:104-106), nunca la identidad.

## Proposed Model

```
EPISODE HISTORY  (crónica append-only e inmutable, persistida P1)
   │  [solo COMPANION]
   ▼
HISTORICAL TOPIC RESOLUTION  (un pase sobre TODA la historia externa; derivación pura)
   • bootstrap = primer episodio cronológico de la familia → canónica ANCLA (inmutable)
   • absorción SIMÉTRICA: |S∩T| ≥ 2  AND  (S ⊆ T  OR  T ⊆ S)
   • regla de ambigüedad conservada: ≥2 candidatos compatibles → tópico propio
      ├── STABLE TOPIC ID        (canónica bootstrap; nunca cambia bajo acréscimo)
      └── PROVENANCE             (source_episode_ids, triggers, external_count histórico)
   │
   ▼
RECENT EXTERNAL EPISODES  head[-50:] COMPANION      ← ventana SOLO para señales
   │   episode_id → topic_id vía mapa histórico
   ▼
ATTENTION SIGNALS  count/unresolved/revised/recency (sobre la ventana) → score saturante
   ▼
ATTENTION PRIORITY → top → wake() si ≥ 0.40
   │
   ▼
CURIOSITY → pursue → CognitiveEpisode(origin=CURIOSITY, target_topic_id=id HISTÓRICO)
   │
   └──────────────X  NUNCA cuenta como recurrencia externa (filtro COMPANION)
```

## Order Test

Firmas verificadas: A=`supplier failed to deliver`={FAIL,DELIVER}; B=`vendor missed the delivery deadline`={FAIL,DELIVER,TIME}.

| Orden | Hoy | Bajo el cambio |
|---|---|---|
| A→B | 1 tópico `DELIVER > FAIL` | 1 tópico, id igual |
| B→A | **2 tópicos** (asimetría) | 1 tópico, mismo miembro; **id = `DELIVER > FAIL > TIME`** |

**P1 — ¿Deben dar la misma identidad?** *Membresía:* sí, deben dar el mismo tópico (sujeto compartido). *Identidad nominal:* no necesariamente — el ancla es el primer episodio de la crónica, un dato histórico. A→B y B→A son **crónicas distintas**; que el nombre del tópico sea el que se mencionó primero es honesto y nunca se muestra como autoridad.

**P2 — Mecanismo mínimo:** compatibilidad **simétrica** (`S⊆T OR T⊆S` en vez de `S⊇T`). Solo eso.

**P3 — ¿Sin LLM/embeddings/vector-BD/segunda-BD/ids mutables/reescritura?** **Sí.** La firma es un mapa determinista ya existente; la regla es un predicado local de conjuntos; la identidad es una función pura de la crónica inmutable ya persistida. El único "costo" es aceptar que [A,B] y [B,A] difieren en el ancla nominal — una decisión documentada, no un defecto.

## Eviction Test

`A={FAIL,DELIVER}`, `B={FAIL,DELIVER,TIME}`, `C={FAIL,DELIVER}` (misma familia):

| Ventana | Hoy | Bajo el cambio |
|---|---|---|
| [A,B,C] | 1 tópico `DELIVER > FAIL` | 1 tópico `DELIVER > FAIL` |
| [B,C] | **2 tópicos** (B nuliterna/re-funda separado) | **1 tópico** `DELIVER > FAIL` (ancla histórica, B sigue siendo miembro) |
| [C] | 1 tópico `DELIVER > FAIL` (por suerte) | **1 tópico** `DELIVER > FAIL` |

**Respuesta a §7:** NO, C no debe cambiar de identidad por la evicción de A/B — y bajo el modelo propuesto no cambia: la identidad es función de la historia completa, no de la ventana; solo cambian las **señales** (recurrencia 3→2→1, recency) — que es exactamente lo que "atención temporal" debe hacer. Separación identidad/atención materializada.

## Window vs History

| Operación | Dominio | Por qué |
|---|---|---|
| Resolución de tópicos (identidad, membresía, proveniencia) | **Historia completa externa** | La pregunta "¿estas experiencias son del mismo asunto?" exige todo el testigo disponible; la evicción no debe borrar la identidad (§7). |
| `external_count` / provenance | Historia completa | Histórico. |
| Señales de atención (count, unresolved, revised, recency) y score | **Últimas 50 externas** | "¿a qué atender ahora?" es temporal por definición (Vision §16); acotado por construcción, sin inflación sin límite. |
| `wake()` gate (`≥ 0.40`) y `representative` | Ventana (para display/re-engagement) | `representative` = metadata de re-enganche (§15). |

## Ambiguity Test

X={FAIL,DELIVER}, Y={TIME,COST}, candidato S={FAIL,DELIVER,TIME,COST} (compatible con ambos). Hoy (probe con firmas correctas): **X,Y→S y S→X,Y dan 3 tópicos** — los dos órdenes.

Bajo el cambio, **S→X,Y → 1 tópico** (S funda; los estrechos se absorben por regla simétrica) mientras **X,Y→S sigue siendo 3 tópicos** (S compatible con 2 → su propio tópico; no colapsa X/Y).

**Decisión epistemológica intencional:** una síntesis que llega DESPUÉS de sus fragmentos es un tópico nuevo (no colapsar hipótesis prematuramente — §14, D-cultura); una síntesis que llega PRIMERO forma la familia que luego se detalla. La estructura es honestamente dependiente de la secuencia de llegada de síntesis ambiguas; eso **permanece** y se documenta (es parte de lo que la regla de ambigüedad protege: jamás `FAIL` solo une dimensiones — verificado: {F,D},{F,C},{F,R} quedan separados).

## Self-Reinforcement Test

Invariante intacta en los tres puntos y en ambos modelos: `derive_attention_priorities` filtra `origin is COMPANION` (**antes** de resolver y **antes** de señales), `abstract_patterns` filtra COMPANION, y el episodio pursued (CURIOSITY) **existe en la crónica pero no en la resolución** — no funda tópico nuevo, no crea recurrencia, no altera proveniencia externa, no infla conteos. Empírico: 5 iteraciones wake→pursue → `before == after` byte-idéntico (iteration 1-5: `('FAIL', 0.80, 5)`). El único efecto de un pursuit es sobre Belief/evidencia (legítimo) y sobre la evicción de la ventana (los episodios CURIOSITY desplazan externas viejas del horizonte — benigno, documentado).

## Persistence Decision

```
P1
```

Episodios persistidos = fuente de verdad; tópicos derivados por lectura; atención derivada de tópicos + ventana. Justificación: (a) determinismo y equivalencia de replays garantizados porque ambos stores son **append-ordered** (JSON append secuencial; SQLite `seq AUTOINCREMENT` — verificado en ambos stores); (b) cero migración de datos; (c) el cache incremental futuro (categoría C, §9) puede materializarse SIN cambiar el modelo epistémico (misma función pura, verificable por recomputacion). P2 rechazado hoy: añade consistencia/mantenimiento por un beneficio que no existe a la escala actual (~10^3).

## Scalability

Razonamiento por recomputación pura en cada lectura de atención (O(N·T)):

| Escala | Costo estimado por wake/attention | Verdict |
|---|---|---|
| 1K | ~10^5–10^6 ops | Trivial (on-demand, no por-reply) |
| 10K | ~10^7–10^8 ops | Aceptable |
| 100K | ~10^9–10^10 ops | **Umbral del cache** (~5·10^4 externas): materialización incremental en `_remember`, O(T) por append |
| 1M | infeasible sin cache | Cache obligatorio; accesos O(50 + T) |

**Camino evolutivo limpio (§21/§22, sin optimización prematura):** la resolución histórica es una función pura de una crónica **append-only**, y la membresía es **monótona** (los miembros solo se unen). Un índice derivado (category C) — `episode_id → topic_id` + registros de tópico — se actualiza en O(T) por append, se re-playa idéntico, y es **descartable** (consistencia por recomputación en tests). Mejoras de rendimiento SIN tocar el modelo epistémico. `target_topic_id` (ya persistido) podría servir de ficha del índice si se materializa — pero **nunca como autoridad**.

## Critical Findings

1. **CRITICAL — Conflación identidad/ventana en `attention_priority.py:80-84`.** La identidad se computa SOLO sobre las últimas-50-externas; la evicción cambia la canónica de una familia ([A,B,C]→`DELIVER > FAIL` vs [B,C]→2 tópicos, probe). §7 pedía "NO"; la implementación responde "SÍ, y además desfragmenta el asunto". Root: `resolve_episodes` recibe la ventana ya recortada.
2. **HIGH — Absorción unidireccional en `topic_resolution.py:87` (`canonical ⊆ signature`).** Un asunto mencionado primero en detalle y luego reafirmado de forma genérica **se parte en 2 tópicos** (probe narrowing: detalle→genérico 2 tópicos; genérico→detalle 1). Es el caso de producción real (la gente primero detalla, luego resume), y es la causa de que S={F,D,T,C} nunca pueda absorber a {F,D} ni {T,C} aunque sean el mismo asunto (la "ambigüedad" S primeros 3 tópicos es en realidad esto). Fix: `(S⊆T or T⊆S)`.
3. **MEDIUM — La invarianza de permutación pura es inalcanzable sin canónicas mutantes — no perseguirla.** A→B y B→A difieren en el id nominal (anchor bootstrap). "Arreglarlo" con intersección-de-miembros renombra tópicos al crecer (narrowing: {F,D,T}→{F,D}), chocando con §10 y con la continuidad nominal del compañero. Decisión documentada: estabilidad de **crónica** (ventana-invariante, monotone anchor), no de conjunto-permutación.
4. **MEDIUM — La regla de ambigüedad es, por diseño, sensible a la secuencia de llegada de síntesis** (S-last→3 tópicos, S-first→1 tópico bajo el fix). Epistemológicamente correcta (§14: no colapsar), pero debe **atestiguarse con tests** en ambas direcciones antes de tocar código.
5. **LOW — Coste O(N·T) por lectura a escala; migrar a cache incremental ~5·10^4 externas** (findings §8). Actualmente intrascendente (N ≈ cientos).
6. **INFO — `resolve_episodes`'s `window=50` como "safety bound" queda obsoleta** para identidad bajo el Modelo B; la ventana pasa a ser solo material de señales.
7. **INFO — Ningún test actual pilla los casos OrderReverse, Narrowing, Eviction o S-first.** Los 118 tests de `tests/semantic_attention` son honestos pero validan la regla unidireccional actual (p.ej. `test_single_concept_topics_never_merge`, `test_ambigous_signature_starts_a_new_topic`) — sobrevivirán o deberán re-leerse según el fix, y 3-4 tests nuevos deben pin el nuevo invariante (ver Minimum Change).

## Minimum Change

```text
Problem          : identidad frágil ante evicción y ante orden de mención (finding 1+2).
Current behavior : tópicos = función de la ventana (50) y de una absorción de una sola dirección.
Why insufficient : viola §7 ("C no cambia de identidad por evicción") y §12 (la dirección no debe poder partir un asunto).
Desired invariant: La identidad de un tópico es una función pura de TODA la historia externa
                   (ancla bootstrap cronológica, inmutable bajo acréscimo); la ventana solo
                   modula señales de atención.
Minimal change   :
  • topic_resolution._compatible  → simétrica: |S∩T| ≥ 2 AND (S ⊆ T OR T ⊆ S)  [mantener
    bootstrap-canonical + regla de ambigüedad + bootstrap-raw-trigger para firmas vacías]
  • attention_priority.derive_attention_priorities → resolver sobre TODAS las externas
    (mapa episode_id→topic_id), computar count/unresolved/revised/recency sobre head[-50:] COMPANION
    con ese mapa.
Data flow after  : history → [histórico] topic map → [ventana] señales → score → wake → impulse.
What remains derived : topic identity (read-only), attention signals, score.
What remains persisted: episodes (P1), provenance en episodios; target_topic_id como provenance.
What must never be authoritative : target_topic_id, cualquier cache de tópicos materializado,
                                   representative, external_count histórico.
Tests required  : order-reverse ([A,B] y [B,A] → 1 tópico); narrowing (§12 detalle→genérico → 1
                   tópico, ancla primero); broadening (§11 [F,D]→[F,D,T]→[F,D,T,C] → canónica {F,D});
                   eviction ([A,B,C]→[B,C]→[C] → misma identidad, señales caen); ambigüedad x2 direcciones
                   (S-last 3, S-first 1); no-pollution ({F,D},{F,C},{F,R}); self-reinforcement (mantener
                   before==after); restart JSON+SQLite idéntico; cache-consistency recompute si se materializa.
Migration impact: NINGUNO. Sin cambio de esquema, sin migración de datos; re-derivación en la próxima
                   lectura con la nueva regla (determinista).
```

**Requerido por el cambio:** **ninguno nuevo** — `no new file`, `no new value object`, `no new persisted field`, `no new store`, `no new index`. Solo las dos funciones existentes mencionadas + tests + docstrings (y los docstrings de "bounded attention" se re-redactan porque ahora acotan atención, no identidad).

## What We Must NOT Change

- El mapa de conceptos (`CONCEPT_MAP`/D15) — la semántica sigue acotada y determinista.
- `ATTEND_THRESHOLD` (0.40) y los pesos de señales — el problema es la identidad, no el umbral.
- La cascada `feel_curious()` — sigue estática; `wake()` es la superficie paralela ránkeada.
- `belief.py` / `evidence.py` / `derive_confidence` / neutral-evidence — invariante epistémica intacta.
- Los stores de episodios (esquema JSON/SQLite) y el `origin` en los tres filtros.
- **Nada de LLM / embeddings / vector search / fuzzy scoring / BD externa / clasificadores probabilísticos** (§23).
- Que `target_topic_id` se vuelva autoritativo — vetado (§9 cat. A).

## Final Architectural Statement

**YES** — Jarvis puede tener tópicos cognitivos históricos estables mientras mantiene la atención ventaneada, determinista, restart-safe e inmune a recurrencia auto-generada **sin** una segunda BD de tópicos autoritativa, porque (i) la identidad es una función pura de una crónica externa append-only e inmutable ya persistida (P1), (ii) la ventana modula solo señales, (iii) los episodios CURIOSITY son excluidos en cada resolución/abstracción/atención por el filtro `origin`, y (iv) cualquier indexación derivada futura es recomputable-idéntica y descartable (categoría C), nunca fuente de verdad.

*(Gate read-only: sin modificaciones de repo, sin código, sin commits.)*
