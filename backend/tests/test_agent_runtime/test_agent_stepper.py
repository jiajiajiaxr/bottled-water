import asyncio
from types import SimpleNamespace

import pytest

from agent_runtime.core.protocol import CONTROL_CANCEL, CONTROL_PAUSE, CONTROL_RESUME
from agent_runtime.core.types import AgentReport, AgentState, AgentWill, Event
from agent_runtime.runtime.agent_stepper import AgentStepper
from agent_runtime.runtime.mailbox import Mailbox


class FakeLoop:
    def __init__(self) -> None:
        self.agent = SimpleNamespace(id="worker")
        self.completed = False

    async def run(self, task, blackboard_view, *, emit_event=None, **kwargs):
        if emit_event:
            await emit_event(Event(type="agent.token", payload={"token": "first"}))
            await emit_event(Event(type="agent.token", payload={"token": "second"}))
        self.completed = True
        return {
            "work_product": f"done {task}",
            "status_report": AgentReport(
                agent_id="worker",
                state=AgentState.COMPLETED,
                will=AgentWill.COMPLETE,
            ),
        }


@pytest.mark.asyncio
async def test_agent_stepper_cancels_between_loop_events():
    mailbox = Mailbox("worker")
    loop = FakeLoop()
    stepper = AgentStepper(loop, mailbox)
    emitted: list[Event] = []

    async def emit_event(event: Event) -> None:
        emitted.append(event)
        if len(emitted) == 1:
            await mailbox.send(Event(type=CONTROL_CANCEL, payload={}, target="worker"))

    result = await stepper.run_assignment("write code", {}, emit_event=emit_event)

    assert result.interrupted is True
    assert result.report.state == AgentState.FAILED
    assert loop.completed is False
    assert [event.payload["token"] for event in emitted] == ["first"]


@pytest.mark.asyncio
async def test_agent_stepper_waits_while_paused_before_assignment():
    mailbox = Mailbox("worker")
    loop = FakeLoop()
    stepper = AgentStepper(loop, mailbox)

    await mailbox.send(Event(type=CONTROL_PAUSE, payload={}, target="worker"))
    task = asyncio.create_task(stepper.run_assignment("write code", {}))
    await asyncio.sleep(0.05)

    assert task.done() is False
    assert stepper.state == AgentState.PAUSED

    await mailbox.send(Event(type=CONTROL_RESUME, payload={}, target="worker"))
    result = await asyncio.wait_for(task, timeout=1)

    assert result.interrupted is False
    assert result.report.state == AgentState.COMPLETED
    assert loop.completed is True
