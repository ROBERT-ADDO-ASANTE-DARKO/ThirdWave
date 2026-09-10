"""
AI Assistant — Chat2Geo-style chat interface, Tier 1 scope (see project
chat history): answers questions by calling tools that read data ALREADY
computed by risk_engine/*.py (risk_zones.json, population_exposure.json,
channel_encroachment_index.json, historical events, active incidents).
No live remote-sensing or geospatial computation happens from this chat --
that's the deferred Tier 2 scope, not built here.

Same Anthropic client pattern as vlm_client.py (.env credentials, the
anthropic-workspace-id header fix for identity-linked API keys), but uses
Claude's tool-use API instead of a single vision call: a loop that keeps
calling the model, executing any tool_use blocks against geo_tools.py, and
feeding tool_result blocks back until Claude returns a final text turn.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

from geo_tools import TOOLS, TOOL_FUNCTIONS

load_dotenv(Path(__file__).parent.parent.parent / ".env")

MODEL = "claude-sonnet-5"
MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """You are the ThirdWave AI Assistant, embedded in a flood early-warning \
system for a pilot district in Accra, Ghana. You answer questions about flood \
vulnerability by calling the tools available to you -- all of them read data that \
was already computed by an offline geospatial pipeline (Sentinel-1 SAR water \
occurrence, Copernicus DEM elevation, ESA WorldCover, OpenStreetMap buildings/waterways, \
WorldPop population). You do not have live satellite access and cannot run new \
geospatial analysis -- only look up what has already been computed.

Rules:
- Always call a tool rather than guessing at numbers, zone IDs, or scores.
- If a tool returns an error (e.g. an address couldn't be geocoded, or a location is \
outside the pilot district), say so plainly -- don't invent a fallback answer.
- Keep answers concise and concrete: cite zone IDs, scores, and levels when relevant.
- This is a proof-of-concept pilot covering a small area of Accra, not all of Ghana -- \
if asked about somewhere clearly outside the pilot district, say the pilot doesn't \
cover it rather than guessing.
- The computed score is NOT the whole picture. find_zone_by_address also returns any \
documented historical flood events near that location -- always mention them when present, \
and treat them as real, independent evidence, not a footnote. The score is built from \
satellite/terrain data (SAR, DEM, land cover) and structurally cannot see hazard types \
like dam-release floods, drainage encroachment, or one-off infrastructure failures -- a \
"Low" score next to a documented flood history is a real gap in what the score can see, \
not a contradiction to explain away. Say so plainly when it happens.
"""


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    return anthropic.Anthropic(api_key=api_key, default_headers=headers)


def _run_turn(client: anthropic.Anthropic, messages: list) -> tuple[str, list]:
    """Runs the tool-calling loop for one user turn. Returns (final_text, tool_log)."""
    tool_log = []
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM_PROMPT,
            tools=TOOLS, messages=messages,
        )
        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            return final_text, tool_log

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            func = TOOL_FUNCTIONS.get(block.name)
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


def render():
    st.subheader("AI Assistant")
    st.caption(
        "Ask questions about flood vulnerability in the pilot district. Answers are grounded in data already "
        "computed by the risk engine (SAR water occurrence, elevation, land cover, OSM buildings/waterways, "
        "WorldPop population, historical events) -- this chat looks things up, it doesn't run new geospatial "
        "analysis or fetch live satellite imagery."
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY not set -- see ThirdWave/.env")
        return

    if "ai_assistant_messages" not in st.session_state:
        st.session_state.ai_assistant_messages = []

    with st.expander("Example questions"):
        st.markdown(
            "- What's the flood risk near Kwame Nkrumah Circle?\n"
            "- Which zones should get drain maintenance priority?\n"
            "- How many people live in high-risk zones?\n"
            "- What historical flood events have happened here?\n"
            "- Compare the seven assemblies by vulnerability score."
        )

    for msg in st.session_state.ai_assistant_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tool_log"):
                with st.expander(f"🔧 {len(msg['tool_log'])} tool call(s) used", expanded=False):
                    for call in msg["tool_log"]:
                        st.markdown(f"**{call['tool']}**`({call['input']})`")
                        st.json(call["result"])

    user_input = st.chat_input("Ask about flood risk in the pilot district...")
    if not user_input:
        return

    st.session_state.ai_assistant_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    api_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.ai_assistant_messages
        if isinstance(m["content"], str)
    ]

    with st.chat_message("assistant"):
        with st.spinner("Looking that up..."):
            client = _get_client()
            try:
                final_text, tool_log = _run_turn(client, api_messages)
            except Exception as exc:
                final_text, tool_log = f"Something went wrong calling the model: {exc}", []
        st.markdown(final_text)
        if tool_log:
            with st.expander(f"🔧 {len(tool_log)} tool call(s) used", expanded=False):
                for call in tool_log:
                    st.markdown(f"**{call['tool']}**`({call['input']})`")
                    st.json(call["result"])

    st.session_state.ai_assistant_messages.append(
        {"role": "assistant", "content": final_text, "tool_log": tool_log}
    )
