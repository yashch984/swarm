"""
Core monolith vs swarm pipeline shared by Streamlit UI and batch runner.

Uses the Groq API only (official groq package). Requires GROQ_API_KEY.

Contains:
- MODEL / temperature / cost constants
- call_api (Groq chat completions)
- run_baseline (monolithic arm)
- run_swarm (Swarm Versonalities arm)

No Streamlit imports here; this module is safe for offline batch runs.
"""

import os
from typing import List, Tuple

from groq import Groq


MODEL = "llama-3.1-8b-instant"
TEMPERATURE = float(os.environ.get("SWARM_TEMPERATURE", "0"))
COST_INPUT_PER_1M = float(os.environ.get("SWARM_COST_INPUT_PER_1M", "0.05"))
COST_OUTPUT_PER_1M = float(os.environ.get("SWARM_COST_OUTPUT_PER_1M", "0.10"))


def _get_groq_client() -> Groq:
    api_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. Set it in your environment to use the Groq API.\n"
            "Example: export GROQ_API_KEY='your-key'"
        )
    return Groq(api_key=api_key)


SYSTEM_PROMPT = """You are part of a Swarm Versonalities v1 workflow. Follow these rules strictly:

1. Use exactly ONE versonality at a time
2. Do NOT skip roles in the sequence
3. Planner: Create a plan but do NOT solve the task
4. Analyst: Analyze requirements but do NOT draft output
5. Builder: Create the actual output
6. Critic: Review and provide feedback but do NOT rewrite
7. Editor: Produce the final clean artifact

Current role will be specified in each message."""


SWARM_ROLES: List[Tuple[str, str, str, str]] = [
    ("planner", "plan", "PLANNER", "Create a plan for completing this task. Do NOT solve it."),
    ("analyst", "decide", "ANALYST", "Analyze the requirements and plan. Do NOT draft any output."),
    ("builder", "act", "BUILDER", "Create the actual output based on the plan and analysis."),
    ("critic", "verify", "CRITIC", "Review the output and provide feedback. Do NOT rewrite it."),
    ("builder2", "act", "BUILDER", "Revise the output based on the critic's feedback."),
    ("editor", "finalize", "EDITOR", "Produce the final clean artifact. Output ONLY the final result, no meta-commentary."),
]


def call_api(messages):
    """Call Groq API (chat completions). Raises ValueError if GROQ_API_KEY is missing; raises groq.APIError on API errors."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
    )
    content = response.choices[0].message.content
    usage = getattr(response, "usage", None)
    tokens_in = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", 0) if usage else 0
    tokens_out = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", 0) if usage else 0
    return content, tokens_in, tokens_out


def cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * COST_INPUT_PER_1M + tokens_out * COST_OUTPUT_PER_1M) / 1e6


def run_baseline(task: str, run_id: str, task_id: str, task_bucket: str = "", *, log_event=None):
    """
    Monolithic arm: single LLM call, no versonalities.
    If log_event is provided, events are emitted to logs/events.jsonl.
    This pipeline does not invoke tools; when extending with tools, call log_event(..., tool="name", tool_ok=...).
    """
    messages = [{"role": "user", "content": task}]
    if log_event is not None:
        log_event(
            run_id=run_id,
            task_id=task_id,
            arm="monolith",
            agent_id="monolith",
            versonality="monolith",
            phase="act",
            event="message",
            task_bucket=task_bucket,
        )
    content, ti, to = call_api(messages)
    if log_event is not None:
        log_event(
            run_id=run_id,
            task_id=task_id,
            arm="monolith",
            agent_id="monolith",
            versonality="monolith",
            phase="act",
            event="end",
            tokens_in=ti,
            tokens_out=to,
            task_bucket=task_bucket,
        )
    return content, ti, to


def run_swarm(task: str, run_id: str, task_id: str, task_bucket: str = "", *, log_event=None):
    """
    Swarm arm: Planner → Analyst → Builder → Critic → Builder → Editor.
    Uses SYSTEM_PROMPT and SWARM_ROLES. If log_event is provided, events are emitted to logs/events.jsonl.
    This pipeline does not invoke tools; when extending with tools, call log_event(..., tool="name", tool_ok=...).
    """
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
    total_in, total_out = 0, 0
    final_content = ""

    for agent_id, phase, role_name, instruction in SWARM_ROLES:
        if agent_id == "builder2":
            user_content = "Role: BUILDER\n\nRevise the output based on the critic's feedback."
        elif agent_id == "editor":
            user_content = f"Role: {role_name}\n\n{instruction}"
        else:
            if agent_id == "planner":
                user_content = f"Role: {role_name}\n\nTask: {task}\n\n{instruction}"
            else:
                user_content = f"Role: {role_name}\n\n{instruction}"

        conversation.append({"role": "user", "content": user_content})
        if log_event is not None:
            log_event(
                run_id=run_id,
                task_id=task_id,
                arm="swarm",
                agent_id=agent_id,
                versonality=role_name.lower(),
                phase=phase,
                event="message",
                task_bucket=task_bucket,
            )
        content, ti, to = call_api(conversation)
        total_in += ti
        total_out += to
        if log_event is not None:
            log_event(
                run_id=run_id,
                task_id=task_id,
                arm="swarm",
                agent_id=agent_id,
                versonality=role_name.lower(),
                phase=phase,
                event="end",
                tokens_in=ti,
                tokens_out=to,
                task_bucket=task_bucket,
            )
        conversation.append({"role": "assistant", "content": content})
        final_content = content

    return final_content, total_in, total_out

