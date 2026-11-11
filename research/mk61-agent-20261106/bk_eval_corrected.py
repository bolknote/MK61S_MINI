"""Future simulations with independent per-episode generation budgets.

The original BJ evaluator remains immutable for reproducing its first report.
Use one process per evaluation, as required by the underlying emulator.
"""
import bj_eval as original
from bk_independent_generate import generate


def evaluate(model, tokenizer, split):
    saved = original.generate
    saved_core = original.core.generate
    original.generate = generate
    original.core.generate = generate
    try:
        return original.evaluate(model, tokenizer, split)
    finally:
        original.generate = saved
        original.core.generate = saved_core
