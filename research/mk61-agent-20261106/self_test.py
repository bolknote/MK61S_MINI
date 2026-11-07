"""Integration checks for real execution, tool control and independent grading."""
import json
from pathlib import Path
import unittest

from emulator import Emulator
from harness import agent_run, check_program, extract_code
from tasks import BUILD, elementary_tasks, program_text


class HarnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.emulator = Emulator()

    def test_reference_programs_execute_on_independent_cases(self):
        for task in elementary_tasks():
            with self.subTest(task=task["id"]):
                result = check_program(self.emulator, task["reference_code"], task["public_tests"] + task["hidden_tests"])
                self.assertTrue(result["pass"])

    def test_model_success_claim_does_not_pass(self):
        result = agent_run(elementary_tasks()[2], lambda _: "<done/> PASS", self.emulator)
        self.assertFalse(result["pass"])
        self.assertEqual(result["valid_tool_calls"], 0)

    def test_trace_then_repair_uses_actual_feedback(self):
        task = elementary_tasks()[2]
        task["initial_code"] = [0x60, 0x61, 0x11, 0x50]
        prompts = []

        def generate(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return "<plan>проверить код</plan><trace/>"
            return "<write>" + program_text(task["reference_code"]) + "</write><run/>"

        result = agent_run(task, generate, self.emulator)
        self.assertTrue(result["pass"])
        self.assertEqual(result["valid_tool_calls"], 2)
        self.assertIn("TRACE", prompts[1])
        self.assertIn("11", prompts[1])

    def test_public_examples_cannot_replace_hidden_tests(self):
        task = {"id": "constant-overfit", "kind": "synthesis", "task": "X=R0",
                "public_tests": [{"registers": {"R0": 0}, "expected_X": "0"}],
                "hidden_tests": [{"registers": {"R0": 7}, "expected_X": "7"}]}
        result = agent_run(task, lambda _: "<write>0D 50</write><run/>", self.emulator)
        self.assertTrue(result["public_pass"])
        self.assertFalse(result["pass"])

    def test_memory_write_is_checked(self):
        task = {"registers": {"R0": 5}, "expected_X": "5", "expected_registers": {"R4": "5"}}
        self.assertFalse(check_program(self.emulator, [0x60, 0x50], [task])["pass"])
        self.assertTrue(check_program(self.emulator, [0x60, 0x44, 0x50], [task])["pass"])

    def test_loop_is_bounded(self):
        result = self.emulator.run([0x51, 0x00], max_commands=12)
        self.assertEqual(result["status"], "limit")
        self.assertEqual(result["commands"], 12)

    def test_malformed_code_is_rejected(self):
        for reply in ["<write>60 gg 50</write>", "<write>6 50</write>", "<write>../../x</write>",
                      "<write>" + "50 " * 106 + "</write>"]:
            self.assertIsNone(extract_code(reply))

    def test_expression_family_partitions_are_disjoint(self):
        training = [json.loads(x) for x in (BUILD / "training/sft-combined-v2.jsonl").read_text().splitlines()]
        families = {r["family"] for r in training if r["source"] == "verified_expression_generator"}
        for split in ["validation", "test"]:
            rows = [json.loads(x) for x in (BUILD / f"tasks/{split}.jsonl").read_text().splitlines()]
            self.assertFalse(families & {r["family"] for r in rows})


if __name__ == "__main__":
    unittest.main()
