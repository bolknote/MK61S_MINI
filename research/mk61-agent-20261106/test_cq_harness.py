"""Exercise role ordering, confirmation, transactional writes, and the context guard."""

from types import SimpleNamespace
import unittest

from aq_protocol import ACTION_ID, prompt_ids
from ay_codec import compile_spec, encode
from ay_common import read, rows
from az_teacher import pool_for
from bl_spec import install
from bl_vm import CachedVM
from ci_runtime import power_key
from cn_data import tokenizer
from cn_runtime import limit
from cp_data import ROOT as LONG_RUN
from cq_language import independent_spec
from cq_runtime import fit_executor, make_session


def power(a, b, store="R4"):
    expr = ["pow", {"constant": a}, {"constant": b}]
    return {"X": expr, "writes": {store: expr} if store else {}, "angle": "DEG"}


class HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install()
        cls.tok = tokenizer()
        cls.vm = CachedVM(96)

    def test_explicit_operands_and_complete_condition(self):
        examples = (
            ("Вычисли степень с основанием 2,5 и показателем 10. Запиши ответ в R4.", power("2.5", "10")),
            ("Показатель степени равен -2, основание равно 2,5. Вычисли степень. Запиши в Р А.",
             power("2.5", "-2", "RA")),
            ("Основание степени — 10, показатель — 2.5. Какой получится результат?", power("10", "2.5", "")),
            ("Найди, чему равна степень с показателем 2,5 и основанием 10.", power("10", "2.5", "")),
            ("Нужна программа МК-61 для следующего вычисления: десять в степени 2.5. Ответ нужен в X и в регистре R4.",
             power("10", "2.5")),
        )
        for text, expected in examples:
            with self.subTest(text=text):
                self.assertEqual(power_key(independent_spec(text, "DEG")), power_key(expected))
        unsupported = (
            "Вычисли степень с основанием 2,5. Запиши ответ в R4.",
            "Показатель степени равен 10, показатель равен 2.5. Вычисли степень.",
            "Основание равно 10, показатель равен 2.5. Затем прибавь 1. Вычисли степень.",
            "Найди степень с основанием 2.5 и показателем 10. Запиши в R4. Запиши в R3.",
            "Вычисли степень с основанием 2.5 и показателем 10. Режим в радианах.",
        )
        for text in unsupported:
            with self.subTest(text=text):
                self.assertIsNone(independent_spec(text, "DEG"))

    def fixture(self, text, start_correct):
        expected = power("2.5", "10")
        neural = power("2.5", "2.5")
        pool = pool_for(text + " 2.5 10")
        original = compile_spec(expected if start_correct else neural, pool)
        task = {"id": "local", "task": text, "spec": expected, "pool": pool,
                "public_inputs": [{"X": "0.5", "R4": "4"}, {"X": "0.3", "R4": "8"}],
                "checker_inputs": [{"X": "0.3", "R4": "15", "R3": "2"}]}
        decoder = SimpleNamespace(tokenizers={"working": self.tok}, full_prompts={}, budgeted={},
                                  verified_request=lambda action, body: (action, body))
        return make_session(decoder)(task, original, self.vm, "spec", neural, True), original, expected, neural

    def test_preserve_correct_code_before_first_model_action(self):
        text = "Вычисли степень с основанием 2.5 и показателем 10. Запиши ответ в R4."
        session, original, expected, neural = self.fixture(text, True)
        self.assertEqual(power_key(session.declared_spec), power_key(expected))
        self.assertEqual(power_key(session.initial_spec), power_key(neural))
        self.assertEqual(session.request(), ("done", []))
        self.assertEqual(session.apply_action("write", encode(neural, session.pool)), "write_rejected")
        self.assertEqual(session.apply_action("done", []), "done")
        self.assertEqual(session.body, original)

    def test_verify_new_code_and_require_both_public_runs(self):
        text = "Основание степени равно 2.5, показатель равен 10. Запиши ответ в R4."
        session, original, expected, neural = self.fixture(text, False)
        self.assertEqual(session.apply_action("done", []), "done_rejected")
        self.assertEqual(session.apply_action("write", encode(neural, session.pool)), "write_rejected")
        self.assertEqual(session.body, original)
        self.assertEqual(session.apply_action("write", encode(expected, session.pool)), "write")
        self.assertFalse(session.eligibility()[0])
        action, body = session.request()
        self.assertEqual(action, "run")
        session.apply_action(action, body)
        self.assertEqual(session.request(), ("done", []))
        self.assertEqual(session.apply_action("done", []), "done")

    def test_request_confirmation_on_missing_named_operand(self):
        text = "Вычисли степень с основанием 2.5. Запиши ответ в R4."
        session, original, _, neural = self.fixture(text, True)
        self.assertTrue(session.awaiting_confirmation)
        self.assertIn("Подтверждаете формулу", session.history[-1]["observation"])
        self.assertRaises(ValueError, session.apply_action, "write", encode(neural, session.pool))
        self.assertEqual(session.body, original)

    def test_budget_previous_truncated_writes_without_cutting_state(self):
        tasks = {g["id"]: g for g in rows(LONG_RUN / "closed.jsonl")}
        run = read(LONG_RUN / "eval/closed-46221/full.json")
        found = 0
        for row in run["records"]:
            if not row["history"]:
                continue
            first = row["history"][0]
            gen = first.get("generation", {})
            if gen.get("codec_error") != "incomplete" or gen["generated_token_ids"][:1] != [ACTION_ID["write"]]:
                continue
            g = tasks[row["task_id"]]
            new = fit_executor(first["prompt"], g["task"], row["initial_spec"], g["pool"], self.tok)
            self.assertLessEqual(len(prompt_ids(self.tok, new)), limit(self.tok))
            for line in first["prompt"].splitlines():
                if line.startswith(("Задача: ", "Константы: ", "Открытые входы: ", "Текущая гипотеза: ", "0000:")):
                    self.assertIn(line, new)
            found += 1
        self.assertEqual(found, 17)


if __name__ == "__main__":
    unittest.main()
