from __future__ import annotations

from persona.core.agent import AgentStatus, BaseAgent


class _Emit(BaseAgent):
    def _execute(self):
        yield "a"
        yield "b"


class _Flaky(BaseAgent):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = 0

    def _execute(self):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("boom")
        yield "ok"


def test_lifecycle_and_terminal_state():
    states = list(_Emit().run())
    assert states[0]["status"] == AgentStatus.RUNNING.value
    assert states[-1]["status"] == AgentStatus.FINISHED.value
    assert any(s["status"] == AgentStatus.SUCCESS.value and s["resp"] == "b" for s in states)


def test_run_to_resp():
    assert _Emit().run_to_resp() == "b"


def test_whole_run_retry_then_succeed():
    ag = _Flaky(max_retries=3)
    assert ag.run_to_resp() == "ok"
    assert ag.calls == 3


def test_retry_exhausted_is_not_fatal():
    class _Always(BaseAgent):
        def _execute(self):
            raise RuntimeError("nope")
            yield

    ag = _Always(max_retries=1)
    states = list(ag.run())
    assert states[-1]["status"] == AgentStatus.FINISHED.value
    assert ag.run_to_resp() is None


def test_message_status_resets_to_running():
    class _Msg(BaseAgent):
        def _execute(self):
            self.status = AgentStatus.MESSAGE
            yield {"seg": 1}
            assert self.status == AgentStatus.RUNNING

    seen = [s["status"] for s in _Msg().run()]
    assert AgentStatus.MESSAGE.value in seen
    assert seen[-1] == AgentStatus.FINISHED.value
