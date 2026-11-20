"""Choose and verify a short-path program before committing a change."""

from ar_spec import infer, verify
from ay_codec import compile_spec
from ce_short_path import spec_key


def checked_program(independent, declared, current, angle, pool, checks, vm, *, prefer_parser):
    """Use only the two parses, the current program, and runtime check inputs."""
    if independent is None:
        return None, "unsupported_text"

    agrees = declared is not None and spec_key(independent) == spec_key(declared)
    if not agrees and not prefer_parser:
        return None, "spec_disagrees"

    if current is not None:
        result = verify(vm, current, pool, independent, checks)
        if result["status"] == "TESTED":
            try:
                implied = infer(current, pool, angle)
            except (ValueError, ArithmeticError, KeyError):
                return None, "current_structure_unknown"
            if spec_key(implied) == spec_key(independent):
                return current, "kept_program"
            return None, "current_structure_differs"
        if result["status"] != "FAIL":
            return None, "current_check_unknown"

    # When the two SPECs agree, retain the existing compilation behavior.
    source = declared if agrees else independent
    try:
        candidate = compile_spec(source, pool)
    except (ValueError, ArithmeticError):
        return None, "compile_failed"
    if verify(vm, candidate, pool, independent, checks)["status"] != "TESTED":
        return None, "candidate_check_failed"
    return candidate, "compiled_program"
