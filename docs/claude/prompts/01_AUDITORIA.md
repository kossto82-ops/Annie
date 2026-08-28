# JARVIS — AUDITORÍA ARQUITECTÓNICA COMPLETA

Quiero que audites el estado actual de Jarvis antes de implementar nuevas capacidades.

## Contexto

Jarvis es un proyecto personal de largo plazo concebido como un:
> Long-term cognitive companion / second brain.

La visión es que Jarvis pueda progresivamente:
- comprender
- recordar
- razonar
- construir y actualizar creencias
- mantener contexto
- planificar
- utilizar herramientas
- aprender de las interacciones
- reflexionar
- desarrollar una personalidad coherente
- actuar con distintos niveles de autonomía

La arquitectura debe ser durable y evitar depender de un proveedor concreto de modelos.

## Principio epistemológico

> Jarvis does not simply store information. Jarvis constructs beliefs.

Las creencias son provisionales y deben poder actualizarse cuando aparece nueva evidencia.

## REGLA PRINCIPAL

NO MODIFIQUES NINGÚN ARCHIVO.

Esta fase es exclusivamente de análisis.

## 1. Lee el proyecto

Empieza leyendo:
- `CLAUDE.md`
- documentación de `/docs`
- arquitectura
- decisiones
- contexto
- epistemología
- código fuente
- tests
- configuración

Identifica qué documentación es normativa y cuál parece obsoleta.

## 2. Mapea la arquitectura real

No describas lo que la documentación dice que existe. Quiero saber lo que realmente existe en el código.

Identifica:
- entry points
- core
- memory
- reasoning
- reflection
- comprehension
- executive
- planner
- orchestrator
- attention
- state
- social
- personality
- communication
- trust
- tools
- LLM/model layer
- persistence
- configuration
- API/UI
- tests

Para cada componente indica:
`EXISTS / PARTIAL / STUB / UNUSED / BROKEN / MISSING`

## 3. Traza una interacción completa

Sigue el recorrido real:
User input → application → comprehension → context → memory → reasoning → LLM → tools → response → persistence.

Indica qué ocurre realmente en cada etapa.

## 4. Memory audit

Determina:
- qué se almacena
- dónde
- cómo se recupera
- cómo se decide qué recordar
- cómo se decide qué recuperar
- memoria episódica
- memoria semántica
- memoria de trabajo
- contexto de usuario
- beliefs
- confidence
- actualización de beliefs
- forgetting
- contradiction handling

No asumas que existe porque haya una clase llamada `Memory`.

## 5. Reasoning audit

Determina si Jarvis:
- razona
- planifica
- divide problemas
- verifica resultados
- revisa respuestas
- detecta incertidumbre
- reconsidera decisiones

Distingue entre generación de texto del LLM y arquitectura real de reasoning.

## 6. Agent / tools audit

Determina exactamente qué puede hacer Jarvis fuera de generar texto.

Lista herramientas, filesystem, shell, web, git, APIs, MCP, etc.

Para cada herramienta indica:
- existe
- funciona
- permisos
- riesgos
- confirmación requerida
- reversible/no reversible

## 7. Model layer audit

Analiza cómo Jarvis utiliza modelos.

Determina si está acoplado a algún proveedor concreto y si puede evolucionar hacia:

Jarvis → LLM abstraction → OmniRoute → provider/model

## 8. Test audit

Analiza:
- cobertura aproximada
- componentes sin tests
- tests débiles
- tests inexistentes
- integración
- end-to-end

## 9. Gap analysis

Compara el estado actual con la visión de Jarvis.

Clasifica cada capacidad:
`IMPLEMENTED / PARTIAL / MISSING`

## 10. Prioridades

Crea:
- P0 — Critical foundation
- P1 — Core capabilities
- P2 — Cognitive capabilities
- P3 — Agency
- P4 — Social / personality

## Resultado

Entrega un informe estructurado con:
- estado actual
- arquitectura
- memory
- reasoning
- tools
- model layer
- testing
- problemas principales
- technical debt
- capacidades faltantes
- P0/P1/P2/P3/P4
- recommended next capability

NO IMPLEMENTES NADA.
