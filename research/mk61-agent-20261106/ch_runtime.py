"""Request one new translation of the original task after an explicit refusal."""

from dataclasses import dataclass

from ay_codec import to_program
from ay_runtime import goal_state, render
from bj_runtime import render as render_replan
from ce_short_path import spec_key
from cg_runtime import FormulaPreview


REJECTED_NOTE = (
    "Пользователь отклонил предыдущую формулу. Заново разбери исходное условие. "
    "Проверь порядок операций, знаки, константы и регистр назначения. Выдай SPEC.\n"
)


@dataclass(frozen=True)
class RetryTranslation:
    prompt: str
    generation: dict
    reason: str
    preview: FormulaPreview | None = None


def retry_after_refusal(task, angle, pool, refused, response, generate, *, mention_refusal):
    if response is not False:
        raise ValueError("A new translation requires an explicit refusal")
    # Only fields already visible in the original translation are passed in.
    view = {"id": "formula-retry", "task": task, "spec": {"angle": angle}, "pool": pool, "public_inputs": []}
    state = goal_state(view)
    if mention_refusal:
        prompt = render(state, "spec").removesuffix("Ассистент: <") + REJECTED_NOTE + "Ассистент: <"
    else:
        state["replan"] = True
        prompt = render_replan(state, "spec")
    generation = generate(prompt)
    if generation.get("codec_error") or generation.get("action") != "write":
        return RetryTranslation(prompt, generation, "decode_failed")
    try:
        _, spec = to_program(generation["body"], pool, angle, "spec")
        preview = FormulaPreview.from_spec(spec)
        if preview is None:
            return RetryTranslation(prompt, generation, "decode_failed")
        if spec_key(spec) == spec_key(refused.spec()):
            return RetryTranslation(prompt, generation, "same_formula")
    except (ValueError, ArithmeticError, RuntimeError):
        return RetryTranslation(prompt, generation, "decode_failed")
    return RetryTranslation(prompt, generation, "new_formula", preview)
