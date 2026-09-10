# PLAN — Command Center al 100%

> Documento de trabajo. La fuente de la verdad es este fichero: si lo lees en una
> nueva conversación, este es el punto de partida.
> Referencia de diseño: `C:\Users\rodri\Downloads\Qwen_html_20260909_5erunrv0u.html`.
> Regla no negociable (epistémica): **todo lo que se muestra o se hace en el panel
> sale de datos o acciones reales de Jarvis. Nada inventado, nada estimado, nada
> cableado porque "queda bonito".** Si falta algo, se desarrolla el seam.

---

## 0. Línea base (lo que YA está hecho y verificado)

### Backend — comandos HTTP (`POST /api/<comando>`), en `command_center.py`
`say`, `explain`, `reflect`, `introspect`, `wonder`, `rest`, `energy_budget`,
`deliberation`, `tunables`, `perceiver`, `learn`, `greeting`, `state`,
`external` (web), `research`, `compare`, `capability` (scout/acquire/reject/
notice/list/recommend/stance), `tool` (list/run con `approved`), `calendar`
(list/get/create/update/delete/range), `google_calendar` (OAuth), `tasks`
(list/get/create/update/delete/enable/disable/due), `documents`
(list/read/info/save/edit/search/remove). Más `POST /api/stream/say` (NDJSON)
y `POST /api/speech/transcribe`.

### Backend — bloques del snapshot (`snapshot(jarvis)`)
`agents` (bordes reales + `can_do`), `environment` (CPU/RAM/Disco reales),
`memory` (episodios/creencias/self/companion/razonando/turnos/llamadas/
`episode_series`), `providers` (+ `stats` de instrumentación), `calendar_events`,
`upcoming_tasks`, `capabilities`, `needs`, `tools`, `documents`, `speech`,
`perceiver`, `tunables`, `energy`, `goals`, `activity`, `actions`, `ready`.

### Frontend (`console.html`) — paneles y navegación
Sidebar con 10 destinos + badges reales (capCount, toolCount, docCount,
convCount=episodios, taskCount=tareas activas). Paneles: `home` (AI Core
Overview, esfera, feed, Active Agents, Timeline, Quick Commands, System Monitor,
Memory Insights, LLM Status, métricas de energía), chat + paneles drawer
`panel-cap`, `panel-tool`, `panel-set` (AI Core: self/companion/tunables/
perceiver/profile), `panel-doc`, y los nuevos `panel-agents`, `panel-task`,
`panel-cal`, `panel-mem`, `panel-wf`. Voz: ear server (`/api/speech/transcribe` +
MediaRecorder) y Web Speech (offline). Panel de razonamiento (`renderReasoning`/
`renderCycle`), streaming por NDJSON, esfera reactiva.

### Puertas de verificación (`tests/test_console_asset.py` + resto)
20 tripwires del asset (incluye: agentes = bordes reales, no catálogo; monitor
sin "CPU est."; `connectedCount` solo en camino real; ids de los paneles nuevos),
157 de command_center, smoke del server, 1391 total + `ruff` + `pyright strict 0`.

---

## 1. Lo que FALTA, por área

Prioridad por fila: **[A] alta (función central que ya tiene backend y solo
falta UI)** · **[M] media (necesita backend pequeño o nuevo)** · **[O] opcional
(mejora).**

### A. Agentes (`panel-agents`)
- [A] **Detalle de estado por borde ("por qué está En espera")**. El backend
  solo expone `active` booleano. Añadir al bloque `agents` un campo `reason`
  por borde, derivado (nunca hardcodeado): seam ausente → "necesita
  `JARVIS_<VAR>`", seam presente pero sin proveedor → "proveedor no conectado",
  etc. Fuente: `server.py:_build_edge` y `usable_capabilities()`.
- [A] **Acciones por borde desde el panel**: los comandos `external`,
  `research`, `compare` ya existen; falta botón por borde (Web/Investigación/
  Comparador) que ejecute el comando con formulario de entrada y muestre el
  resultado real (no narrativa de chat).
- [M] **Superficie "raruns"**: `actions` ya está en el snapshot (Incremento 160).
  Falta un bloque en el panel que liste las acciones de ejecución recientes
  (comando, resultado, hora) con su política aplicada.
- [M] **Configurar seams desde la UI**: para cada borde en espera, enlazar a la
  pestaña/panel donde se configura (perceiver → AI Core; voz → estado de voz;
  web/research/mail/docs/notes → "Guide" con las env vars exactas, ver N).
- [O] Navegación "Ver todo" ya abre `panel-agents` (correcto).

### B. Tareas (`panel-task`)
- [A] **CRUD completo en UI**. El backend ya tiene `get/update/delete/enable/
  disable`. Falta en JS: editar (prellenar `taskName/taskCommand/taskCron`),
  eliminar (confirmación), toggle activar/desactivar, y refresco del listado
  (`pendingTaskBody`) tras cada acción. Mantener ids `taskList`/`taskDue`/
  `taskCreate` (tripwire).
- [M] **"Run now"**: no existe acción `run` en `_tasks`. Añadir action `run`
  (ejecutar la tarea de inmediato en el scheduler) al backend y botón por tarea.
- [M] **Última ejecución / salida**: extender `_upcoming_tasks` (o un nuevo
  bloque `task_runs`) con `last_run`, `last_status`, `last_output` si el
  scheduler lo guarda; si no lo guarda, anotar que el scheduler debería
  registrarlo (cambio de backend en el scheduler seam).
- [M] Validación de cron con mensaje claro de error.

### C. Calendario (`panel-cal`)
- [A] **CRUD completo en UI**: backend tiene `get/update/delete/range`. Falta
  editar (prellenar formulario), eliminar, y refrescar `pendingCalBody`.
- [M] **Vista por día/semana**: navegación de fecha con los eventos de ese rango
  (usar action `range` del backend), no solo lista de próximos.
- [M] **Conectar Google Calendar desde la UI**: existe el callback
  `/api/auth/google/callback` y `google_calendar`; falta botón "Conectar Google
  Calendar", estado conectado/desconectado y desvinculación. Mostrar
  `provider`/`kind` del bloque `calendar_events` o un nuevo campo `calendar`
  en el snapshot con `source`: local/google/none.
- [O] Preferencias de zona horaria/formato.

### D. Tools (`panel-tool`)
- [A] **Ejecutar una herramienta desde la UI**: backend `tool run` existe (con
  `approved` gate). Falta: por cada tool un botón "Run" que despliegue el
  formulario de argumentos apropiado y muestre el resultado real.
- [A] **Flujo de aprobación**: para `requires_approval`, la UI debe pedir
  confirmación explícita antes de enviar `approved: true` (el gate está en el
  core; la UI solo lo expone, nunca lo salta). Mostrar la política de cada tool
  (WRITE/external/destructive).
- [M] **Registro de ejecuciones** de tools (resultado/error/hora) en el propio
  panel (podría reusar el bloque `actions` del snapshot).
- [O] Agrupar por nivel de permiso; filtro de búsqueda.

### E. Capacidades / Skills / Odysseus (`panel-cap` + Tools & Skills)
- [A] **Scout desde el panel**: input "qué te hace falta que sepa hacer" →
  `capability scout`, persistir propuestas y mostrarlas con su `stance`
  derivada por evidencia (backend ya devuelve `recommendations`).
- [A] **Actuar sobre propuestas**: botón `acquire` y `reject` por propuesta
  (deliberado y con el stance visible; la recomendación es solo sugerencia).
- [M] **`notice` (necesidades auto-detectadas)**: botón "detectar ahora" +
  mostrar las necesidades con su evidencia (ya hay `needsbody`).
- [M] **Panel "Skills" real**: decidir la semántica (skills = capacidades
  adquiridas listas + herramientas asociadas) y renderizarlo; hoy "Tools &
  Skills" es solo el badge y el listado de tools. El badge debe seguir siendo el
  nº real de lo que se liste.
- [O] Timeline de adquisición de capacidades (adquirida_cuándo₋y evidencia).

### F. Workflows (`panel-wf`)
- [M] **Ejecutar un workflow real**: los pasos (external/research/compare/notes/
  mail/calendar/tasks) existen como comandos; falta un mini-orquestador en la UI
  que encadene pasos, muestre el estado de cada uno y el resultado final.
  Mantener honesto: un workflow solo se ejecuta si sus bordes están activos.
- [O] Crear workflows propios (selector de pasos + argumentos).

### G. Memoria (`panel-mem` + Memory Insights)
- [A] **Explorar creencias**: listar creencias con confianza y nº de evidencias,
  y poder abrir cada una en el panel de razonamiento (datos ya presentes en
  `memory.beliefs`; falta el detalle por creencia en el snapshot o un comando
  nuevo `belief <id>`).
- [M] **Recuerdo activo desde la UI**: input "buscar en mi memoria" →
  `jarvis.recall` (comando nuevo `recall` en backend) mostrando episodios con
  fuentes y pesos (candidatos, nunca veredicto).
- [M] **Conversaciones**: grupo de episodios por sesión. El badge nav usa
  episodios; falta un panel/hijo que agrupe los episodios en conversaciones y
  permita retomarlas (mandar el historial al chat).
- [O] Serie temporal con más resolución (por hora) y filtro por tipo.

### H. LLM / Proveedores / Perceiver (`panel-set` + LLM Status)
- [M] **Gestión de proveedores completa**: hoy solo switch de perceiver.
  Falta: health/test real por proveedor (llamada de verificación → `successes`),
  lista de modelos disponibles por proveedor, y elegir proveedor para el
  *razonador* (no solo perceiver).
- [M] **Estadísticas legibles**: el snapshot ya expone `stats`; falta render con
  llamadas/errores/latencia por proveedor y botón "reset".
- [M] **Stance de deliberación desde la UI**: comando `deliberation` existe;
  falta un control del valor por defecto (`deliberation` default) en la tarjeta
  Tune junto a los knobs existentes.
- [O] Banner de "sin proveedor externo — modo offline determinista".

### I. System Monitor
- [O] Historial de muestras (sparkline) en vez de solo valor instantáneo.
- [O] Mostrar `cores` y plataforma (os.name) del host.

### J. Chat / Voz / Documentos
- [M] **Documentos**: usar `remove`/`info`/`edit` desde el panel (backend listo);
  colapsar por carpeta; botón eliminar con confirmación.
- [O] **Voz**: selector de ear (browser/server) y mostrar estado de forma clara
  (ya hay `speech` block).
- [O] "Operator" real (`btnHome`): mostrar el perfil del compañero en vez de un
  avatar fijo.

### K. Energía / Metas / Necesidades
- [M] **Metas recurrentes con detalle**: hoy solo el contador. Mostrar las metas
  (texto, veces, estado) en un desplegable del strip de energía.
- [O] Tarjeta de `actions` del ejecutor (Incremento 160) en el home.

### L. Autenticación / aprobaciones / secretos
- [A] **Aprobar una acción externa/destructiva desde la UI**: flujo claro de
  confirmación que mande `approved: true` (nunca por defecto). Cubre E/D.
- [M] La key del perceiver ya se guarda en `.env` (git-ignored); anotar que
  ningún otro secreto nuevo debe aparecer en respuestas ni en claves del
  snapshot.

### M. Marca/alineación final con la referencia
- [M] Revisar el alineamiento del home con la referencia sección a sección
  (AI Core Overview, feed, Active Agents, Timeline, Quick Commands, System
  Monitor, Memory Insights, LLM Status) y rellenar los huecos visuales menores
  (tooltips, estados "N/A", iconografía) sin introducir datos falsos.

### N. Guía de configuración cerrada ("Guide")
- [M] **Panel de onboarding interno**: lista de `JARVIS_*` env vars que activan
  cada borde (`JARVIS_AGENT_ROOT`, `JARVIS_STT_*`, `JARVIS_CALENDAR_*`,
  `JARVIS_TASKS_*`, `JARVIS_PROJECT_ROOTS`, providers, Google OAuth), con estado
  actual derivado del snapshot. Mantenerla junto al panel de agentes (A) para
  que "en espera" siempre tenga un porqué accionable.

---

## 2. Orden de trabajo recomendado (por fases)

Cada fase termina con tests verdes + `ruff` + `pyright` (0 errores). Regla:
primero backend/honestidad, después UI, después tests tripwire (ampliar
`test_console_asset.py` y `test_command_center.py`).

- **F1 — Cerrar los CRUD que ya tienen backend [A]** (menor esfuerzo, mayor
  impacto): B (tasks editar/eliminar/toggle), C (calendario editar/eliminar),
  A-detalle (`reason` por borde), J-docs remove/info/edit, D-run+aprobación.
  Test: tripwires por acción nueva.
- **F2 — Odysseus en el panel [A]**: scout/acquire/reject/notice/stance (E) +
  cap de recomendaciones. Test: actions del backend que ya existen.
- **F3 — Proveedores y stat [M]**: gestión de providers, health real, stats
  render, deliberation default (H). Backend: `provider_health`/`reasoner`
  comandos nuevos si hacen falta.
- **F4 — Orquestador de workflows [M]**: encadenar pasos reales con estado (F).
- **F5 — Memoria en profundidad [M]**: `recall` comando nuevo, creencias con
  detalle, conversaciones por sesión (G).
- **F6 — Vista calendario por día + Google connect [M]** (C) y tareas run/last
  run con registro en el scheduler (B).
- **F7 — Pulido final + Guide [O/M]**: M, N, K, I, J-opcional.

---

## 3. Verificación por fase

1. `python -m pytest tests/test_console_asset.py tests/test_command_center.py -q`
2. `python -m pytest tests/ -q` (suite completa, hoy 1391 passed)
3. `JARVIS_UI_SMOKE=1 python -m pytest tests/test_command_center_server.py -q`
4. `python -m ruff check .` y `python -m pyright src/jarvis/interface/`
5. Comprobación manual en navegador de cada panel nuevo (la animación/voz no se
   cubren con pytest).

## 4. Reglas de honestidad (releer antes de tocar nada del panel)
- Un contador se muestra solo si hay un dato real detrás (estado del snapshot
  con la fuente en el docstring).
- Nunca añadir un setter imperativo de confianza ni "Connected" sin `successes`.
- Los estados por defecto son honestos: fresh Jarvis = todo "En espera",
  monitor = "n/d", proveedor = "sin envíos".
- UI solo expone el gate de aprobación; la decisión de actuar la toma el core.