"""What API and worker check of the language model before they start work: a setting the model
cannot take, a context window that holds no document, an encoding they could not count with.
Each would fail a paid job halfway; none needs the key or the network."""

from app.llm.budget import check_context_window, load_tokenizer
from app.llm.client import check_reasoning_effort, context_tokens
from app.llm.settings import LLMSettings


def check_model_layer(settings: LLMSettings) -> None:
    """ValueError for a setting, TokenizerMissing for the encoding; the tokenizer is built here,
    off any event loop that would stand still while it builds."""
    check_reasoning_effort(settings)
    check_context_window(context_tokens(settings))
    load_tokenizer()
