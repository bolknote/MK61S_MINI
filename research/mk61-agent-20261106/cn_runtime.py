"""The executor uses distilled instructions on the first turn after SPEC review."""

import re

from aq_protocol import header_ids, prompt_ids
from bj_runtime import Session as Parent
from bl_prompt import compact
from cm_runtime import ASSISTANT, REVIEW_GUIDE, REVIEW_OBSERVATION, WRITE_SLACK
from ha_protocol import bytes_text


CONTEXT = 1024
# A 31-node SPEC has at most 16 constant leaves. Every constant uses two bytes.
MAX_SPEC_BYTES = 1 + 31 + 16
COMPACT_SUFFIX = "После пересмотра SPEC доступны WRITE, RUN, DONE и UNSURE.\n" + ASSISTANT
REMAINING = re.compile(r"(?:^|\n)(Осталось действий: \d+\.) Исправление: [^\n]*")


def limit(tokenizer):
    # Two hex digits per byte, a space between bytes, then the terminator.
    return CONTEXT - len(header_ids(tokenizer, "write")) - 3 * MAX_SPEC_BYTES


def needs_room(prompt, revised_body, tokenizer):
    tokens = len(prompt_ids(tokenizer, prompt))
    body = tokenizer.encode(bytes_text(revised_body), add_special_tokens=False)
    return tokens > CONTEXT - len(header_ids(tokenizer, "write")) - len(body) - 1 - WRITE_SLACK


def shortened(prompt, question, tokenizer):
    # The user condition can be multiline. Do not apply instruction replacements to it.
    start = prompt.index("Задача: ") + len("Задача: ")
    stop = start + len(question.strip())
    assert prompt[start:stop] == question.strip()
    state = prompt[stop:]
    suffix = REVIEW_GUIDE + ASSISTANT
    assert state.endswith(suffix)
    state = state[:-len(suffix)] + COMPACT_SUFFIX
    state = state.replace(REVIEW_OBSERVATION, "\nЭмулятор: SPEC_REVISED.\n", 1)
    state = REMAINING.sub(r"\n\1", state, count=1)
    prefix = prompt[:start] + question.strip() + state
    result = compact(prefix, question)
    if len(prompt_ids(tokenizer, result)) > limit(tokenizer):
        result = compact(prefix, question, level=2)
    return result


class Session(Parent):
    def __init__(self, *args, tokenizer, phase_only=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.tokenizer = tokenizer
        self.phase_only = phase_only

    def request(self):
        prompt = super().request()
        if self.history and self.history[-1]["kind"] == "replan":
            if not self.phase_only or needs_room(prompt, self.history[-1]["body"], self.tokenizer):
                result = shortened(prompt, self.task["task"], self.tokenizer)
                if len(prompt_ids(self.tokenizer, result)) <= limit(self.tokenizer):
                    return result
        return prompt
