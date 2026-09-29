"""Hosted concierge SSE completion with independent idle and total deadlines."""
import asyncio
import json

import httpx
from . import config


def complete(messages, json_mode=False):
    """Synchronous API for synchronous concierge routes and command-line clients."""
    if not config.CONCIERGE_API_KEY.strip() or not config.CONCIERGE_BASE_URL.strip():
        raise ValueError("Concierge provider credentials or endpoint missing")
    return asyncio.run(_complete_stream(messages, json_mode))


async def _complete_stream(messages, json_mode=False):
    payload = {"model": config.CONCIERGE_MODEL, "messages": messages,
               "max_tokens": config.REVIEW_MAX_TOKENS, "stream": True}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": "Bearer " + config.CONCIERGE_API_KEY,
               "Accept": "text/event-stream"}
    timeout = httpx.Timeout(config.REVIEW_IDLE_TIMEOUT,
                           read=config.REVIEW_IDLE_TIMEOUT,
                           connect=config.REVIEW_CONNECT_TIMEOUT)
    chunks = []
    stopped = False
    data_lines = []
    event_type = ""
    async with asyncio.timeout(config.REVIEW_TIMEOUT):
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", config.CONCIERGE_BASE_URL.rstrip("/") + "/chat/completions",
                                     headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith(":"):
                        continue  # SSE heartbeat; total deadline still applies.
                    if line:
                        field, separator, value = line.partition(":")
                        if separator and value.startswith(" "):
                            value = value[1:]
                        if field == "data":
                            data_lines.append(value)
                        elif field == "event":
                            event_type = value
                        elif field not in ("id", "retry"):
                            raise ValueError("Malformed concierge SSE field")
                        continue
                    if event_type == "error":
                        raise ValueError("Concierge returned an SSE error")
                    event_type = ""
                    if not data_lines:
                        continue
                    data = "\n".join(data_lines)
                    data_lines.clear()
                    if data == "[DONE]":
                        content = "".join(chunks)
                        if not stopped or not content.strip():
                            raise ValueError("Concierge stream lacked completed final content")
                        return content
                    event = json.loads(data)
                    if not isinstance(event, dict) or "error" in event:
                        raise ValueError("Concierge returned an invalid stream event")
                    choices = event.get("choices")
                    if choices == [] and "usage" in event:
                        continue
                    if not isinstance(choices, list) or len(choices) != 1:
                        raise ValueError("Concierge stream requires one completion choice")
                    choice = choices[0]
                    if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                        raise ValueError("Concierge returned an invalid completion choice")
                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        raise ValueError("Concierge returned an invalid completion delta")
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str) or (stopped and content):
                            raise ValueError("Concierge returned invalid final content")
                        chunks.append(content)
                    # Never accumulate, log, or persist reasoning_content/thinking.
                    finish = choice.get("finish_reason")
                    if finish is not None:
                        if finish != "stop" or stopped:
                            raise ValueError("Concierge completion did not finish normally")
                        stopped = True
    raise ValueError("Concierge stream ended before completed DONE event")
