"""Give the next executor action room after a successful SPEC review."""

from aq_protocol import header_ids, prompt_ids
from bj_runtime import Session as RecoverySession
from ha_protocol import bytes_text


REVIEW_GUIDE = (
    "DIAG 04 FF FF 00 00 означает ошибку гипотезы; затем повторный разбор условия без изменения программы.\n"
)
REVIEW_OBSERVATION = "\nЭмулятор: SPEC_REVISED. Это новая гипотеза условия; проверь программу.\n"
ASSISTANT = "Ассистент: <"
WRITE_SLACK = 8


class Session(RecoverySession):
    def __init__(self, *args, tokenizer, context, **kwargs):
        super().__init__(*args, **kwargs)
        self.tokenizer = tokenizer
        self.context = context
        self.write_header_tokens = len(header_ids(tokenizer, "write"))

    def request(self):
        prompt = super().request()
        if not self.history or self.history[-1]["kind"] != "replan":
            return prompt

        # The last SPEC supplies a size estimate. Leave room for the WRITE
        # header, its terminator, and a few additional HEX bytes.
        revised_body = bytes_text(self.history[-1]["body"])
        body_tokens = len(self.tokenizer.encode(revised_body, add_special_tokens=False))
        limit = self.context - self.write_header_tokens - body_tokens - 1 - WRITE_SLACK
        if len(prompt_ids(self.tokenizer, prompt)) <= limit:
            return prompt

        suffix = REVIEW_GUIDE + ASSISTANT
        if not prompt.endswith(suffix):
            return prompt
        prompt = prompt[:-len(suffix)] + ASSISTANT
        if len(prompt_ids(self.tokenizer, prompt)) > limit:
            before, marker, after = prompt.rpartition(REVIEW_OBSERVATION)
            if marker:
                prompt = before + "\nЭмулятор: SPEC_REVISED.\n" + after
        return prompt
