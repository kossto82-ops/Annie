"""External edge surface: web, research, email, delegation, execution, and tools.

Methods that interact with external providers through the seams wired into
Jarvis.  The Jarvis class retains thin delegator methods and the setter
methods (which trigger provider registry refreshes).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from jarvis.domain.retrieval.external_source import ChannelStatus
from jarvis.domain.services.model_compare import ModelRun
from jarvis.domain.tools.tool import Tool
from jarvis.domain.value_objects.email_message import EmailMessage
from jarvis.domain.value_objects.research_report import ResearchReport
from jarvis.domain.value_objects.retrieved_document import RetrievedDocument
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.domain.value_objects.tool_call_result import ToolCallResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.infrastructure.mcp_tools import McpTool

if TYPE_CHECKING:
    from jarvis.domain.retrieval.external_source import ExternalSource
    from jarvis.domain.retrieval.mail_source import MailBox
    from jarvis.domain.retrieval.research_source import ResearchSource
    from jarvis.domain.retrieval.task_agent_source import TaskAgent
    from jarvis.jarvis import Jarvis


class EdgesSurface:
    """External edge surface for web, research, email, delegation, execution, and tools."""

    def __init__(self, jarvis: Jarvis) -> None:
        self._jarvis = jarvis

    def _external(self) -> ExternalSource:
        source = self._jarvis.external_source
        if source is None:
            raise RuntimeError("no Internet capability configured; set_external_source")
        return source

    def _research(self) -> ResearchSource:
        source = self._jarvis.research_source
        if source is None:
            raise RuntimeError("no research capability configured; set research_source")
        return source

    def _mails(self) -> MailBox:
        source = self._jarvis.mail_source
        if source is None:
            raise RuntimeError("no email capability configured; set_mail_source")
        return source

    def _agent(self) -> TaskAgent:
        agent = self._jarvis.task_agent
        if agent is None:
            raise RuntimeError("no agent capability configured; set_task_agent")
        return agent

    def _openbot(self) -> TaskAgent:
        agent = self._jarvis.openbot_agent
        if agent is None:
            raise RuntimeError(
                "no OpenBot execution capability configured; set_openbot_agent"
            )
        return agent

    def _instruction(self) -> TaskAgent:
        agent = self._jarvis.instruction_agent
        if agent is None:
            raise RuntimeError(
                "no instruction executor configured; set_instruction_agent"
            )
        return agent

    # -- Internet (ExternalSource) --------------------------------------------

    def read_external(self, url: str) -> RetrievedDocument:
        return self._external().read(url)

    def search_external(
        self, query: str, *, limit: int = 5
    ) -> tuple[RetrievedDocument, ...]:
        return self._external().search(query, limit=limit)

    def internet_channels(self) -> tuple[ChannelStatus, ...]:
        source = self._jarvis.external_source
        if source is None:
            return ()
        return source.available_channels()

    # -- Research -------------------------------------------------------------

    def deep_research(self, query: str, *, depth: int = 1) -> ResearchReport:
        return self._research().deep_research(query, depth=depth)

    # -- Model comparison -----------------------------------------------------

    def compare_models(
        self, prompt: str, *, models: Sequence[str] | None = None
    ) -> tuple[ModelRun, ...]:
        compared = self._jarvis.model_compare
        if compared is None:
            raise RuntimeError("no model comparison configured; set model_compare")
        return compared.compare(prompt, models=models)

    # -- Email ----------------------------------------------------------------

    def list_emails(
        self, *, folder: str = "inbox", limit: int = 10, unread: bool = False
    ) -> tuple[EmailMessage, ...]:
        return self._mails().list_messages(folder=folder, limit=limit, unread=unread)

    def list_mail_folders(self) -> tuple[str, ...]:
        return self._mails().list_folders()

    def read_email(self, message_id: str, *, folder: str = "inbox") -> EmailMessage:
        return self._mails().read_message(message_id, folder=folder)

    def send_email(
        self, *, to: tuple[str, ...], subject: str, body: str
    ) -> EmailMessage:
        return self._mails().send_message(
            to=to, subject=subject, body=body
        )

    # -- Delegation (TaskAgent) -----------------------------------------------

    def delegate(self, task: str) -> TaskResult:
        return self._agent().run_task(task)

    def execute_on_computer(self, task: str) -> TaskResult:
        return self._openbot().run_task(task)

    def execute(self, task: str) -> TaskResult:
        return self._instruction().run_task(task)

    # -- Tools ----------------------------------------------------------------

    def register_tool(self, tool: Tool) -> None:
        self._jarvis.tool_registry.register(tool)

    def run_tool(
        self,
        name: str,
        arguments: Mapping[str, str] | None = None,
        *,
        approved: bool = False,
    ) -> ToolCallResult:
        if arguments is None:
            arguments = {}
        return self._jarvis.tool_registry.run(name, dict(arguments), approved=approved)

    def tool_names(self) -> tuple[str, ...]:
        return self._jarvis.tool_registry.tool_names()

    def tool_spec(self, name: str) -> ToolSpec | None:
        return self._jarvis.tool_registry.spec(name)

    def tool_channels(self) -> tuple[ToolSpec, ...]:
        return tuple(
            spec
            for name in self._jarvis.tool_registry.tool_names()
            if (spec := self._jarvis.tool_registry.spec(name))
        )

    def tool_origin(self, name: str) -> str:
        tool = self._jarvis.tool_registry.tool(name)
        if tool is None:
            return "unknown"
        if isinstance(tool, McpTool):
            return "mcp"
        if name.startswith("project:"):
            return "project"
        return "local"
