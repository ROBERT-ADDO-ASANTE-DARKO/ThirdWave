"""
claude_client.py — shared Anthropic client + tool-calling loop, extracted
from ai_assistant.py so a second feature (the district-briefing drafter,
see .claude/plans/temporal-waddling-trinket.md) can reuse the exact same
client setup and tool-use loop instead of a second copy of it. Behavior is
unchanged from what ai_assistant.py had inline -- this is a pure
extraction, not a rewrite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

MODEL = "claude-sonnet-5"


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    return anthropic.Anthropic(api_key=api_key, default_headers=headers)


def run_tool_loop(
    client: anthropic.Anthropic, *, system: str, tools: list, tool_functions: dict,
    messages: list, max_rounds: int = 6, max_tokens: int = 1024,
) -> tuple[str, list]:
    """Runs a tool-calling loop until Claude stops asking for tools (or
    max_rounds is hit). Returns (final_text, tool_log). Generic over which
    tools/system prompt are used, so ai_assistant.py's chat and
    geo_tools.draft_briefing() can share one implementation instead of
    each maintaining their own copy of this loop."""
    tool_log = []
    for _ in range(max_rounds):
        response = client.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            tools=tools, messages=messages,
        )
        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            return final_text, tool_log

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            func = tool_functions.get(block.name)
            try:
                result = func(**block.input) if func else {"error": f"Unknown tool {block.name}"}
            except Exception as exc:
                result = {"error": str(exc)}
            tool_log.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return "I wasn't able to finish looking that up -- try rephrasing your question.", tool_log
