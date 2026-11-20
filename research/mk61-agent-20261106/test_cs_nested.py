"""Check explicit scope, refusal of extra instructions, and direct repair."""

from types import SimpleNamespace
import unittest

from ay_codec import compile_spec
from az_teacher import pool_for
from bl_spec import install
from bl_vm import CachedVM
from ci_runtime import power_key
from cn_data import tokenizer
from cs_language import parse_task
from cs_runtime import checked_program, make_session


TASK = "Какое значение даст разность значений (квадрат от R1) и (модуль от R2)? Ответ нужен в X и в регистре R4."
EXPR = ["-", ["square", "R1"], ["abs", "R2"]]
EXPECTED = {"angle": "DEG", "X": EXPR, "writes": {"R4": EXPR}}


class NestedGrammarTests(unittest.TestCase):
    def test_explicit_scopes(self):
        cases = (
            (TASK, EXPR, "R4"),
            ("Нужна программа МК-61 для следующего вычисления: натуральный логарифм от (синус от (модуль от RА)).",
             ["ln", ["sin", ["abs", "RA"]]], None),
            ("Вычти 1,75 из значения ((арктангенс от (обратная величина от R5)) с противоположным знаком).",
             ["-", ["neg", ["atan", ["reciprocal", "R5"]]], {"constant": "1.75"}], None),
            ("Посчитай, пожалуйста: степень с основанием (модуль от R1) и показателем (квадрат от R2).",
             ["pow", ["abs", "R1"], ["square", "R2"]], None),
            ("Найди: косинус от (сумма значений R2 и (синус от R3)). В градусах.",
             ["cos", ["+", "R2", ["sin", "R3"]]], None),
            ("К значению (квадрат от R1) добавь (синус от R2). Итог сохрани в R3.",
             ["+", ["square", "R1"], ["sin", "R2"]], "R3"),
            ("Значение (квадрат от R1) надо умножить на (модуль от R2).",
             ["*", ["square", "R1"], ["abs", "R2"]], None),
            ("Значение (косинус от (модуль от RА)) нужно умножить на 1,75.",
             ["*", ["cos", ["abs", "RA"]], {"constant": "1.75"}], None),
        )
        for text, expr, destination in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_task(text, "DEG"), {"angle": "DEG", "X": expr,
                                 "writes": {destination: expr} if destination else {}})

    def test_incomplete_or_ambiguous_conditions(self):
        cases = (
            "Вычисли косинус от (синус от R1.",
            "Вычисли квадрат от (R1). Затем прибавь 7.",
            "Вычисли косинус от (R2). Ответ нужен в X и в регистре R3. Запиши в R4.",
            "Вычисли синус от (R1). В радианах.",
            "Вычисли разность значений (R1) и R2 с противоположным знаком.",
            "Вычисли сумму значений (R1) и (R2). При ошибке верни ноль.",
            "Найди степень: (синус от R0).",
            "Извлеки (R1).",
            "Найди: (R1) плюс R2 умножить на R3.",
            "Вычисли косинус от (@0@).",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertIsNone(parse_task(text, "DEG"))


class DirectCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install()
        cls.vm = CachedVM(96)
        cls.tok = tokenizer()

    def session(self, correct=False, text=TASK, expected=EXPECTED):
        wrong_expr = ["+", *EXPR[1:]]
        wrong = {"angle": "DEG", "X": wrong_expr, "writes": {"R4": wrong_expr}}
        pool = pool_for(text)
        reference = compile_spec(expected, pool)
        body = reference if correct else compile_spec(wrong, pool)
        goal = {"id": "cs-local", "task": text, "spec": expected, "pool": pool,
                "public_inputs": [{"R1": "2.5", "R2": "-3"}, {"R1": "3", "R2": "4"}],
                "checker_inputs": [{"R1": "3.7", "R2": "-4.5", "R4": "99"}]}
        decoder = SimpleNamespace(tokenizers={"working": self.tok}, full_prompts={}, budgeted={},
                                  verified_request=lambda action, body: (action, body),
                                  recovery_request=lambda action, body, phase: (action, body, phase))
        return make_session(decoder, direct=True)(goal, body, self.vm, "spec", wrong, True), reference

    def test_direct_repair_runs_new_revision_before_done(self):
        session, reference = self.session()
        self.assertEqual(power_key(session.required_spec), power_key(EXPECTED))
        action, body, phase = session.request()
        self.assertEqual((action, body, phase), ("write", reference, "compile_confirmed_spec"))
        self.assertEqual(session.apply_action(action, body), "write")
        self.assertTrue(session.history[-1]["direct_compiler"])
        self.assertEqual(session.gate_checks, [])
        self.assertFalse(session.eligibility()[0])
        action, body = session.request()
        self.assertEqual(action, "run")
        session.apply_action(action, body)
        self.assertEqual(session.request(), ("done", []))
        self.assertEqual(session.apply_action("done", []), "done")
        self.assertEqual(session.body, reference)

    def test_decimal_comma_can_compile_without_a_pool_entry(self):
        text = "Вычти 1,75 из значения (квадрат от R1). Итог сохрани в R4."
        expected_expr = ["-", ["square", "R1"], {"constant": "1.75"}]
        expected = {"angle": "DEG", "X": expected_expr, "writes": {"R4": expected_expr}}
        session, reference = self.session(text=text, expected=expected)
        self.assertNotIn("1.75", session.pool)
        action, body, phase = session.request()
        self.assertEqual((action, body, phase), ("write", reference, "compile_confirmed_spec"))
        self.assertEqual(session.apply_action(action, body), "write")
        self.assertEqual(session.body, reference)
        self.assertEqual(session.verify_current()["status"], "TESTED")

    def test_already_correct_skips_compiler(self):
        session, reference = self.session(correct=True)
        self.assertEqual(session.request(), ("done", []))
        self.assertEqual(session.body, reference)
        self.assertFalse(session.direct_attempted)

    def test_complete_nested_power_resolves_initial_confirmation(self):
        text = "Посчитай, пожалуйста: степень с основанием (модуль от R1) и показателем (модуль от R2)."
        expected = {"angle": "DEG", "X": ["pow", ["abs", "R1"], ["abs", "R2"]], "writes": {}}
        session, reference = self.session(text=text, expected=expected)
        self.assertFalse(session.awaiting_confirmation)
        self.assertEqual(session.history, [])
        self.assertEqual(session.request(), ("write", reference, "compile_confirmed_spec"))

    def test_failed_candidate_leaves_program_and_returns_to_executor(self):
        session, _ = self.session()
        original = session.body.copy()
        session.request()
        self.assertEqual(session.apply_action("write", original), "write_rejected")
        self.assertFalse(session.abstained)
        self.assertEqual(session.body, original)
        self.assertEqual(session.output_arm, "spec")
        self.assertIsInstance(session.request(), str)

    def test_primary_route_requires_emulator_evidence(self):
        pool = pool_for(TASK)
        self.assertIsNone(checked_program(EXPECTED, pool, self.vm, []))
        self.assertIsNotNone(checked_program(EXPECTED, pool, self.vm, [{"R1": "1", "R2": "3"}]))
        div_zero = {"angle": "DEG", "X": ["/", "R1", "R2"], "writes": {}}
        self.assertIsNone(checked_program(div_zero, pool, self.vm, [{"R1": "1", "R2": "0"}]))


if __name__ == "__main__":
    unittest.main()
