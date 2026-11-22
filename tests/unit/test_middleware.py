"""The middleware list of a built specialist (ADR-0033 points 8 and 12; lang-family-controls)."""

from typing import Any

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, PIIMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

import orchestrator.graph.worker as worker_module
from orchestrator.contracts import AgentStatus
from orchestrator.graph.middleware import (
    ALLOWED_MIDDLEWARE,
    MIDDLEWARE_ORDER,
    BudgetMeteringMiddleware,
    MiddlewareNotAllowed,
    MiddlewareOutOfOrder,
    build_middleware,
    check_middleware,
    is_content_filter_block,
    retry_only_transient,
    tool_error_content,
)
from orchestrator.models.catalogue import ModelCatalogue, parse_catalogue
from orchestrator.tools.gateway import AgentStopped
from tests.conftest import run_async
from tests.scripted import ScriptedChatModel, specialist_output_args, tool_call_message
from tests.unit.test_worker import content_filter_error
from tests.worker_env import RESERVATION, WorkerEnv, grant, make_env, make_spec, make_task

FORBIDDEN = [
    "ShellToolMiddleware",
    "FilesystemMiddleware",
    "FilesystemFileSearchMiddleware",
    "SubAgentMiddleware",
    "AutoModeMiddleware",
    "ModelRouterMiddleware",
    "HumanInTheLoopMiddleware",
    "LLMToolEmulator",
    "SummarizationMiddleware",
    "TodoListMiddleware",
]


def stub(name: str) -> AgentMiddleware[Any, Any, Any]:
    middleware: AgentMiddleware[Any, Any, Any] = type(name, (AgentMiddleware,), {})()
    return middleware


def names(stack: list[AgentMiddleware[Any, Any, Any]]) -> list[str]:
    return [type(m).__name__ for m in stack]


def built(env: WorkerEnv, **spec_over: Any) -> list[AgentMiddleware[Any, Any, Any]]:
    spec = make_spec(tools=[], **spec_over)
    meter = env.deps.meters.for_agent(spec.agent_id, "reasoning-standard", spec.budget)
    return build_middleware(spec, meter=meter, stores=env.stores, kill=env.kill)


@pytest.fixture
def env() -> WorkerEnv:
    return make_env()


# ------------------------------------------------------------------ allow-list and order
def test_a_built_specialist_has_only_allow_listed_classes_in_the_adr_0033_order(
    env: WorkerEnv,
) -> None:
    stack = built(env)
    assert set(names(stack)) <= ALLOWED_MIDDLEWARE
    assert names(stack) == [
        "BudgetMeteringMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "PIIMiddleware",
        "PIIMiddleware",
        "PIIMiddleware",
        "ModelRetryMiddleware",
        "ModelRefusalMiddleware",
        "ToolRetryMiddleware",
        "ToolErrorMiddleware",
    ]
    check_middleware(stack)


def test_the_stack_the_worker_really_passes_to_create_agent_is_checked(
    env: WorkerEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    real = create_agent

    def spy(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr("orchestrator.graph.worker.create_agent", spy)
    spec = make_spec(tools=[grant()])

    async def scenario() -> None:
        await env.add_agent(spec)
        env.script = [AIMessage("x")]
        await worker_module.build_specialist(env.deps, spec)

    run_async(scenario())
    assert set(names(captured["middleware"])) <= ALLOWED_MIDDLEWARE
    check_middleware(captured["middleware"])
    assert names(captured["middleware"])[0] == "BudgetMeteringMiddleware"


def test_a_catalogue_fallback_adds_model_fallback_between_pii_and_retry() -> None:
    catalogue: ModelCatalogue = parse_catalogue(
        {
            "version": "t",
            "bands": {"low": {"input_per_1k": "1", "output_per_1k": "1"}},
            "entries": {
                key: {
                    "deployment": key,
                    "api": "responses",
                    "api_version": "v1",
                    "highest_classification": "internal",
                    "cost_band": "low",
                    "status": "provisional",
                    **({"fallback": "reasoning-alternate"} if key == "reasoning-standard" else {}),
                }
                for key in ("reasoning-standard", "reasoning-alternate")
            },
        }
    )
    env = make_env(catalogue=catalogue)
    spec = make_spec(tools=[])

    async def scenario() -> list[str]:
        await env.add_agent(spec)
        env.script = [AIMessage("x")]
        await worker_module.build_specialist(env.deps, spec)
        return [m.model_name if hasattr(m, "model_name") else "scripted" for m in env.models]

    run_async(scenario())
    assert len(env.models) == 2, "the fallback model was built from its own catalogue entry"


@pytest.mark.parametrize("name", FORBIDDEN)
def test_every_middleware_the_controls_forbid_is_refused_by_name(env: WorkerEnv, name: str) -> None:
    assert name not in ALLOWED_MIDDLEWARE
    with pytest.raises(MiddlewareNotAllowed, match=name):
        check_middleware([*built(env), stub(name)])


def test_a_renamed_copy_of_an_allowed_class_is_refused_too(env: WorkerEnv) -> None:
    class QuietModelRetryMiddleware(AgentMiddleware[Any, Any, Any]):
        pass

    with pytest.raises(MiddlewareNotAllowed):
        check_middleware([*built(env), QuietModelRetryMiddleware()])


def test_the_right_classes_in_the_wrong_order_are_refused(env: WorkerEnv) -> None:
    stack = built(env)
    stack[0], stack[1] = stack[1], stack[0]
    with pytest.raises(MiddlewareOutOfOrder):
        check_middleware(stack)
    reordered = list(reversed(built(env)))
    with pytest.raises(MiddlewareOutOfOrder):
        check_middleware(reordered)


def test_the_order_constant_is_the_order_in_lang_family_controls() -> None:
    assert MIDDLEWARE_ORDER == (
        "BudgetMeteringMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "PIIMiddleware",
        "ModelFallbackMiddleware",
        "ModelRetryMiddleware",
        "ModelRefusalMiddleware",
        "ToolRetryMiddleware",
        "ToolErrorMiddleware",
    )


def test_metering_is_outermost(env: WorkerEnv) -> None:
    assert isinstance(built(env)[0], BudgetMeteringMiddleware)


def test_the_limits_come_from_the_specification(env: WorkerEnv) -> None:
    from tests.worker_env import budget

    stack = built(env, budget=budget(max_model_calls=3, max_tool_calls=4, max_retries=1))
    by_name = {type(m).__name__: m for m in stack}
    assert by_name["ModelCallLimitMiddleware"].run_limit == 3  # type: ignore[attr-defined]
    assert by_name["ToolCallLimitMiddleware"].run_limit == 4  # type: ignore[attr-defined]
    assert by_name["ModelRetryMiddleware"].max_retries == 1  # type: ignore[attr-defined]
    assert by_name["ToolRetryMiddleware"].max_retries == 1  # type: ignore[attr-defined]


# ------------------------------------------------------------------ retry rules
@pytest.mark.parametrize(
    "error,expected",
    [
        (ConnectionError("x"), True),
        (TimeoutError("x"), True),
        (ValueError("x"), False),
        (AgentStopped("cancelled"), False),
        (content_filter_error(), False),
    ],
)
def test_only_transient_faults_are_retried(error: Exception, expected: bool) -> None:
    assert retry_only_transient(error) is expected


def test_a_content_filter_block_is_recognised_and_other_bad_requests_are_not() -> None:
    import httpx2
    import openai

    assert is_content_filter_block(content_filter_error())
    other = openai.BadRequestError(
        "bad",
        response=httpx2.Response(400, request=httpx2.Request("POST", "https://example.invalid/")),
        body={"code": "invalid_prompt"},
    )
    assert not is_content_filter_block(other)
    assert not is_content_filter_block(ConnectionError("x"))


# ------------------------------------------------------------------ tool errors
@tool
def explode(query: str) -> str:
    """Always fails."""
    raise ValueError("secret internal detail")


def test_a_tool_failure_always_becomes_content_that_names_the_type_and_hides_the_message(
    env: WorkerEnv,
) -> None:
    stack = [m for m in built(env) if type(m).__name__ == "ToolErrorMiddleware"]
    model = ScriptedChatModel(
        script=[tool_call_message("explode", {"query": "x"}), AIMessage("ok")]
    )
    agent = create_agent(model, tools=[explode], middleware=stack)
    messages = agent.invoke({"messages": [{"role": "user", "content": "go"}]})["messages"]
    tool_message = next(m for m in messages if isinstance(m, ToolMessage))
    assert tool_message.status == "error"
    assert "ValueError" in str(tool_message.content)
    assert "secret internal detail" not in str(tool_message.content)
    assert messages[-1].content == "ok"
    assert callable(tool_error_content)


# ------------------------------------------------------------------ PII settings
def pii_only(env: WorkerEnv) -> list[AgentMiddleware[Any, Any, Any]]:
    return [m for m in built(env) if isinstance(m, PIIMiddleware)]


@tool
def directory(query: str) -> str:
    """Look someone up."""
    return "Contact: jane.doe@example.com"


def test_input_is_not_scanned_output_is_redacted_and_tool_results_are_not_altered(
    env: WorkerEnv,
) -> None:
    model = ScriptedChatModel(
        script=[
            tool_call_message("directory", {"query": "x"}),
            AIMessage("Write to jane.doe@example.com"),
        ]
    )
    agent = create_agent(model, tools=[directory], middleware=pii_only(env))
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "The sponsor is bob@example.com"}]}
    )
    sent_first = " ".join(str(m.content) for m in model.seen[0])
    assert "bob@example.com" in sent_first, "the sponsor's request reaches the agent verbatim"
    sent_second = " ".join(str(m.content) for m in model.seen[1])
    assert "jane.doe@example.com" in sent_second, "tool results are not altered"
    final = result["messages"][-1].content
    assert "jane.doe@example.com" not in final and "[REDACTED_EMAIL]" in final


def test_each_pii_setting_is_stated_explicitly(env: WorkerEnv) -> None:
    for middleware in pii_only(env):
        assert middleware.apply_to_input is False  # type: ignore[attr-defined]
        assert middleware.apply_to_output is True  # type: ignore[attr-defined]
        assert middleware.apply_to_tool_results is False  # type: ignore[attr-defined]
        assert middleware.strategy == "redact"  # type: ignore[attr-defined]


def test_the_pii_instances_have_distinct_names_so_they_can_share_one_agent(
    env: WorkerEnv,
) -> None:
    pii_names = [m.name for m in pii_only(env)]
    assert len(pii_names) == len(set(pii_names)) == 3


def probe_structured_output_redaction(env: WorkerEnv) -> dict[str, Any]:
    """Does output scanning reach the text the specialist returns through the structured-output
    tool call? Recorded in the findings either way."""
    spec = make_spec(tools=[])
    args = specialist_output_args(1)
    args["claims"] = []
    args["executive_summary"] = "Contact jane.doe@example.com for details."

    async def scenario() -> dict[str, Any]:
        await env.add_agent(spec)
        env.script = [tool_call_message("SpecialistOutput", args)]
        outcome = await worker_module.run_specialist(
            env.deps, spec, make_task(spec), reservation_id=RESERVATION
        )
        assert outcome.result is not None
        return {
            "summary": outcome.result.output.executive_summary,
            "status": AgentStatus.AWAITING_REVIEW,
        }

    return run_async(scenario())


def test_known_gap_pii_output_scan_does_not_reach_the_structured_result(env: WorkerEnv) -> None:
    """PIIMiddleware scans message text, and a specialist's result is the arguments of a tool call.
    This pins today's behaviour (langchain 1.5.2) so a library change shows up. See the issue
    linked from docs/governance/control-matrix.md."""
    summary = probe_structured_output_redaction(env)["summary"]
    assert summary == "Contact jane.doe@example.com for details."
