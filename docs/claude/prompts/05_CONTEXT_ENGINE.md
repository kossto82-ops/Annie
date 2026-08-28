# JARVIS — CONTEXT ENGINE

Quiero construir el sistema de contexto de Jarvis.

Objetivo:
> the right context, at the right time, in the right amount.

## Pipeline

User input
→ Intent/topic analysis
→ Current conversation state
→ Relevant memory retrieval
→ Relevant beliefs
→ Current goals/tasks
→ Context assembly
→ LLM

## Context layers

Distingue:
1. immediate conversation
2. working memory
3. relevant long-term memory
4. beliefs
5. goals
6. current task state
7. system constraints

No mezcles todo en un único prompt gigante.

## Relevancia

El sistema debe poder explicar internamente:
`Why was this memory retrieved?`

Debe ser observable/debuggable.

## Token efficiency

Optimiza:
- relevancia
- tamaño
- redundancia
- freshness
- importance

No asumas que más contexto es mejor.

## Tests

Crea escenarios con:
- memoria relevante
- memoria irrelevante
- información contradictoria
- información antigua
- información reciente

Comprueba que el contexto resultante sea razonable.

Primero audita la arquitectura existente y después implementa incrementalmente.
