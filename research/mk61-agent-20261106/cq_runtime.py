"""Verify explicit task intent before writes and completions, and budget long prompts."""

from copy import deepcopy
import re

from aq_protocol import prompt_ids
from ar_spec import verify
from ay_codec import encode, to_program
from bl_prompt import fit
from cg_runtime import FormulaPreview
from ci_runtime import power_key
from cn_review_check import make_session as previous_session
from cn_runtime import limit, needs_room
from cq_language import independent_spec, named_power
from hf_runtime import GUIDE


WRITE_NOTE = re.compile(r"(\nОсталось действий: \d+\. Исправление: WRITE с компактной спецификацией SPEC\.).*")


def fit_executor(prompt, question, spec, pool, tokenizer):
    """Compact only a prompt which needs more space for the WRITE payload."""
    try:
        estimate = encode(spec, pool) if spec is not None else None
    except (ValueError, ArithmeticError):
        estimate = None
    length = len(prompt_ids(tokenizer, prompt))
    budget = limit(tokenizer)
    if length <= budget or (estimate is not None and not needs_room(prompt, estimate, tokenizer)):
        return prompt

    start = prompt.index("Задача: ") + len("Задача: ")
    end = start + len(question.strip())
    assert prompt[start:end] == question.strip()
    guide, rest = prompt[:start], prompt[end:]
    guide = guide.replace(" Эмулятор сообщает фактическое состояние.", "", 1)
    rest = rest.replace("Заметки: " + GUIDE + "\n", "Заметки:\n", 1)
    rest = WRITE_NOTE.sub(r"\1", rest, count=1)
    short = guide + prompt[start:end] + rest
    if len(prompt_ids(tokenizer, short)) <= budget:
        return short
    short, info = fit(prompt, question, tokenizer)
    return short if info["fits"] else prompt


def make_session(decoder, fit_long_prompts=False):
    parent = previous_session(decoder, notify=False, correct_action=True)
    tokenizer = decoder.tokenizers["working"]

    class Session(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            text, angle = self.task["task"], self.task["angle"]
            self.required_spec = independent_spec(text, angle) if self.mechanical else None
            public = [segment["inputs"] for case in self.task["public_tests"] for segment in case["segments"]]
            self.independent_inputs = [*public, *self.checker_inputs]
            self.independent_revision = None
            self.independent_result = None
            self.awaiting_confirmation = False
            if self.required_spec is not None:
                self.replan_attempted = True
                self.use_independent_spec()
            elif self.mechanical and named_power(text):
                self.request_confirmation()

        def use_independent_spec(self):
            if self.declared_spec is None or power_key(self.declared_spec) != power_key(self.required_spec):
                self.declared_spec = deepcopy(self.required_spec)
                self.gate_cache = None

        def request_confirmation(self):
            preview = FormulaPreview.from_spec(self.declared_spec)
            self.awaiting_confirmation = True
            self.abstained = True
            self.observation = (preview.text() if preview else "Уточните основание, показатель и регистр результата.")
            self.history.append({"kind": "needs_confirmation", "revision": self.revision,
                                 "observation": self.observation})

        def verify_current(self):
            if not self.independent_inputs:
                return {"status": "UNKNOWN", "reason": "NO_CHECK_INPUTS"}
            if self.independent_revision != self.revision:
                self.independent_result = verify(self.vm, self.body, self.pool, self.required_spec,
                                                 self.independent_inputs)
                self.independent_revision = self.revision
            return self.independent_result

        def verified_action(self):
            if self.required_spec is None or not self.independent_inputs:
                return None
            if self.verify_current()["status"] != "TESTED":
                return None
            eligible, missing, failed = self.eligibility()
            if eligible:
                return "done", []
            if missing and not failed:
                return "run", [missing[0]]
            return None

        def request(self):
            if decision := self.verified_action():
                return decoder.verified_request(*decision)
            prompt = super().request()
            if fit_long_prompts and prompt not in decoder.full_prompts:
                short = fit_executor(prompt, self.task["task"], self.declared_spec, self.pool, tokenizer)
                if short != prompt:
                    decoder.budgeted[short] = len(prompt_ids(tokenizer, prompt))
                    return short
            return prompt

        def apply_replan(self, body):
            super().apply_replan(body)
            if self.required_spec is not None:
                self.use_independent_spec()

        def reject_write(self, reason):
            self.observation = "WRITE_REJECTED. " + reason
            self.history.append({"kind": "write_rejected", "revision": self.revision,
                                 "observation": self.observation, "reason": reason})
            return "write_rejected"

        def apply_action(self, action, body):
            if self.awaiting_confirmation:
                raise ValueError("CONFIRM_SPEC_FIRST")
            if self.required_spec is not None:
                if action == "write":
                    current = self.verify_current()["status"]
                    if current == "TESTED":
                        return self.reject_write("Текущая программа уже проверена.")
                    if current != "FAIL":
                        return self.reject_write("Текущую программу не удалось проверить.")
                    candidate, _ = to_program(body, self.pool, self.task["angle"], self.output_arm)
                    check = verify(self.vm, candidate, self.pool, self.required_spec, self.independent_inputs)
                    if check["status"] != "TESTED":
                        return self.reject_write("Программа расходится с независимо разобранным условием.")
                elif action == "done":
                    self.gate_cache = self.verify_current()
            return super().apply_action(action, body)

    return Session
