"""Give a disproved program one repair request before stopping or compiling."""

from aq_protocol import prompt_ids
from ay_codec import encode
from bl_prompt import fit
from ci_runtime import power_key
from cn_runtime import limit
from cq_runtime import make_session as previous_session


COUNTEREXAMPLES = frozenset(("COUNTEREXAMPLE", "ASSEMBLY", "EXECUTION"))


class WriteRequest(str):
    """An executor prompt whose next action is selected by the harness."""


def make_session(decoder, use_compiler=False):
    parent = previous_session(decoder, fit_long_prompts=True)
    tokenizer = decoder.tokenizers["working"]

    class Session(parent):
        def __init__(self, *args, **kwargs):
            self.disproved = set()
            self.next_recovery = None
            self.requested_recovery = None
            super().__init__(*args, **kwargs)

        def verification_key(self):
            spec = None if self.declared_spec is None else power_key(self.declared_spec)
            return tuple(self.body or ()), spec

        def schedule(self, phase):
            self.next_recovery = self.verification_key(), phase

        def request(self):
            scheduled = self.next_recovery
            self.next_recovery = None
            if scheduled is None or scheduled[0] != self.verification_key():
                return super().request()

            phase = scheduled[1]
            self.requested_recovery = phase
            if phase == "model":
                prompt = super().request()
                count = len(prompt_ids(tokenizer, prompt))
                if count > limit(tokenizer):
                    old = prompt
                    prompt, info = fit(old, self.task["task"], tokenizer)
                    if not info["fits"]:
                        return decoder.recovery_request("unsure", [], "write_has_no_room")
                    decoder.budgeted[prompt] = count
                return WriteRequest(prompt)
            if phase == "compiler":
                try:
                    body = encode(self.required_spec, self.pool)
                except (ValueError, ArithmeticError, KeyError):
                    return decoder.recovery_request("unsure", [], "compile_unavailable")
                return decoder.recovery_request("write", body, "compile_confirmed_spec")
            return decoder.recovery_request("unsure", [], phase)

        def request_confirmation(self):
            super().request_confirmation()
            if self.declared_spec is None:
                self.observation = "Уточните требуемое вычисление и место записи результата."
                self.history[-1]["observation"] = self.observation

        def apply_recovery(self, phase, action, body):
            if phase == "clarify":
                self.request_confirmation()
                return "needs_confirmation"
            if phase == "stop":
                return super().apply_action("unsure", [])
            if action == "write":
                try:
                    result = super().apply_action(action, body)
                except (ValueError, ArithmeticError) as error:
                    result = self.reject_write(str(error))
            else:
                reason = ("Команда WRITE не завершилась." if phase == "model" else
                          "Подтверждённую формулу не удалось закодировать.")
                result = self.reject_write(reason)
            self.history[-1]["repair_source"] = phase
            if result != "write":
                self.schedule("compiler" if use_compiler and phase == "model" else "stop")
            return result

        def apply_action(self, action, body):
            if self.requested_recovery is not None:
                phase = self.requested_recovery
                self.requested_recovery = None
                return self.apply_recovery(phase, action, body)

            if action == "done" and self.verification_key() in self.disproved:
                self.history.append({"kind": "done_blocked", "revision": self.revision,
                                     "observation": "Для текущей программы уже найден контрпример."})
                if self.next_recovery is None:
                    self.schedule("stop" if self.required_spec is not None else "clarify")
                return "done_blocked"
            result = super().apply_action(action, body)
            if result != "done_rejected":
                return result

            verdict = self.gate_checks[-1]
            reason = verdict["reason"]
            if reason == "PUBLIC_RUNS" and verdict["missing"]:
                # The inherited cycle runs missing public tests on this revision.
                return result
            if reason in COUNTEREXAMPLES or (reason == "PUBLIC_RUNS" and verdict["failed"]):
                self.disproved.add(self.verification_key())
                self.schedule("model" if self.required_spec is not None else "clarify")
            elif reason in ("SPEC_DOMAIN", "SPEC_UNAVAILABLE"):
                if self.required_spec is None and not self.replan_attempted:
                    self.pending_replan = True
                else:
                    self.schedule("clarify")
            return result

    return Session
