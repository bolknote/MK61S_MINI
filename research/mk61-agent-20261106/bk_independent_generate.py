"""One episode's output budget must not depend on another padded prompt.

Retain the original single-episode decoding, grammar, weights and 1024 limit.
This also matches the intended single-agent calculator execution.
"""
from aq_eval import generate as original_generate


def generate(model, tokenizer, prompts, forced_action=None):
    return [original_generate(model, tokenizer, [prompt], forced_action=forced_action)[0] for prompt in prompts]
