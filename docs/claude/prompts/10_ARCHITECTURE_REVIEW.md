# JARVIS — ARCHITECTURE REVIEW

Antes de continuar con nuevas funcionalidades, realiza una revisión de la implementación actual.

NO añadas nuevas features.

## Architecture

- ¿Sigue la arquitectura de Jarvis?
- ¿Existe acoplamiento innecesario?
- ¿Hay responsabilidades mezcladas?
- ¿Se han creado abstracciones prematuras?

## Cognitive integrity

- ¿La funcionalidad aporta una capacidad cognitiva real?
- ¿O simplemente añade otra llamada al LLM?

## Memory

- ¿Se almacena correctamente?
- ¿Se crean recuerdos innecesarios?
- ¿Se distinguen observations, beliefs y evidence?

## Context

- ¿Se envía contexto innecesario?
- ¿Hay duplicación?
- ¿Hay problemas de token usage?

## Models

- ¿Jarvis sigue siendo provider-agnostic?
- ¿Está correctamente desacoplado de OmniRoute?
- ¿Podemos cambiar de proveedor sin modificar Jarvis?

## Tools

- ¿Existen permisos adecuados?
- ¿Se registran acciones?
- ¿Hay riesgos?

## Tests

- ¿La nueva capacidad está cubierta?
- ¿Existen tests de integración?

## Technical debt

Clasifica:
- Critical
- High
- Medium
- Low

No arregles automáticamente todo. Presenta resultados y recomienda qué merece atención.
