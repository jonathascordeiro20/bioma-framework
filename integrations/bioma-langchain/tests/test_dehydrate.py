"""Offline tests for bioma-langchain (requires langchain-core + bioma_micro)."""
import pytest

lc = pytest.importorskip("langchain_core.messages")
from langchain_core.messages import (  # noqa: E402
    AIMessage, HumanMessage, SystemMessage, ToolMessage)

import bioma_micro  # noqa: E402
from bioma_langchain import BiomaDehydrator, dehydrate_messages, signal_for  # noqa: E402


def _long_session(rounds: int = 20):
    msgs = [
        SystemMessage("You are a precise ops copilot."),
        HumanMessage("FACT: incident code is INC-7743.",
                     additional_kwargs={"bioma": "fact"}),
    ]
    for i in range(rounds):
        msgs.append(AIMessage("", tool_calls=[
            {"name": "bash", "args": {"cmd": f"audit {i}"}, "id": f"t{i}"}]))
        msgs.append(ToolMessage("conn=ok filler " * 120, tool_call_id=f"t{i}"))
        msgs.append(HumanMessage(f"Round {i}: anomaly?"))
        msgs.append(AIMessage(f"Round {i}: nothing above baseline."))
    msgs.append(HumanMessage("Which incident code is open?"))
    return msgs


def test_signal_mapping():
    assert signal_for(SystemMessage("x")) == bioma_micro.SYSTEM
    assert signal_for(ToolMessage("x", tool_call_id="1")) == bioma_micro.TOOL
    assert signal_for(HumanMessage("x")) == bioma_micro.USER
    assert signal_for(AIMessage("x")) == bioma_micro.ASSISTANT
    assert signal_for(HumanMessage("x", additional_kwargs={"bioma": "fact"})) == bioma_micro.FACT


def test_protected_classes_survive_and_tools_purge():
    msgs = _long_session()
    lean, audit = dehydrate_messages(msgs, return_audit=True)
    texts = [m.content for m in lean]
    assert "You are a precise ops copilot." in texts          # SYSTEM survives
    assert any("INC-7743" in str(t) for t in texts)           # FACT survives
    assert texts[-1] == "Which incident code is open?"        # newest turn survives
    assert audit["reduction"] > 0.5                            # bulk of tool logs gone
    assert audit["blocks_purged"] > 0
    assert audit["kernel_latency_us"] < 10_000                 # µs-scale, generous CI bound


def test_original_objects_and_order_preserved():
    msgs = _long_session(rounds=5)
    lean = dehydrate_messages(msgs)
    ids = {id(m) for m in msgs}
    assert all(id(m) in ids for m in lean)                     # same objects, no copies
    positions = [msgs.index(m) for m in lean]
    assert positions == sorted(positions)                      # order preserved


def test_runnable_invoke_and_audit():
    d = BiomaDehydrator()
    lean = d.invoke(_long_session())
    assert d.last_audit is not None and d.last_audit["tokens_after"] > 0
    assert len(lean) < 20 * 4 + 3


def test_threshold_02_keeps_freshest_tool_result():
    # agentic shape: the tool result the agent is ABOUT to reason over is age 1
    msgs = _long_session(rounds=12)[:-1]  # drop the trailing question
    msgs.append(AIMessage("", tool_calls=[
        {"name": "bash", "args": {"cmd": "pytest"}, "id": "tf"}]))
    msgs.append(ToolMessage("FAILED test_x — assert 1 == 2", tool_call_id="tf"))
    msgs.append(HumanMessage("What does the failure say?"))

    at_035 = dehydrate_messages(msgs, safe_threshold=0.35)
    at_020 = dehydrate_messages(msgs, safe_threshold=0.2)
    fresh = lambda lean: any(  # noqa: E731
        isinstance(m, ToolMessage) and "FAILED test_x" in str(m.content) for m in lean)
    assert not fresh(at_035)   # kernel default purges even the freshest tool (measured trap)
    assert fresh(at_020)       # the recommended agentic tuning keeps it
