"""RET-10e-a: claude_llm, the LlamaIndex Anthropic wrapper that works for Claude 5 ids, with prompt caching.

Run: uv run python -m unittest tests.test_eval_claude
"""
import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.eval import claude as claude_module  # noqa: E402
from pipeline.eval.claude import Claude5, claude_llm  # noqa: E402

SAMPLING = ("temperature", "top_p", "top_k")


class ClaudeLLM(unittest.TestCase):
    def test_a_claude_5_id_gets_metadata_instead_of_an_unknown_model_error(self):
        meta = claude_llm("claude-haiku-5-5", api_key="x").metadata
        self.assertEqual((meta.context_window, meta.is_function_calling_model, meta.is_chat_model, meta.model_name),
                         (1_000_000, True, True, "claude-haiku-5-5"))

    def test_a_model_the_library_knows_keeps_the_library_s_metadata(self):
        from llama_index.llms.anthropic import Anthropic
        ours, theirs = claude_llm("claude-3-haiku-20240307", api_key="x").metadata, Anthropic(model="claude-3-haiku-20240307", api_key="x").metadata
        self.assertEqual(ours.context_window, theirs.context_window)

    def test_the_request_has_no_sampling_parameters_for_any_model(self):
        for model in ("claude-haiku-5-5", "claude-sonnet-4-6"):
            kwargs = claude_llm(model, api_key="x")._get_all_kwargs()
            self.assertEqual([name for name in SAMPLING if name in kwargs], [], model)

    def test_the_request_carries_adaptive_thinking_the_effort_and_the_cache_field(self):
        kwargs = claude_llm("claude-haiku-5-5", api_key="x", effort="high")._get_all_kwargs()
        self.assertEqual((kwargs["thinking"], kwargs["output_config"], kwargs["cache_control"], kwargs["max_tokens"]),
                         ({"type": "adaptive"}, {"effort": "high"}, {"type": "ephemeral"}, 8_000))

    def test_the_effort_defaults_to_medium_and_max_tokens_can_be_set(self):
        kwargs = claude_llm("claude-haiku-5-5", api_key="x", max_tokens=2_000)._get_all_kwargs()
        self.assertEqual((kwargs["output_config"]["effort"], kwargs["max_tokens"]), ("medium", 2_000))

    def test_sampling_parameters_passed_per_call_are_dropped_too(self):
        self.assertNotIn("temperature", claude_llm("claude-haiku-5-5", api_key="x")._get_all_kwargs(temperature=0.0))

    def test_the_request_the_sdk_receives_on_chat_has_no_sampling_parameters_and_carries_the_cache_field(self):
        from unittest.mock import MagicMock
        from llama_index.core.llms import ChatMessage
        llm = claude_llm("claude-haiku-5-5", api_key="x")
        llm._client.messages.create = MagicMock(side_effect=RuntimeError("stop before the network"))
        with self.assertRaises(RuntimeError):
            llm.chat([ChatMessage(role="user", content="hi")])
        sent = llm._client.messages.create.call_args.kwargs
        self.assertEqual(([name for name in SAMPLING if name in sent], sent["cache_control"]), ([], {"type": "ephemeral"}))

    def test_it_is_the_library_component(self):
        from llama_index.llms.anthropic import Anthropic
        self.assertIsInstance(claude_llm("claude-haiku-5-5", api_key="x"), Anthropic)
        self.assertTrue(issubclass(Claude5, Anthropic))

    def test_doctests(self):
        self.assertEqual(doctest.testmod(claude_module).failed, 0)


if __name__ == "__main__":
    unittest.main()
