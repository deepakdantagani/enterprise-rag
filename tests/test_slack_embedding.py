"""SLACK-11a: embed_model(), Qwen3-Embedding-0.6B through LlamaIndex's OllamaEmbedding.

Run: uv run python -m unittest discover tests
"""
import doctest
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.ollama import OllamaEmbedding

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.slack import embedding as embedding_module  # noqa: E402
from pipeline.slack.documents import thread_documents  # noqa: E402
from pipeline.slack.embedding import EmbedSettings, check_dimensions, embed_model, embed_settings, window_guard  # noqa: E402
from pipeline.slack.messages import split_messages  # noqa: E402
from pipeline.slack.nodes import SlackThreadParser  # noqa: E402

LARGEST = ROOT / "tests/fixtures/slack_largest"  # the largest real thread: 4,143 cl100k, 4,470 Qwen tokens
DEFAULT = embed_settings({})  # the defaults, whatever this machine's environment or .env says
EMBED_VARIABLES = ("EMBED_PROVIDER", "EMBED_MODEL", "EMBED_BASE_URL", "EMBED_WINDOW", "EMBED_DIMENSIONS")


def cosine(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b)) / (sum(x * x for x in a) ** 0.5 * sum(y * y for y in b) ** 0.5)


def model_is_served() -> bool:
    try:
        with urllib.request.urlopen(f"{embed_model(DEFAULT).base_url}/api/tags", timeout=2) as response:
            return any(model["name"] == DEFAULT.model for model in json.load(response)["models"])
    except Exception:  # no Ollama, no model, or an unexpected reply: skip, do not break the import
        return False


class SettingsFromTheEnvironment(unittest.TestCase):
    def test_with_nothing_set_it_is_qwen3_embedding_on_the_local_ollama(self):
        self.assertEqual(DEFAULT, EmbedSettings(
            provider="ollama", model="qwen3-embedding:0.6b", base_url="", window=32_768, dimensions=1024))

    def test_each_setting_comes_from_its_environment_variable(self):
        self.assertEqual(embed_settings({"EMBED_PROVIDER": "ollama", "EMBED_MODEL": "bge-m3",
                                         "EMBED_BASE_URL": "http://gpu-box:11434",
                                         "EMBED_WINDOW": "8192", "EMBED_DIMENSIONS": "1024"}),
                         EmbedSettings("ollama", "bge-m3", "http://gpu-box:11434", 8192, 1024))

    def test_a_window_or_dimension_that_is_not_a_positive_number_is_an_error(self):
        for bad in ({"EMBED_WINDOW": "32k"}, {"EMBED_DIMENSIONS": "0"}, {"EMBED_WINDOW": "-1"}, {"EMBED_WINDOW": "\u00b2"}):
            with self.assertRaisesRegex(ValueError, "must be a positive whole number", msg=bad):
                embed_settings(bad)

    def test_a_env_file_is_read_and_a_real_environment_variable_wins_over_it(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("EMBED_MODEL=bge-m3\nEMBED_WINDOW=8192\n")
            others = {name: value for name, value in os.environ.items() if name not in EMBED_VARIABLES}
            with mock.patch.dict(os.environ, others, clear=True), mock.patch.object(embedding_module, "ENV_FILE", env_file):
                self.assertEqual(embed_settings()[1:4], ("bge-m3", "", 8192))
            with mock.patch.dict(os.environ, {**others, "EMBED_MODEL": "nomic-embed-text"}, clear=True), \
                    mock.patch.object(embedding_module, "ENV_FILE", env_file):
                self.assertEqual(embed_settings().model, "nomic-embed-text")

    def test_an_unknown_provider_is_an_error_naming_the_ones_we_have(self):
        with self.assertRaisesRegex(ValueError, r"EMBED_PROVIDER 'openai' is not one of \['ollama'\]"):
            embed_settings({"EMBED_PROVIDER": "openai"})
        with self.assertRaisesRegex(ValueError, r"EMBED_PROVIDER 'openai' is not one of \['ollama'\]"):
            embed_model(DEFAULT._replace(provider="openai"))

    def test_every_variable_is_documented_in_env_example(self):
        example = (ROOT / ".env.example").read_text()
        for variable in embedding_module.DEFAULTS:
            self.assertIn(f"{variable}=", example)

    def test_doctests(self):
        self.assertEqual(doctest.testmod(embedding_module).failed, 0)


class TheModel(unittest.TestCase):
    def test_it_is_a_llamaindex_embedding_the_rest_of_the_pipeline_can_take_as_is(self):
        self.assertIsInstance(embed_model(DEFAULT), BaseEmbedding)

    def test_the_default_is_qwen3_embedding_on_the_local_ollama(self):
        model = embed_model(DEFAULT)
        self.assertIsInstance(model, OllamaEmbedding)
        self.assertEqual((model.model_name, model.base_url), ("qwen3-embedding:0.6b", "http://localhost:11434"))

    def test_ollama_is_given_the_model_s_full_window_explicitly(self):
        self.assertEqual(embed_model(DEFAULT).ollama_additional_kwargs, {"num_ctx": 32_768})

    def test_the_model_is_built_from_the_settings_it_is_given(self):
        model = embed_model(EmbedSettings("ollama", "bge-m3", "http://gpu-box:11434", 8192, 1024))
        self.assertEqual((model.model_name, model.base_url, model.ollama_additional_kwargs),
                         ("bge-m3", "http://gpu-box:11434", {"num_ctx": 8192}))

    def test_threads_are_embedded_without_an_instruction(self):
        self.assertIsNone(embed_model(DEFAULT).text_instruction)
        self.assertIsNone(embed_model(DEFAULT).query_instruction)  # SLACK-11c sets the one for questions


class TheGuardFollowsTheWindow(unittest.TestCase):
    def test_the_guard_ceiling_is_the_window_less_a_margin_for_the_tokenizer(self):
        self.assertEqual(window_guard(DEFAULT).max_tokens, 26_214)  # 32,768 x 0.8
        self.assertEqual(window_guard(DEFAULT._replace(window=512)).max_tokens, 409)

    def test_a_small_model_s_window_refuses_long_threads_instead_of_truncating_them(self):
        [node] = SlackThreadParser().get_nodes_from_documents(list(thread_documents(LARGEST)))
        with self.assertRaisesRegex(ValueError, "over the embedding window of 409 tokens"):
            window_guard(DEFAULT._replace(window=512))([node])
        self.assertEqual(window_guard(DEFAULT)([node]), [node])


class TheDimensionsAreChecked(unittest.TestCase):
    def test_a_model_that_returns_the_configured_size_passes(self):
        check_dimensions(MockEmbedding(embed_dim=1024), DEFAULT)

    def test_a_model_that_returns_another_size_stops_before_anything_is_stored(self):
        with self.assertRaisesRegex(ValueError, "EMBED_DIMENSIONS is 1024 but qwen3-embedding:0.6b returns 768"):
            check_dimensions(MockEmbedding(embed_dim=768), DEFAULT)


@unittest.skipUnless(model_is_served(), "Ollama with qwen3-embedding:0.6b not running (ollama pull qwen3-embedding:0.6b)")
class AgainstTheRealModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        [cls.node] = SlackThreadParser().get_nodes_from_documents(list(thread_documents(LARGEST)))
        cls.text = cls.node.get_content(MetadataMode.EMBED)
        cls.model = embed_model(DEFAULT)

    def test_a_vector_has_1024_numbers_and_is_near_identical_on_every_run(self):
        # Not bit-for-bit: the first call after Ollama loads the model, and the same text at another
        # place in a batch, differ by up to 9e-05 per number (cosine 0.9999997). Measured 2026-09-26.
        first = self.model.get_text_embedding(self.text)
        self.assertEqual(len(first), DEFAULT.dimensions)
        check_dimensions(self.model, DEFAULT)
        again, in_a_batch = self.model.get_text_embedding_batch([self.text, "general\n\nana: hi\n", self.text])[::2]
        for other in (again, in_a_batch, self.model.get_text_embedding(self.text)):
            self.assertGreater(cosine(first, other), 0.9999)

    def test_the_end_of_the_largest_thread_reaches_the_vector(self):
        # Dropping the last message (316 chars, "Sam: Closing thread summary: ...") moves the vector to
        # cosine 0.9995, far past the run-to-run noise (0.9999997). With the window cut to 2,048 the
        # model never reads it: cosine 1.0. So a truncating setup fails this test.
        last_message = split_messages(self.node.text).messages[-1].rstrip("\n")
        self.assertTrue(self.text.endswith(last_message))
        without_it = self.text[: -len(last_message)]
        truncating = embed_model(DEFAULT._replace(window=2048))
        self.assertLess(cosine(self.model.get_text_embedding(self.text), self.model.get_text_embedding(without_it)), 0.9999)
        self.assertGreater(cosine(truncating.get_text_embedding(self.text), truncating.get_text_embedding(without_it)), 0.9999)


if __name__ == "__main__":
    unittest.main()
