"""Use a complete independent parse and optionally compile as the first repair."""

from ar_spec import verify
from ay_codec import compile_spec
from cr_runtime import make_session as bounded_session
from cs_language import parse_task


def checked_program(spec, pool, vm, inputs):
    if spec is None or not inputs:
        return None
    try:
        program = compile_spec(spec, pool)
        if verify(vm, program, pool, spec, inputs)["status"] == "TESTED":
            return program
    except (ValueError, ArithmeticError, KeyError):
        pass
    return None


def make_session(decoder, direct=False):
    parent = bounded_session(decoder, use_compiler=True)

    class Session(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.direct_attempted = False
            self.direct_pending = False
            if not self.mechanical or self.required_spec is not None:
                return
            spec = parse_task(self.task["task"], self.task["angle"])
            if spec is None:
                return
            if self.awaiting_confirmation:
                # The original grammar can request clarification for a nested power.
                assert len(self.history) == 1 and self.history[-1]["kind"] == "needs_confirmation"
                self.history.pop()
                self.awaiting_confirmation = False
                self.abstained = False
                self.observation = None
            self.required_spec = spec
            self.replan_attempted = True
            self.use_independent_spec()

        def request(self):
            if (direct and not self.direct_attempted and self.required_spec is not None
                    and self.verify_current()["status"] == "FAIL"):
                self.direct_attempted = True
                candidate = checked_program(self.required_spec, self.pool, self.vm, self.independent_inputs)
                if candidate is not None:
                    self.direct_pending = True
                    return decoder.recovery_request("write", candidate, "compile_confirmed_spec")
            return super().request()

        def apply_action(self, action, body):
            if not self.direct_pending:
                return super().apply_action(action, body)
            self.direct_pending = False
            if action != "write":
                return self.reject_write("Прямой компилятор не вернул программу.")
            # Bypass the model's SPEC wire codec and keep the same checked-write transaction.
            arm = self.output_arm
            self.output_arm = "hex"
            try:
                result = super().apply_action(action, body)
            finally:
                self.output_arm = arm
            self.history[-1].update(direct_compiler=True, repair_source="compiler")
            return result

    return Session
