# JARVIS — EXECUTIVE / PLANNER

Quiero construir el sistema ejecutivo de Jarvis.

## Loop

Goal → Understand → Plan → Act → Observe → Evaluate → Re-plan → Complete

## Requisitos

El planner debe poder:
- dividir objetivos
- crear subtareas
- priorizar
- ejecutar
- observar resultados
- detectar fallos
- replanificar
- saber cuándo parar

No quiero:
LLM → generate giant plan → execute blindly

Quiero:
plan → step → observe → evaluate → next step

## State

Define claramente:
- goal
- task
- subtask
- current step
- status
- result
- error
- retry
- blocked
- completed

## Autonomía

Inicialmente limitada. Pedir ayuda cuando falte información es un resultado válido.

## Tests

Prueba:
- tarea sencilla
- multi-step
- fallo de herramienta
- información insuficiente
- replanning
- timeout
- completion

Implementa solo después de inspeccionar el sistema actual.
