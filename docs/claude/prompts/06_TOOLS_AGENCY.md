# JARVIS — TOOL SYSTEM / AGENCY

Quiero evolucionar Jarvis para que pueda utilizar herramientas de forma segura.

## Principio

No quiero:
LLM → execute()

Quiero:
Jarvis → Tool selection → Permission/policy → Execution → Observation → Evaluation → Next step

## Initial tools

Evalúa progresivamente:
- filesystem
- shell
- git
- web
- Python
- HTTP/API

No implementes todas si no son necesarias.

## Permissions

Define niveles:
- READ
- WRITE
- EXECUTE
- EXTERNAL_ACTION
- DESTRUCTIVE

Las operaciones destructivas o externas requieren confirmación inicialmente.

## Observability

Cada tool call debe poder registrar:
- herramienta
- argumentos relevantes
- resultado
- error
- duración
- permission level

No registres secretos.

## Safety

Debe ser difícil que un prompt ambiguo provoque:
- borrar proyectos
- exfiltrar secretos
- acciones destructivas
- modificar sistemas externos

## Tests

Prueba:
- herramienta válida
- inexistente
- argumentos inválidos
- permiso insuficiente
- error
- timeout
- acción destructiva
- confirmación

No conviertas Jarvis en agente autónomo todavía.
