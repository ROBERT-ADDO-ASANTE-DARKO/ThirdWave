"""
routers/assistant.py — POST /assistant/chat, Phase 4 feature #6 (AI
Assistant). Citizen-facing, no officer key -- same open-access stance as
every other citizen-facing endpoint in this backend.

Stateless like the rest of this backend: no server-side conversation
history is kept between requests. The client sends its full message
history each call and appends the reply itself, same shape OpenAI-style
chat APIs use -- simpler than adding session storage for a Tier 1 scope
chat that only needs this one turn's context to answer tool-grounded
questions.
"""

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

import ai_tools
import claude_chat
from db import get_session

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage]


@router.post("/chat")
def chat(body: ChatBody, session: Session = Depends(get_session)) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "ANTHROPIC_API_KEY not configured (ThirdWave/.env)."}

    tool_functions = ai_tools.build_tool_functions(session)
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        final_text, tool_log = claude_chat.run_tool_loop(
            claude_chat.get_client(), system=ai_tools.SYSTEM_PROMPT, tools=ai_tools.TOOLS,
            tool_functions=tool_functions, messages=messages, max_rounds=6,
        )
    except Exception as exc:
        return {"error": f"Something went wrong calling the model: {exc}"}

    return {"reply": final_text, "tool_log": tool_log}
