"""Stage an exact formula for confirmation and verify programs before a commit."""

from copy import deepcopy
from dataclasses import dataclass
import json

from ar_spec import expression_text, verify
from ay_codec import compile_spec


ANGLES = {"DEG": "градусы", "RAD": "радианы", "GRAD": "грады"}


@dataclass(frozen=True)
class FormulaPreview:
    serialized_spec: str

    @classmethod
    def from_spec(cls, spec):
        if spec is None or spec.get("angle") not in ANGLES or "X" not in spec:
            return None
        if len(spec["writes"]) > 1 or any(value != spec["X"] for value in spec["writes"].values()):
            return None
        return cls(json.dumps(spec, ensure_ascii=False, sort_keys=True))

    def spec(self):
        return json.loads(self.serialized_spec)

    def text(self):
        spec = self.spec()
        formula = expression_text(spec["X"])
        destination = next(iter(spec["writes"]), None)
        lines = [f"X = {formula}", f"Углы — {ANGLES[spec['angle']]}"]
        if destination is None:
            lines.append("Регистры памяти сохраняются.")
        else:
            lines.append(f"Записать тот же результат в {destination}. Остальные регистры сохраняются.")
        lines.append("Подтверждаете формулу и место записи?")
        return "\n".join(lines)


def after_confirmation(preview, accepted, current, pool, checks, vm):
    if accepted is None:
        return None, "awaiting_confirmation"
    if accepted is False:
        return None, "rejected_formula"
    if accepted is not True:
        raise ValueError("Expected an explicit response to the formula preview")
    if not checks:
        raise ValueError("Expected runtime inputs for program verification")

    spec = preview.spec()
    if current is not None:
        status = verify(vm, current, pool, spec, checks)["status"]
        if status == "TESTED":
            return current, "kept_program"
        if status != "FAIL":
            return None, "current_check_unknown"
    try:
        candidate = compile_spec(spec, pool)
    except (ValueError, ArithmeticError):
        return None, "compile_failed"
    if verify(vm, candidate, pool, spec, checks)["status"] != "TESTED":
        return None, "candidate_check_failed"
    return candidate, "compiled_program"


def confirmed_session(base):
    class ConfirmedSession(base):
        def __init__(self, goal, current, vm, arm, declared, gate):
            super().__init__(goal, current, vm, arm, declared, gate)
            self.confirmed_spec = deepcopy(declared)

        def apply_action(self, action, body):
            if action == "done":
                assert self.declared_spec == self.confirmed_spec
            result = super().apply_action(action, body)
            # The full cycle can continue repairing code under the approved formula.
            # A new interpretation requires its own confirmation.
            if self.pending_replan:
                self.pending_replan = False
                self.replan_attempted = True
                self.observation = "SPEC уже подтверждена. Проверь программу по этой формуле."
                self.history[-1]["observation"] = self.observation
            return result

    return ConfirmedSession
