from __future__ import annotations

from collections import Counter
from typing import Any

from .models import NormalizedTrace, ToolCallRecord


def normalize_trace(agent_result: dict[str, Any]) -> NormalizedTrace:
    messages = agent_result.get("messages") or []
    tool_outputs = _tool_outputs_by_id(messages)

    tool_calls: list[ToolCallRecord] = []
    step_index = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue

        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            continue

        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue

            tool_use_id = str(raw_call.get("id", ""))
            output_message = tool_outputs.get(tool_use_id, {})
            output = output_message.get("content")
            is_error = _is_error_output(output)
            tool_calls.append(
                ToolCallRecord(
                    step_index=step_index,
                    tool_use_id=tool_use_id,
                    name=str(raw_call.get("name", "")),
                    args=_as_dict(raw_call.get("args")),
                    output=output,
                    is_error=is_error,
                    latency_ms=_int_value(output_message.get("latency_ms")),
                )
            )
            step_index += 1

    tool_sequence = [call.name for call in tool_calls]
    fetched_urls = [
        str(call.args["url"])
        for call in tool_calls
        if call.name == "fetch_url" and not call.is_error and "url" in call.args
    ]
    cited_urls = _string_list(agent_result.get("citations"))
    counts = Counter(tool_sequence)

    return NormalizedTrace(
        tool_calls=tool_calls,
        tool_sequence=tool_sequence,
        fetched_urls=fetched_urls,
        cited_urls=cited_urls,
        citations_missing_fetch=[
            url for url in cited_urls if url not in set(fetched_urls)
        ],
        final_answer=_string_or_none(agent_result.get("final_answer")),
        stopped_reason=str(agent_result.get("stopped_reason", "")),
        tool_count=len(tool_calls),
        search_count=counts.get("web_search", 0),
        fetch_count=counts.get("fetch_url", 0),
        quote_count=counts.get("extract_quotes", 0),
        finish_count=counts.get("finish", 0),
        wall_time_ms=_int_value(agent_result.get("wall_time_ms")),
        cost_usd=_float_value(agent_result.get("cost_usd")),
    )


def _tool_outputs_by_id(messages: list[Any]) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        tool_use_id = message.get("tool_use_id")
        if tool_use_id is None:
            continue
        outputs[str(tool_use_id)] = message
    return outputs


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _float_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _is_error_output(value: Any) -> bool:
    return isinstance(value, dict) and "error" in value
