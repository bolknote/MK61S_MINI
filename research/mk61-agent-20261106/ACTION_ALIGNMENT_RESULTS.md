# 3M Q4: separate actions, diagnosis and iterative preferences

A bounded paired experiment, not a device release. The original harness-debug-v3 exports and exam results remain unchanged.

The model uses 7 existing reserved IDs for WRITE/PATCH/RUN/TRACE/DIAG/DONE/UNSURE, 23 HEX-body IDs and EOS: 31 output rows. Russian input vocabulary and all original input embedding rows are bit-identical. No parameter-count increase.

Training objective: CE(action) + 0.5 × per-example mean CE(HEX arguments) + 0.03 × language replay. Action CE is not divided by answer length. The preference arm additionally uses action-only DPO (beta=0.2, weight=0.5) with the fixed common warmup as reference; argument tokens use the same SFT objective in both arms.

Common format warmup: 600 updates. Each arm: 4 stages × 400 updates, batch128, Q4 from the first update. Both arms use identical SFT draw digests at every stage. The union of current-student training states is refreshed after warmup and stages1–3; validation and final tasks never enter these pools.

Offline process lessons: 20,723. New tasks:1000 training,250 validation,250 final; validation and final each have500 tool episodes (one verified wrong start and one semantically correct start per task). Public input counts vary1–4. Exact new task texts are disjoint from the v3 sets; these are new instances of partly familiar task families.

Contracts: preserve memory when that is graded; no implicit PC/one-instruction constraint for ordinary semantic stop tasks. Equivalent correct programs, including verified extra-NOP alternatives, are accepted. Historical exams were not relabelled.

DIAG is a five-byte hypothesis: cause, proposed expected serialized byte, observed serialized byte, two-byte serialized offset. Its runtime validates only the observed byte and offset. Teacher hypotheses use the verified canonical repair; they are not proofs of a unique cause. Runtime tools expose only actual public executions. Hidden expected outputs are used solely by offline teachers and grading.

Strict tool success requires a correct final program, explicit DONE, and execution/stopping of every public case on that program revision. False DONE counts semantically incorrect programs that the raw model declared complete. UNSURE and timeouts are unsolved. No semantic oracle or learned critic overrides raw decisions.

| Arm | Selected stage | New code generation | Repair + finish | All strict tool successes | False DONE | Premature DONE | UNSURE | ISA retention | Old formulas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sft | 1 | 220/250 | 63/250 | 286/500 | 73 | 0 | 121 | 638/648 | 52/98 |
| preference | 3 | 210/250 | 62/250 | 287/500 | 55 | 0 | 148 | 641/648 | 42/98 |

Validation selection was frozen before the final exam. Release criterion: zero false DONE, at least80% strict tool success, all648 documented opcode/mode cases retained and at least66/98 old formulas. An abstain-all model cannot pass.

Selected research artifact: `sft`. Validation release criterion met: **False**. Final exam does not retroactively change checkpoint selection.

| Public cases | SFT strict success | SFT false DONE | Preference strict success | Preference false DONE |
|---:|---:|---:|---:|---:|
| 1 | 70/126 | 19 | 65/126 | 18 |
| 2 | 69/126 | 21 | 72/126 | 10 |
| 3 | 73/124 | 20 | 71/124 | 21 |
| 4 | 74/124 | 13 | 79/124 | 6 |

Native verification:

- sft: exact Q4 re-export/reload; CPU/B200 14/14; native/B200 14/14; MKA 2,160,856 B; FP32 KV at1024 5,242,880 B; model workspace 17,392 B.
- preference: exact Q4 re-export/reload; CPU/B200 14/14; native/B200 14/14; MKA 2,160,856 B; FP32 KV at1024 5,242,880 B; model workspace 17,392 B.

Allocation-free action parser: 528 B, 1027 round trips and allowed-token masks matched Python. Full device peak RAM and speed were not measured. The existing assembler/runtime need additional memory.

Artifacts: `export/sft`, `export/preference`, `export/selected-research`; CLI: `aa_chat.py --model PATH --angle DEG --inputs JSON [--native] QUESTION`. A model DONE remains a claim: the public-input-only CLI reports `verified_task_success:null`.

All own GPU jobs ended; source checkpoint, frozen training/evaluation files and private emulator source were checked unchanged. See `postflight.json`.
