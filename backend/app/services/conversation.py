"""Conversation history management — token-based sliding window with rolling summary."""

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.core.prompts import SUMMARIZE_HISTORY_PROMPT
from app.services.summary import count_tokens
from app.services import chat_store

log = get_logger("conversation")


async def build_history_window(
    session: dict,
    all_messages: list[dict],
) -> tuple[str, list[dict]]:
    """Build the history context: running summary + recent messages that fit in token budget.

    Returns (running_summary, recent_messages).
    If overflow messages need summarizing, updates the DB.
    """
    running_summary = session.get("running_summary", "")
    watermark = session.get("summary_watermark", 0)
    budget = settings.chat_history_token_budget

    # Exclude the last user message (it's the current question, handled separately)
    history = all_messages[:-1] if all_messages else []

    if not history:
        return running_summary, []

    # Walk backward, accumulating tokens
    total_tokens = 0
    cutoff_idx = len(history)

    for i in range(len(history) - 1, -1, -1):
        msg = history[i]
        msg_tokens = count_tokens(f"{msg['role']}: {msg['content']}")
        if total_tokens + msg_tokens > budget:
            cutoff_idx = i + 1
            break
        total_tokens += msg_tokens
        cutoff_idx = i

    recent = history[cutoff_idx:]

    # Check for overflow: messages before the window that haven't been summarized yet
    overflow = [m for m in history[:cutoff_idx] if m["id"] > watermark]

    if overflow:
        log.info("Summarizing %d overflow messages for session %s", len(overflow), session["chat_id"][:8])

        overflow_text = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in overflow
        )

        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

        prompt_parts = []
        if running_summary:
            prompt_parts.append(f"Existing summary:\n{running_summary}")
        prompt_parts.append(f"New messages to incorporate:\n{overflow_text}")

        response = await llm.ainvoke([
            {"role": "system", "content": SUMMARIZE_HISTORY_PROMPT},
            {"role": "user", "content": "\n\n".join(prompt_parts)},
        ])

        running_summary = response.content
        new_watermark = max(m["id"] for m in overflow)
        await chat_store.update_running_summary(session["chat_id"], running_summary, new_watermark)

    return running_summary, recent
