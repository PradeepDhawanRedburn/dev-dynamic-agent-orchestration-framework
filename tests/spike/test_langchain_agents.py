"""S-09, S-10, S-16, S-18, S-19: LangChain agents, middleware and structured output (no model)."""

import asyncio
import re
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRefusalMiddleware,
    ModelRetryMiddleware,
    PIIDetectionError,
    PIIMatch,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
    hook_config,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.structured_output import (
    StructuredOutputValidationError,
    ToolStrategy,
)
from langchain.tools import tool
from langchain_core.exceptions import ModelRefusalError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from tests.spike.support import (
    ScriptedChatModel,
    SpecialistOutput,
    specialist_output_args,
    tool_call_message,
)

FINAL = AIMessage(content="final answer")


def agent_input(text: str = "hello") -> dict[str, Any]:
    return {"messages": [HumanMessage(text)]}


# ---------------------------------------------------------------- S-09


@pytest.mark.parametrize("claims", [3, 60])
def test_s09_tool_strategy_returns_a_validated_pydantic_instance(claims: int) -> None:
    model = ScriptedChatModel(
        script=[tool_call_message("SpecialistOutput", specialist_output_args(claims))]
    )
    agent = create_agent(model, tools=[], response_format=ToolStrategy(SpecialistOutput))
    result = agent.invoke(agent_input())
    output = result["structured_response"]
    assert isinstance(output, SpecialistOutput)
    assert len(output.claims) == claims


def invalid_output_args() -> dict[str, Any]:
    args = specialist_output_args(1)
    args["claims"][0]["evidence_ids"] = []  # a material claim with no evidence is invalid
    return args


def test_s09_invalid_output_is_returned_to_the_model_once_then_accepted() -> None:
    model = ScriptedChatModel(
        script=[
            tool_call_message("SpecialistOutput", invalid_output_args()),
            tool_call_message("SpecialistOutput", specialist_output_args(1)),
        ]
    )
    agent = create_agent(model, tools=[], response_format=ToolStrategy(SpecialistOutput))
    result = agent.invoke(agent_input())
    assert isinstance(result["structured_response"], SpecialistOutput)
    assert model.calls == 2
    # The error text goes back to the model as a ToolMessage whose status is still "success".
    feedback = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert str(feedback[0].content).startswith("Error: Failed to parse structured output")
    assert "evidence" in str(feedback[0].content)


def test_s09_validation_errors_can_be_made_to_raise_instead() -> None:
    model = ScriptedChatModel(script=[tool_call_message("SpecialistOutput", invalid_output_args())])
    strategy = ToolStrategy(SpecialistOutput, handle_errors=False)
    agent = create_agent(model, tools=[], response_format=strategy)
    with pytest.raises(StructuredOutputValidationError):
        agent.invoke(agent_input())


# ---------------------------------------------------------------- S-10


class Recorder(AgentMiddleware):  # type: ignore[type-arg]
    def __init__(self, name: str, events: list[str]) -> None:
        super().__init__()
        self.label = name
        self.events = events

    @property
    def name(self) -> str:
        return f"Recorder-{self.label}"

    async def abefore_model(self, state: AgentState[Any], runtime: Runtime[Any]) -> None:
        self.events.append(f"abefore {self.label}")

    async def aafter_model(self, state: AgentState[Any], runtime: Runtime[Any]) -> None:
        self.events.append(f"aafter {self.label}")


def test_s10_async_hooks_run_under_ainvoke_in_order_and_after_hooks_in_reverse() -> None:
    events: list[str] = []
    model = ScriptedChatModel(script=[FINAL])
    agent = create_agent(
        model, tools=[], middleware=[Recorder("one", events), Recorder("two", events)]
    )
    asyncio.run(agent.ainvoke(agent_input()))
    assert events == ["abefore one", "abefore two", "aafter two", "aafter one"]


class Stopper(AgentMiddleware):  # type: ignore[type-arg]
    def __init__(self, where: str) -> None:
        super().__init__()
        self.where = where

    async def abefore_model(self, state: AgentState[Any], runtime: Runtime[Any]) -> None:
        if self.where == "before":
            raise RuntimeError("stop before the model")

    async def aafter_model(self, state: AgentState[Any], runtime: Runtime[Any]) -> None:
        if self.where == "after":
            raise RuntimeError("stop after the model")


@pytest.mark.parametrize(("where", "model_calls"), [("before", 0), ("after", 1)])
def test_s10_raising_from_a_hook_stops_the_agent(where: str, model_calls: int) -> None:
    model = ScriptedChatModel(script=[FINAL])
    agent = create_agent(model, tools=[], middleware=[Stopper(where)])
    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(agent.ainvoke(agent_input()))
    assert model.calls == model_calls


class JumpToEnd(AgentMiddleware):  # type: ignore[type-arg]
    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return {"messages": [AIMessage("stopped by middleware")], "jump_to": "end"}


def test_s10_documented_jump_to_end_stops_without_an_exception() -> None:
    model = ScriptedChatModel(script=[FINAL])
    agent = create_agent(model, tools=[], middleware=[JumpToEnd()])
    result = asyncio.run(agent.ainvoke(agent_input()))
    assert model.calls == 0
    assert result["messages"][-1].content == "stopped by middleware"


# ---------------------------------------------------------------- S-16


def test_s16_include_raw_returns_raw_parsed_and_parsing_error() -> None:
    good = ScriptedChatModel(
        script=[tool_call_message("SpecialistOutput", specialist_output_args(2), input_tokens=7)]
    )
    result = good.with_structured_output(SpecialistOutput, include_raw=True).invoke("go")
    assert set(result) == {"raw", "parsed", "parsing_error"}
    assert isinstance(result["parsed"], SpecialistOutput)
    assert result["parsing_error"] is None
    assert result["raw"].usage_metadata["input_tokens"] == 7

    bad = ScriptedChatModel(script=[tool_call_message("SpecialistOutput", invalid_output_args())])
    failed = bad.with_structured_output(SpecialistOutput, include_raw=True).invoke("go")
    assert failed["parsed"] is None
    assert failed["parsing_error"] is not None
    assert failed["raw"].tool_calls


# ---------------------------------------------------------------- S-18


ALLOWED = [
    "ModelCallLimitMiddleware",
    "ToolCallLimitMiddleware",
    "ModelRetryMiddleware",
    "ToolRetryMiddleware",
    "ModelFallbackMiddleware",
    "ToolErrorMiddleware",
    "ModelRefusalMiddleware",
    "PIIMiddleware",
]
FORBIDDEN_PRESENT_IN_LANGCHAIN = [
    "ShellToolMiddleware",
    "FilesystemFileSearchMiddleware",
    "AutoModeMiddleware",
    "ModelRouterMiddleware",
    "HumanInTheLoopMiddleware",
    "LLMToolEmulator",
]
FORBIDDEN_NOT_IN_LANGCHAIN = ["FilesystemMiddleware", "SubAgentMiddleware"]


def test_s18_every_allowed_middleware_exists() -> None:
    import langchain.agents.middleware as middleware

    assert [name for name in ALLOWED if not hasattr(middleware, name)] == []


def test_s18_forbidden_middleware_that_exists_in_langchain_can_be_detected() -> None:
    import langchain.agents.middleware as middleware

    assert [n for n in FORBIDDEN_PRESENT_IN_LANGCHAIN if not hasattr(middleware, n)] == []
    assert [n for n in FORBIDDEN_NOT_IN_LANGCHAIN if hasattr(middleware, n)] == []


@tool
def lookup(query: str) -> str:
    """Look something up."""
    return f"result for {query}"


@tool
def explode(query: str) -> str:
    """Always fails."""
    raise ValueError("secret internal detail")


def test_s18_the_allowed_middleware_compose_in_one_agent() -> None:
    primary = ScriptedChatModel(script=[tool_call_message("lookup", {"query": "x"}), FINAL])
    agent = create_agent(
        primary,
        tools=[lookup, explode],
        middleware=[
            ModelCallLimitMiddleware(run_limit=5),
            ToolCallLimitMiddleware(run_limit=5),
            ModelRetryMiddleware(max_retries=1, initial_delay=0, jitter=False),
            ToolRetryMiddleware(max_retries=1, initial_delay=0, jitter=False),
            ModelFallbackMiddleware(ScriptedChatModel(script=[FINAL])),
            ModelRefusalMiddleware(),
            ToolErrorMiddleware(on_error=lambda error, request: type(error).__name__),
            PIIMiddleware("email", strategy="redact"),
        ],
    )
    result = agent.invoke(agent_input("write to jane@example.com"))
    assert result["messages"][-1].content == "final answer"
    assert primary.calls == 2
    sent = " ".join(str(m.content) for m in primary.seen[0])
    assert "jane@example.com" not in sent and "[REDACTED_EMAIL]" in sent


def retry_and_fallback_agent(order: str) -> tuple[Any, ScriptedChatModel, ScriptedChatModel]:
    primary = ScriptedChatModel(script=[FINAL], fail_first=1)
    fallback = ScriptedChatModel(script=[AIMessage("from fallback")])
    retry = ModelRetryMiddleware(max_retries=1, initial_delay=0, jitter=False)
    switch = ModelFallbackMiddleware(fallback)
    stack = [retry, switch] if order == "retry_first" else [switch, retry]
    return create_agent(primary, tools=[], middleware=stack), primary, fallback


def test_s18_list_order_decides_whether_a_failed_model_is_retried_or_replaced() -> None:
    """The first middleware in the list is the outermost, so it sees a failure last."""
    agent, primary, fallback = retry_and_fallback_agent("retry_first")
    assert agent.invoke(agent_input())["messages"][-1].content == "from fallback"
    assert primary.attempts == 1, "the fallback caught the failure before the retry could"

    agent, primary, fallback = retry_and_fallback_agent("fallback_first")
    assert agent.invoke(agent_input())["messages"][-1].content == "final answer"
    assert primary.attempts == 2 and fallback.calls == 0


def test_s18_model_call_limit_can_raise() -> None:
    model = ScriptedChatModel(script=[tool_call_message("lookup", {"query": "x"})])
    agent = create_agent(
        model,
        tools=[lookup],
        middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="error")],
    )
    with pytest.raises(ModelCallLimitExceededError):
        agent.invoke(agent_input())


def test_s18_model_fallback_switches_to_the_named_alternate() -> None:
    primary = ScriptedChatModel(script=[FINAL], fail_first=99)
    fallback = ScriptedChatModel(script=[AIMessage("from fallback")])
    agent = create_agent(primary, tools=[], middleware=[ModelFallbackMiddleware(fallback)])
    assert agent.invoke(agent_input())["messages"][-1].content == "from fallback"


def test_s18_a_refusal_is_raised_not_returned_as_an_answer() -> None:
    refusal = AIMessage(content=[{"type": "refusal", "refusal": "I cannot help"}])
    agent = create_agent(
        ScriptedChatModel(script=[refusal]), tools=[], middleware=[ModelRefusalMiddleware()]
    )
    with pytest.raises(ModelRefusalError):
        agent.invoke(agent_input())

    plain = create_agent(ScriptedChatModel(script=[refusal]), tools=[])
    assert plain.invoke(agent_input())["messages"][-1].content


def test_s18_tool_failure_becomes_a_message_only_when_a_handler_returns_content() -> None:
    script = [tool_call_message("explode", {"query": "x"}), FINAL]
    handled = create_agent(
        ScriptedChatModel(script=list(script)),
        tools=[explode],
        middleware=[ToolErrorMiddleware(on_error=lambda error, request: type(error).__name__)],
    )
    messages = handled.invoke(agent_input())["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert tool_messages[0].status == "error" and tool_messages[0].content == "ValueError"
    assert "secret internal detail" not in str(tool_messages[0].content)

    unhandled = create_agent(
        ScriptedChatModel(script=list(script)),
        tools=[explode],
        middleware=[ToolErrorMiddleware(on_error=lambda error, request: None)],
    )
    with pytest.raises(ValueError, match="secret internal detail"):
        unhandled.invoke(agent_input())


# ---------------------------------------------------------------- S-19


def name_detector(text: str) -> list[PIIMatch]:
    return [
        PIIMatch(type="person_name", value=m.group(), start=m.start(), end=m.end())
        for m in re.finditer(r"\b(?:Alice|Bob) [A-Z][a-z]+\b", text)
    ]


def sent_text(model: ScriptedChatModel) -> str:
    return " ".join(str(m.content) for m in model.seen[0])


def test_s19_pii_middleware_accepts_a_regex_and_a_callable_detector() -> None:
    model = ScriptedChatModel(script=[FINAL])
    agent = create_agent(
        model,
        tools=[],
        middleware=[
            PIIMiddleware("account_number", detector=r"\bACC-\d{6}\b", strategy="redact"),
            PIIMiddleware("person_name", detector=name_detector, strategy="hash"),
        ],
    )
    agent.invoke(agent_input("Alice Smith owns ACC-123456"))
    text = sent_text(model)
    assert "ACC-123456" not in text and "[REDACTED_ACCOUNT_NUMBER]" in text
    assert "Alice Smith" not in text and "<person_name_hash:" in text


def test_s19_block_strategy_raises_and_defaults_leave_output_and_tool_results_alone() -> None:
    blocker = create_agent(
        ScriptedChatModel(script=[FINAL]),
        tools=[],
        middleware=[PIIMiddleware("email", strategy="block")],
    )
    with pytest.raises(PIIDetectionError):
        blocker.invoke(agent_input("mail jane@example.com"))

    leaky = create_agent(
        ScriptedChatModel(script=[AIMessage("contact jane@example.com")]),
        tools=[],
        middleware=[PIIMiddleware("email", strategy="redact")],
    )
    assert "jane@example.com" in leaky.invoke(agent_input())["messages"][-1].content
