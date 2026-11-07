# 3M Q4: separate actions, diagnosis and iterative preferences

A bounded paired experiment, not a device release. The original harness-debug-v3 exports and exam results remain unchanged.

The model uses 7 existing reserved IDs for WRITE/PATCH/RUN/TRACE/DIAG/DONE/UNSURE, 23 HEX-body IDs and the original < row30 as terminator:31 output rows. Russian input vocabulary and all original input embedding rows are bit-identical. No parameter-count increase.

The synthetic < primer is encoded separately to avoid the space/< BPE merge. A wire action is never fed into KV; the runtime instead inserts the original fixed neural tag header for that chosen action. These headers select no instruction and contain no task answer. A pre-training pilot reproduced131/131 old programs exactly with this adapter and no SGD.

Training objective: CE(action) + 0.5 × per-example mean CE(HEX arguments) + 0.03 × language replay. Action CE is not divided by answer length. The preference arm additionally uses action-only DPO (beta=0.2, weight=0.5) with the fixed common warmup as reference; argument tokens use the same SFT objective in both arms.

Common readout-only warmup: 400 updates; the original backbone is bit-identical after this stage. Each arm: 3 stages × 400 updates, batch128, Q4 from update1. Backbone LR2e-6, action readout LR2e-5. Both arms use identical SFT draw digests at every stage. Current-student states refresh after warmup and stages1–2; validation/final tasks never enter these pools.

Offline process lessons: 20,723. Training and development reuse the v1 course,1000 additional training tasks and250 development tasks. A new250-task final set was frozen before v2 SGD, disjoint from v1 and v3 exact task texts. Development and final each have500 episodes (one verified wrong and one semantically correct start per task), with1–4 public inputs. These are new instances of partly familiar families.

Contracts: preserve memory when that is graded; no implicit PC/one-instruction constraint for ordinary semantic stop tasks. Equivalent correct programs, including verified extra-NOP alternatives, are accepted. Historical exams were not relabelled.

DIAG is a five-byte hypothesis: cause, proposed expected serialized byte, cited serialized byte, two-byte serialized offset. The runtime returns the actual byte at that offset (or an out-of-bounds fact), even when the citation is wrong. This prevents a mistaken hypothesis from blocking the repair loop. Teacher hypotheses use a verified canonical repair; they do not prove a unique cause. Runtime tools expose only actual public executions. Hidden expected outputs are used solely by offline teachers and grading.

Strict tool success requires a correct final program, explicit DONE, and execution/stopping of every public case on that program revision. False DONE counts semantically incorrect programs that the raw model declared complete. UNSURE and timeouts are unsolved. No semantic oracle or learned critic overrides raw decisions.

| Arm | Selected stage | New code generation | Repair + finish | All strict tool successes | False DONE | Premature DONE | UNSURE | ISA retention | Old formulas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sft | 3 | 213/250 | 49/250 | 259/500 | 163 | 0 | 16 | 643/648 | 50/98 |
| preference | 3 | 205/250 | 44/250 | 260/500 | 183 | 0 | 18 | 630/648 | 65/98 |

Validation selection was frozen before the final exam. Release criterion: zero false DONE, at least80% strict tool success, all648 documented opcode/mode cases retained and at least66/98 old formulas. An abstain-all model cannot pass.

Selected research artifact: `sft`. Validation release criterion met: **False**. Final exam does not retroactively change checkpoint selection.

| Public cases | SFT strict success | SFT false DONE | Preference strict success | Preference false DONE |
|---:|---:|---:|---:|---:|
| 1 | 63/126 | 47 | 60/126 | 53 |
| 2 | 78/126 | 34 | 81/126 | 35 |
| 3 | 51/124 | 54 | 52/124 | 59 |
| 4 | 67/124 | 28 | 67/124 | 36 |

Native verification:

- sft: exact Q4 re-export/reload; CPU/B200 14/14; native/B200 14/14; MKA 2,160,856 B; FP32 KV at1024 5,242,880 B; model workspace 17,392 B.
- preference: exact Q4 re-export/reload; CPU/B200 14/14; native/B200 14/14; MKA 2,160,856 B; FP32 KV at1024 5,242,880 B; model workspace 17,392 B.

Allocation-free action parser: 528 B, 1027 round trips and allowed-token masks matched Python. Full device peak RAM and speed were not measured. The existing assembler/runtime need additional memory.

Artifacts: `export/sft`, `export/preference`, `export/selected-research`; CLI: `ab_chat.py --model PATH --angle DEG --inputs JSON [--native] QUESTION`. A model DONE remains a claim: the public-input-only CLI reports `verified_task_success:null`.

All own GPU jobs ended; source checkpoint, frozen training/evaluation files and private emulator source were checked unchanged. See `postflight.json`.
