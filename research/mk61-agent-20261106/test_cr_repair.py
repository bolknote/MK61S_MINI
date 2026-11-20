"""Test the transitions of the bounded repair loop with a real emulator."""

from types import SimpleNamespace
import unittest

from aq_protocol import prompt_ids
from ay_codec import compile_spec, encode
from az_teacher import pool_for
from bl_spec import install
from bl_vm import CachedVM
from cn_data import tokenizer
from cn_runtime import limit
from cr_runtime import WriteRequest, make_session
from test_cq_harness import power


class BoundedRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install()
        cls.tok = tokenizer()
        cls.vm = CachedVM(96)

    def session(self, use_compiler=False, known=True, correct=False):
        text = ("Вычисли степень с основанием 2.5 и показателем 10. Запиши ответ в R4." if known
                else "Сделай вычисление по моему правилу и выведи его результат.")
        spec = power("2.5", "10")
        other = power("2.5", "2.5")
        pool = pool_for(text + " 2.5 10")
        body = compile_spec(spec if correct else other, pool)
        goal = {"id": "bounded-local", "task": text, "spec": spec, "pool": pool,
                "public_inputs": [{"X": "0.5", "R4": "4"}, {"X": "0.3", "R4": "8"}],
                "checker_inputs": [{"X": "0.3", "R4": "15", "R3": "2"}]}
        decoder = SimpleNamespace(tokenizers={"working": self.tok}, full_prompts={}, budgeted={},
                                  verified_request=lambda action, body: (action, body),
                                  recovery_request=lambda action, body, phase: (action, body, phase))
        session = make_session(decoder, use_compiler)(goal, body, self.vm, "spec", other, True)
        return session, spec, other

    def finish_write(self, session):
        self.assertFalse(session.eligibility()[0])
        action, body = session.request()
        self.assertEqual(action, "run")
        session.apply_action(action, body)
        self.assertEqual(session.request(), ("done", []))
        self.assertEqual(session.apply_action("done", []), "done")
        self.assertTrue(session.finished)

    def test_repeated_claim_keeps_one_pending_repair(self):
        session, spec, _ = self.session()
        self.assertEqual(session.apply_action("done", []), "done_rejected")
        self.assertEqual(session.apply_action("done", []), "done_blocked")
        self.assertEqual(len(session.gate_checks), 1)
        prompt = session.request()
        self.assertIsInstance(prompt, WriteRequest)
        self.assertLessEqual(len(prompt_ids(self.tok, prompt)), limit(self.tok))
        self.assertEqual(session.apply_action("write", encode(spec, session.pool)), "write")
        self.assertEqual(session.history[-1]["repair_source"], "model")
        self.finish_write(session)

    def test_invalid_proposal_is_transactional_and_stops(self):
        session, _, other = self.session()
        original = session.body.copy()
        session.apply_action("done", [])
        self.assertIsInstance(session.request(), WriteRequest)
        self.assertEqual(session.apply_action("write", encode(other, session.pool)), "write_rejected")
        self.assertEqual(session.body, original)
        self.assertEqual(session.revision, 0)
        self.assertEqual(session.request(), ("unsure", [], "stop"))
        self.assertEqual(session.apply_action("unsure", []), "unsure")

    def test_compiler_repairs_after_decoder_failure(self):
        session, spec, _ = self.session(use_compiler=True)
        session.apply_action("done", [])
        self.assertIsInstance(session.request(), WriteRequest)
        self.assertEqual(session.apply_action("unsure", []), "write_rejected")
        action, body, phase = session.request()
        self.assertEqual((action, body, phase), ("write", encode(spec, session.pool), "compile_confirmed_spec"))
        self.assertEqual(session.apply_action(action, body), "write")
        self.assertEqual(session.history[-1]["repair_source"], "compiler")
        self.finish_write(session)

    def test_counterexample_against_unconfirmed_formula_requests_confirmation(self):
        session, _, _ = self.session(use_compiler=True, known=False, correct=True)
        original = session.body.copy()
        self.assertIsNone(session.required_spec)
        self.assertEqual(session.apply_action("done", []), "done_rejected")
        self.assertEqual(session.request(), ("unsure", [], "clarify"))
        self.assertEqual(session.apply_action("unsure", []), "needs_confirmation")
        self.assertIn("Подтверждаете формулу", session.observation)
        self.assertEqual(session.body, original)

    def test_missing_public_test_precedes_repair(self):
        session, _, _ = self.session()
        session.runs.pop(1)
        self.assertEqual(session.apply_action("done", []), "done_rejected")
        self.assertEqual(session.pending_runs, [1])
        self.assertIsNone(session.next_recovery)
        session.apply_action("run", [session.pending_runs.pop(0)])
        self.assertEqual(session.apply_action("done", []), "done_rejected")
        self.assertIsInstance(session.request(), WriteRequest)


if __name__ == "__main__":
    unittest.main()
