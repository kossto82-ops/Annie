# Accesso a Internet: integración de Agent-Reach

Jarvis puede consultar, leer y recuperar información de Internet a través de
**Agent-Reach** (`C:\Projects\agent-reach`, upstream `https://github.com/Panniantong/agent-reach`).

Agent-Reach es una **capacidad** de Jarvis, no su cerebro. No sustituye la memoria, el
razonamiento ni la arquitectura cognitiva: solo abre el acceso al exterior y devuelve
documentos con procedencia, que Jarvis interpreta y razona. Nunca escribe sobre las
creencias/memoria de Jarvis directamente.

## Arquitectura

La capacidad se modela con el mismo patrón que el resto de capabilities de Jarvis
(`PerceptionSource`, `MemoryRetriever`): un `Protocol` de dominio + un adaptador en
`infrastructure`, con la red en el borde (transporte inyectable) para que los tests
sean deterministas y offline (Vision §38, D8).

```
Usuario
  ↓
Jarvis — razona y decide cuándo necesita información externa
  ↓  (solo cuando hace falta: info actualizada, buscar, verificar, leer un doc)
ExternalSource (Protocol de dominio)
  ↓
AgentReachSource (adaptador en infrastructure)
  ↓
Agent-Reach (WebChannel/Jina Reader para leer; Exa/Jina search para buscar)
  ↓
Web / fuentes externas
  ↓
RetrievedDocument (content + source + url + title + metadata)
  ↓
Jarvis interpreta y razona sobre los resultados
  ↓
Respuesta al usuario
```

### Separación de responsabilidades

1. **Razonamiento**: el núcleo cognitivo / executive. No cambia aquí.
2. **Memoria**: creencias y episodios de Jarvis. Agent-Reach nunca escribe en ella.
3. **Información externa**: lo que devuelve `ExternalSource`, con procedencia.
4. **Capacidad / herramienta**: `AgentReachSource` es solo el acceso al exterior.

Documentos traídos de vuelta: `RetrievedDocument` (content, source, url, title,
retrieved_at, metadata). Esto permite a Jarvis distinguir después entre *conocimiento
interno*, *información recuperada de Internet* e *información dicha por el usuario*.

## Componentes nuevos

| Archivo | Rol |
|---|---|
| `src/jarvis/domain/value_objects/retrieved_document.py` | `RetrievedDocument` (resultado con procedencia) |
| `src/jarvis/domain/retrieval/external_source.py` | `ExternalSource` Protocol + `ChannelStatus` |
| `src/jarvis/infrastructure/agent_reach_source.py` | `AgentReachSource` (adaptador) + `build_agent_reach_source()` |
| `src/jarvis/jarvis.py` | API pública: `read_external`, `search_external`, `internet_channels`, `set_external_source` |
| `src/jarvis/interface/command_center.py` | Comando `external` (read / search / channels) |

## Interfaces reales

La interfaz de la capacidad se adaptó a lo que Agent-Reach expone realmente:

- **`read(url)`** → `WebChannel.read(url)` vía Jina Reader (`r.jina.ai`), Markdown. *Free / zero-config.*
- **`search(query)`** → búsqueda web. En Jarvis se implementa sobre el endpoint de
  Jina (`s.jina.ai`) y **requiere `JINA_API_KEY`**. Agent-Reach no expone una API de
  búsqueda unificada; el resto de su búsqueda es por CLIs (yt-dlp, gh, opencli, ...)
  según su `SKILL.md`, que no es una interfaz programática estable — queda fuera de
  esta primera integración (ver DECISIONS: no añadir abstracciones sin responsabilidad clara).
- **`available_channels()`** → espejo del `doctor()` de Agent-Reach (salud/backend de
  cada canal: ok / warn / off / error).

`build_agent_reach_source()` devuelve `None` cuando el paquete `agent-reach` no está
instalado → Jarvis queda totalmente offline y normal.

## Configuración

1. **Instalar** Agent-Reach en el entorno de Jarvis (opcional; sin él, Jarvis funciona igual):
   ```powershell
   & C:\Projects\Annie\.venv\Scripts\python.exe -m pip install -e C:\Projects\agent-reach
   ```
2. **Leer páginas** (funciona sin clave):
   ```python
   from jarvis.infrastructure.agent_reach_source import build_agent_reach_source
   jarvis.set_external_source(build_agent_reach_source())
   doc = jarvis.read_external("https://example.com")
   ```
   O, si usas `Jarvis.persistent(...)`, la fuente se cablea automáticamente cuando
   el paquete está presente.
3. **Buscar en la web**: define la variable de entorno `JINA_API_KEY` (tu clave de
   Jina). Sin ella, `search()` responde un error claro ("no web-search provider
   configured"), para distinguir "no puedo buscar aún" de "no encontré nada". La clave
   se guarda solo en el entorno (nunca en código o el repo). También se respeta el propio
   `~/.agent-reach/config.yaml` si configuras canales vía `agent-reach configure`.

### Control de uso

Jarvis **no** llama a Internet por cada mensaje. `ExternalSource` es una capacidad
optativa, cableada y disponible; el uso real lo abre el comando `external` (read /
search / channels) o una llamada explícita a `read_external` / `search_external`.
La decisión de *cuándo* buscar sigue siendo de Jarvis (o del usuario que pide), no del
adaptador. `docs/claude/prompts/06_TOOLS_AGENCY.md` reserva el disparo automático
(modelo autónomo) para más adelante.

## Seguridad

- No se exponen secrets en el código; claves solo por entorno / `~/.agent-reach`.
- Agent-Reach ya aplica su propio saneamiento (scrub de credenciales en URLs, bloqueo
  de hosts no públicos, escaneo anti-bot, límite de tamaño de respuesta).
- La capacidad solo *recupera*; nunca escribe en memoria/creencias de Jarvis.
- Un fallo de Internet se reporta como mensaje claro; no rompe una conversación normal
  ni el aprendizaje.

## Verificación

- `pytest` (suite completa): **664 passed, 3 skipped**.
- `ruff check src` y `pyright src` (strict): **sin errores**.
- Tests específicos: `tests/domain/test_retrieved_document.py`,
  `tests/infrastructure/test_agent_reach_source.py` (transporte inyectado, sin red),
  y casos `TestExternal` en `tests/test_command_center.py` (comando `external`).
