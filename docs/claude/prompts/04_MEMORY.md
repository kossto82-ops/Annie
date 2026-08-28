# JARVIS — MEMORY SYSTEM

Quiero implementar/evolucionar el sistema de memoria de Jarvis.

## Principio fundamental

Jarvis no debe tratar la memoria como una simple colección de documentos.

La visión epistemológica es:

Experience → Observation → Interpretation → Belief → Confidence → Evidence → Possible revision

Una memoria puede representar:
- experiencias
- hechos observados
- preferencias
- decisiones
- objetivos
- relaciones
- conocimientos
- creencias
- contradicciones
- incertidumbre

## Debe distinguir

### Observation
Lo que ocurrió o fue dicho.

### Belief
Lo que Jarvis considera provisionalmente verdadero.

### Evidence
Qué respalda una creencia.

### Confidence
Grado de confianza.

### Source
De dónde procede.

### Temporal information
Cuándo era válida.

## Actualización

Si nueva evidencia contradice una creencia, NO sobrescribas silenciosamente.

Debe ocurrir:
Old belief → contradictory evidence → re-evaluation → updated belief

Conserva suficiente historial para entender por qué cambió.

## Retrieval

Recupera lo que sea:
- relevant
- recent
- important
- high-confidence
- contextually useful

Evita inundar el contexto.

## Context

Separa:
Long-term memory → retrieval → working context → LLM

No introduzcas toda la memoria en cada prompt.

## Privacidad

No guardes automáticamente cualquier contenido como memoria permanente.

Debe existir criterio para:
- remember
- don't remember
- temporary
- uncertain
- sensitive

## Tests

Demuestra:
1. guardar
2. recuperar
3. relevancia
4. actualización
5. contradicción
6. confidence
7. temporalidad
8. no recuperación de información irrelevante

Antes de implementar, inspecciona el sistema actual y propón cómo evolucionarlo sin romperlo.
