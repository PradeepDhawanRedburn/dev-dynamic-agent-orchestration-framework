"""S-25 and S-26 (ADR-0031): questions that park a task without stopping the run.

The question store lives outside graph state. A scheduling node reads it on every pass and sends
the tasks that can run. A task that cannot proceed returns "waiting" and is sent again later in
the same run when its answer is in the store. When nothing can proceed, the supervisor (and only
the supervisor) pauses the run with interrupt(), and an arriving answer resumes it.
"""

from collections import Counter
from typing import Annotated, Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from typing_extensions import TypedDict

from tests.spike.test_checkpointer_postgres import saver_for


def merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class Run(TypedDict):
    tasks: Annotated[dict[str, str], merge]


class QuestionStore:
    """Stands in for the PostgreSQL question store. It is not part of the graph's state."""

    def __init__(self, arrive_on_read: dict[int, dict[str, str]] | None = None) -> None:
        self.answers: dict[str, str] = {}
        self.reads = 0
        self.dispatched: Counter[str] = Counter()
        self.arrive_on_read = arrive_on_read or {}

    def read_answers(self) -> dict[str, str]:
        self.reads += 1
        self.answers.update(self.arrive_on_read.get(self.reads, {}))
        return dict(self.answers)


class Plan:
    def __init__(self, deps: dict[str, list[str]], questions: dict[str, str]) -> None:
        self.deps = deps
        self.questions = questions  # task id -> question id; the task waits until it is answered


def build(
    plan: Plan, store: QuestionStore, *, pause_when_stuck: bool, checkpointer: Any | None = None
) -> Any:
    def worker(payload: dict[str, str]) -> dict[str, Any]:
        task = payload["task_id"]
        store.dispatched[task] += 1
        question = plan.questions.get(task)
        if question and question not in store.answers:
            return {"tasks": {task: "waiting"}}
        return {"tasks": {task: "done"}}

    def scheduler(state: Run) -> Command[Any]:
        answers = store.read_answers()
        status = state["tasks"]

        def runnable(task: str) -> bool:
            if any(status.get(d) != "done" for d in plan.deps[task]):
                return False
            if status.get(task) == "done":
                return False
            if status.get(task) == "waiting":
                return plan.questions[task] in answers
            return True

        ready = [t for t in plan.deps if runnable(t)]
        if ready:
            return Command(goto=[Send("worker", {"task_id": t}) for t in ready])
        outstanding = sorted(t for t in plan.deps if status.get(t) == "waiting")
        if outstanding and pause_when_stuck:
            interrupt({"gate": "waiting_for_answers", "outstanding": outstanding})
            return Command(goto="scheduler")
        return Command(goto=END)

    builder = StateGraph(Run)
    builder.add_node("worker", worker)
    builder.add_node("scheduler", scheduler, destinations=("worker", "scheduler", END))
    builder.add_edge(START, "scheduler")
    builder.add_edge("worker", "scheduler")
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


PLAN = Plan(
    deps={"t1": [], "t2": [], "t3": ["t2"], "t4": []},
    questions={"t2": "q_t2"},
)


def thread(name: str) -> Any:
    return {"configurable": {"thread_id": name}}


def test_s25_a_waiting_task_is_sent_again_in_the_same_run_when_the_store_gains_its_answer() -> None:
    store = QuestionStore(arrive_on_read={2: {"q_t2": "use postgres"}})
    graph = build(PLAN, store, pause_when_stuck=False)
    result = graph.invoke({"tasks": {}}, thread("s25"))

    assert result["tasks"] == {"t1": "done", "t2": "done", "t3": "done", "t4": "done"}
    assert store.dispatched == Counter({"t1": 1, "t4": 1, "t2": 2, "t3": 1})
    assert store.reads == 4, "the scheduling node read the store on every pass"


def test_s25_other_tasks_continue_while_one_waits_and_dependants_are_held() -> None:
    store = QuestionStore()
    graph = build(PLAN, store, pause_when_stuck=False)
    result = graph.invoke({"tasks": {}}, thread("s25-never"))

    assert result["tasks"] == {"t1": "done", "t4": "done", "t2": "waiting"}
    assert "t3" not in result["tasks"], "t3 depends on the parked t2 and was never sent"
    assert store.dispatched == Counter({"t1": 1, "t4": 1, "t2": 1}), "nothing ran twice"


@pytest.mark.postgres
def test_s25_the_same_flow_works_on_the_postgres_checkpointer(pg_dsn: str) -> None:
    store = QuestionStore(arrive_on_read={2: {"q_t2": "use postgres"}})
    with saver_for(pg_dsn) as saver:
        graph = build(PLAN, store, pause_when_stuck=False, checkpointer=saver)
        result = graph.invoke({"tasks": {}}, thread("s25-pg"))
        history = list(graph.get_state_history(thread("s25-pg")))
    assert result["tasks"]["t2"] == "done" and result["tasks"]["t3"] == "done"
    assert history[0].values["tasks"]["t2"] == "done"
    assert any(s.values.get("tasks", {}).get("t2") == "waiting" for s in history)


PAUSE_PLAN = Plan(
    deps={"a": [], "b": [], "c": ["a"]},
    questions={"a": "q_a", "b": "q_b"},
)


def pause_value(result: dict[str, Any]) -> dict[str, Any]:
    interrupts = result["__interrupt__"]
    assert len(interrupts) == 1
    value: dict[str, Any] = interrupts[0].value
    return value


def test_s26_the_run_pauses_only_when_nothing_can_proceed_and_resumes_answer_by_answer() -> None:
    store = QuestionStore()
    graph = build(PAUSE_PLAN, store, pause_when_stuck=True)
    config = thread("s26")

    first = graph.invoke({"tasks": {}}, config)
    assert pause_value(first) == {"gate": "waiting_for_answers", "outstanding": ["a", "b"]}
    assert store.dispatched == Counter({"a": 1, "b": 1})

    store.answers["q_a"] = "yes"  # one answer arrives; q_b is still outstanding
    second = graph.invoke(Command(resume="answer_arrived"), config)
    assert pause_value(second) == {"gate": "waiting_for_answers", "outstanding": ["b"]}
    assert store.dispatched == Counter({"a": 2, "b": 1, "c": 1}), "b was not run again"
    assert graph.get_state(config).values["tasks"] == {"a": "done", "b": "waiting", "c": "done"}

    # A timer wake-up with no new answer must pause again without doing any work.
    third = graph.invoke(Command(resume="timer"), config)
    assert pause_value(third)["outstanding"] == ["b"]
    assert store.dispatched == Counter({"a": 2, "b": 1, "c": 1})

    store.answers["q_b"] = "no"
    final = graph.invoke(Command(resume="answer_arrived"), config)
    assert "__interrupt__" not in final
    assert final["tasks"] == {"a": "done", "b": "done", "c": "done"}
    assert store.dispatched == Counter({"a": 2, "b": 2, "c": 1})


def test_s26_two_answers_arriving_before_one_resume_release_both_tasks_together() -> None:
    store = QuestionStore()
    graph = build(PAUSE_PLAN, store, pause_when_stuck=True)
    config = thread("s26-both")
    graph.invoke({"tasks": {}}, config)

    store.answers.update({"q_a": "yes", "q_b": "no"})
    final = graph.invoke(Command(resume="answer_arrived"), config)
    assert "__interrupt__" not in final
    assert final["tasks"] == {"a": "done", "b": "done", "c": "done"}
    assert store.dispatched == Counter({"a": 2, "b": 2, "c": 1})


def test_s26_a_resume_value_the_scheduler_did_not_consume_does_not_leak_into_the_next_pause() -> (
    None
):
    """When the answer is already in the store on re-run the node never calls interrupt(), so the
    resume value goes unused. The later pause must still stop the run, not return that value."""
    store = QuestionStore()
    graph = build(PAUSE_PLAN, store, pause_when_stuck=True)
    config = thread("s26-leak")
    graph.invoke({"tasks": {}}, config)
    store.answers["q_a"] = "yes"
    second = graph.invoke(Command(resume="stale"), config)
    assert pause_value(second)["outstanding"] == ["b"], "the second pause is a real pause"


@pytest.mark.postgres
def test_s26_the_pause_and_resume_survive_a_new_connection(pg_dsn: str) -> None:
    store = QuestionStore()
    config = thread("s26-pg")
    with saver_for(pg_dsn) as saver:
        graph = build(PAUSE_PLAN, store, pause_when_stuck=True, checkpointer=saver)
        paused = graph.invoke({"tasks": {}}, config)
        assert pause_value(paused)["outstanding"] == ["a", "b"]

    store.answers.update({"q_a": "yes", "q_b": "no"})
    with saver_for(pg_dsn) as other:
        graph = build(PAUSE_PLAN, store, pause_when_stuck=True, checkpointer=other)
        final = graph.invoke(Command(resume="answer_arrived"), config)
    assert final["tasks"] == {"a": "done", "b": "done", "c": "done"}
