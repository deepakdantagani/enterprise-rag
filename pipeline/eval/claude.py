"""RET-10e-a: claude_llm, the LlamaIndex Anthropic wrapper that works for Claude 5 ids, with prompt caching.

The first live run of the agent loop (RET-10e smoke, 2026-11-08) failed twice before any model
call. `llama-index-llms-anthropic` 0.12.2 raises `Unknown model: claude-haiku-5-5` from
`.metadata`: its context-size table has Sonnet 5, Sonnet 5.5, Opus 5 and Opus 5.5, but not the
Haiku the agent runs on, and the agent reads the context window to size its memory. Fixed, it then
sent `temperature=0.1`, the wrapper's default: the library drops `temperature` only for the ids in
its `ANTHROPIC_NO_TEMP_MODELS` list (Haiku 5.5 and the 4.x ids are not on it), while the Anthropic
SDK 1.11 (API version 2026-10-21) rejects it for every model with a `TypeError` before the request
leaves. And a loop of 8 calls resends its whole history each call: qst_0437 spent 268K full-price
input tokens. The wrapper's optional `cache_idx` marks every message, and the API allows four cache
points per request, so it cannot serve a loop; the API's top-level `cache_control` field can.

So one subclass, kept to two overrides, and one function. Known models keep the library's
metadata; any other id, a typo included, gets the Claude 5 values (1M context, tool-calling, chat)
and fails at the API instead. `_get_all_kwargs` is the one method all four chat paths (chat,
stream_chat and their async forms) build the request through, so one override covers them all;
it drops the three sampling parameters for every model. Adaptive thinking and an effort level go
through, and `cache_control` caches the prefix (tools, system prompt, history) up to the last
cacheable block: on qst_0001, call 1 wrote 1,350 tokens (prompt and 3 tools), calls 2 to 7 read
the growing prefix (1,350 → 19,016) with 2 uncached tokens each, about half a cent in all.

    >>> llm = claude_llm("claude-haiku-5-5", api_key="x")
    >>> sorted(llm._get_all_kwargs())
    ['cache_control', 'max_tokens', 'model', 'output_config', 'thinking']
    >>> llm.metadata.context_window, llm.metadata.is_function_calling_model
    (1000000, True)
"""
from typing import Any, Dict, Optional

from llama_index.core.llms import LLMMetadata
from llama_index.llms.anthropic import Anthropic

SAMPLING_PARAMETERS = ("temperature", "top_p", "top_k")  # the SDK 1.11 / API 2026-10-21 rejects them for every model
CLAUDE_5_CONTEXT = 1_000_000
DEFAULT_EFFORT, DEFAULT_MAX_TOKENS = "medium", 8_000  # Haiku 5.5's default effort; the longest agent answer so far was 1,547 tokens


class Claude5(Anthropic):
    """The library's Anthropic LLM with metadata for any Claude id and no sampling parameters in the request."""

    @property
    def metadata(self) -> LLMMetadata:
        try:
            return super().metadata  # the library's table, for the models it knows
        except ValueError:
            return LLMMetadata(context_window=CLAUDE_5_CONTEXT, num_output=self.max_tokens, is_chat_model=True,
                               is_function_calling_model=True, model_name=self.model)

    def _get_all_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        request = super()._get_all_kwargs(**kwargs)  # the library keeps temperature for ids outside ANTHROPIC_NO_TEMP_MODELS
        for name in SAMPLING_PARAMETERS:
            request.pop(name, None)
        return request


def claude_llm(model: str, effort: str = DEFAULT_EFFORT, max_tokens: int = DEFAULT_MAX_TOKENS, api_key: Optional[str] = None) -> Anthropic:
    """A Claude LLM for the agent and the judges: adaptive thinking, `effort`, and the API's top-level prompt caching."""
    return Claude5(model=model, max_tokens=max_tokens, api_key=api_key, thinking_dict={"type": "adaptive"},
                   additional_kwargs={"output_config": {"effort": effort}, "cache_control": {"type": "ephemeral"}})
