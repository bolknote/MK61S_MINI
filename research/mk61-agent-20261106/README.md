# Local MK-61 programming agent experiment

The target executes its model and calculator tools on PicoCalc. B200 is used
for training and host evaluation. This experiment does not modify or control
the ongoing TinyTalk conversational training in another task.

The first proposed custom architecture was a 4.39M GQA decoder. The user then
requested a Russian pretrained foundation before training begins. The current
candidate is [akanemind/Flourish-3M](https://huggingface.co/akanemind/Flourish-3M),
revision `33b38dfec202c39c3698f7f2d1a9933a34a2de1a`.

## Completed native Q4 versus mixed-bit comparison

The two new architectures completed matched language continuation and8,000
standard-MK61 SFT updates each, with target-bit training throughout. Validation
selected `q4` before the new84-condition audit opened. Its first neural
program passes 65/84; full formal regression is
95/98. Extended MK61S memory commands are excluded
from executable targets. See [all measured results](FINAL_RESULTS.md#полный-курс-для-q4-и-q2q4-стандартный-мк-61--6-ноября-2026).

The mixed model passes67/84 on that audit, compared with65/84 for Q4 and63/84
for the previous3M baseline. Neither new model reaches the90% target or solves
the40 compound tasks. Long-context scores are10/14 at1024 and9/14 at2048.

The actual evaluated MKQB packets and learned Q2 scales are preserved under
`/Users/bolk/Projects/MK61S_MINI/.build/mk61-agent-20261106/native-mixed-v1/server-results/export`. CPU replay and FP16 KV storage checks are in
`local-verification.json`. This does not measure native PicoCalc performance.

## Completed capacity and low-bit comparison

The validation-selected 3M Q4 candidate solves 60/84 new single-operation
conditions, compared with 58/84 for 4.49M Q4 and 50/84 for 4.49M Q2-FFN/Q4-rest
after short QAT. Full formal regression is 98/98 and 96/98 for the two Q4 models.
The 90% curriculum gate was not met. See [the completed comparison](FINAL_RESULTS.md).

The completed preceding course compared 3,017,984 parameters with a function-preserving
FFN expansion to 4,492,544. Attention, KV dimensions, vocabulary and 512-token
context are identical. Initial sampled logits match exactly in FP32 and real Q4.
Both sizes receive the same single-operation course, paired register renamings,
example-balanced loss and a student-predicted `<calc>` prefix before bytecode.
The harness does not compute that prefix or compile model answers at inference.
These training choices were informed by the referenced `LLM на PicoCalc` thread
and its `research/tinytalk-quality-20261105` experiments; their conversational
scores do not establish Russian MK-61 programming performance.

The new teacher references are independently reverse-parsed with opaque IDs and
shuffled classes. A pre-gradient check found operation names in provenance IDs;
that verification attempt is retained but excluded, and the opaque-ID pass is
used instead. Whole minimal pairs and register-neutral exact wordings share a
split. Manual validation and new fresh probes were frozen before gradients.
Actual model-written first-turn programs, register preservation and parsing are
scored separately. Numeric input/output examples are hidden from language prompts.
Stage 2 is conditional on 90% parsing and program execution on both validation
partitions, with at least 95% formal regression preservation.

Both sizes completed 4000 initial updates and 2000 additional updates using a
balanced replay pool of composed arithmetic and control tasks. The latter
recovered formal skills that the initial control-only replay did not preserve.
Q3, Q2 and Q2-FFN/Q4-rest each received a matched 500-update QAT comparison after
the main Q4 course. This uses a transparent uniform per-32-weight baseline,
not an implementation of ParetoQ/GPTQ. Low-bit failure would only characterize
this recipe and budget. Formats/checkpoints are selected before fresh scoring.

| Initial packed weights | 3.02M | 4.49M |
| --- | ---: | ---: |
| Q4 | 1,724,490 B | 2,553,942 B |
| Q3 | 1,346,565 B | 1,991,711 B |
| Q2 | 969,692 B | 1,430,527 B |
| FFN Q2, rest Q4 | 1,354,768 B | 1,815,587 B |

The 1.8 MiB weight ceiling used for one comparison is an experimental weight-only
budget. FP16 KV remains 1,310,720 B at 512 tokens. No native device memory or
speed claim follows from these packed file sizes. All five exports restored
exactly on CPU. Sixteen replies matched B200; actual FP16 KV storage preserved
all sixteen replies too. This verifies host behavior. The experiment state is available via:

```sh
python3 research/mk61-agent-20261106/capacity_remote.py status
```

## Completed result

Both training rounds, baseline evaluation, packed Q4 evaluation and local
artifact reload checks are complete. See [the measured results](RESULTS.md).
The Q4 plan arm solves 98/98 formal tasks but only 1/24 fresh, manually worded
Russian tasks. The no-plan arm scores 97/98 and 3/24. This is a narrow formal
program generator, not a reliable free-language MK-61 programming assistant.
The plan arm was selected by validation alone; both checkpoints are retained.

Teacher continuation subsequently improved fresh Russian Q4 execution to 30/64,
from 13/64 for the previous direct checkpoint on that same set. Formal regression
is 96/98. See [the teacher results](DISTILLATION_RESULTS.md) and
[its methodology](DISTILLATION.md). This falls short of the declared 80% target.
`distill-hard` is also complete: executable correct/incorrect program pairs and
text-first SFT were compared with a newly frozen 64-condition audit. The previous
64 conditions are diagnostic only, not new gradient or selection data.

See [the final neural and hybrid results](FINAL_RESULTS.md). On the newest set,
original Flourish solves 0/64, the pre-teacher checkpoint 8/64, the selected
teacher-trained checkpoint 26/64, DPO 29/64 and text-first SFT 22/64 in Q4.
An explicitly separate automatic arithmetic repair wrapper raises the selected
model to 49/64 and formal regression to 98/98. It needs public numerical examples
with expected outputs and tries at most 512 candidates; hidden failures never
guide its search. Neither neural nor hybrid accuracy reaches the declared 80%
natural-language target. Native PicoCalc execution of these checkpoint exports has not been measured.

An executable example of model failure followed by repair:

```sh
.build/squeal-chat-20261105/venv/bin/python research/mk61-agent-20261106/try_model.py \
  --model .build/mk61-agent-20261106/distill-hard/export/baseline/hf \
  --weights .build/mk61-agent-20261106/distill-hard/export/baseline/model.mkq4 \
  --task-file research/mk61-agent-20261106/demo-repair.json \
  --no-plan --repair-budget 512
```

The second round added 25,333 Russian instruction/feedback examples with 16,000
replay examples, and ran 2000 further updates per arm with QAT throughout.
The 24 fresh natural-language tasks were frozen before this round and did not
enter training or checkpoint selection. The earlier 12-task language set became
a diagnostic set after it exposed the first round's transfer failure.

## Verified starting point

- Safetensors checkpoint downloaded with file hashes; no remote model code run.
- 3,017,984 unique parameters, 10 layers, width 128, FFN 384, four Q heads,
  two KV heads, head dimension 32, shared input/output embeddings.
- Native training context: 512 tokens. Extending it to 1024 or 2048 requires
  dedicated training and evaluation; the memory calculation is not such a test.
- Standard Transformers loading and a finite-logit forward pass passed locally.
- Two Russian task descriptions round-trip through the tokenizer in 41 and
  27 tokens, respectively. This does not measure instruction following.
- Weight layout estimate: 1,709,056 bytes using signed Q4 matrices with one
  FP16 scale per 32 weights and FP32 vectors. Actual exported files including
  metadata are 1,724,477 bytes (plan) and 1,724,480 bytes (no-plan); exact reload
  of both trained artifacts was checked. Host evaluation uses FP32 activations
  and KV cache. Native PicoCalc execution of these checkpoint exports has not been measured.
- Full FP16 KV: 2560 bytes/token; 1.25 MiB at 512, 2.50 MiB at 1024,
  5.00 MiB at 2048 tokens. Tokenizer JSON: 758,901 bytes. Working buffers,
  emulator/UI allocations and actual device throughput are not measured.
- Base model has no demonstrated MK-61 coding, tool-use or reasoning ability.
  Its model card reports weak coherence; it is an experimental starting point.

## Corpus snapshot

Read-only source: the sibling `/Users/bolk/Projects/MK-61` repository.
Its authoritative manifest has 696 entries, including 624 games. Whole families
are joined by series, normalized titles, identical bytecode and >=85% sequence
similarity before splitting. There are 518 components in this snapshot.

The existing canonical mnemonic parser decoded 548 entries without diagnostics.
The other 148 remain excluded with exact diagnostics, mainly notation aliases
and listings requiring interpretation. These are not assumed to be bad games.
The current training/validation/test partitions contain 462/43/43 decoded
programs, respectively. Descriptions and all derived examples must retain the
parent game's split. Test games are not a prompt selection or debugging set.

Six general instructional documents were snapshotted for training. Nine books'
existing OCR/native text yielded 302 selected instructional prose units. Raw
program tables were excluded as supervised answers. Six separately inventoried
PDF files were not used as additional text sources. Provenance hashes and
family-split checks are recorded in the data audit.

`core_bridge.cpp` and `emulator.py` expose bounded execution of the production
PicoCalc microcode core. This is a host tool foundation, not the device harness.
Arithmetic, branches, register writes, instruction limits, hidden-test grading
and trace/repair interaction pass the research integration checks.

## First controlled training run

The immutable original checkpoint is evaluated in FP32 and packed/reloaded Q4
before training. The official comparison uses a 512-token context, greedy
decoding, at most 160 generated tokens per turn and three tool turns.

Domain continuation uses 462 normalized historical listings, 302 instructional
prose units from nine Russian books, and six general reference documents.
Raw OCR program tables are not trusted program answers. Book passages mentioning
games, held-out titles or different calculator architectures are filtered out.
These historical listings are syntax-normalized training material; this does
not establish that all 462 games have passed gameplay tests.

The supervised set has 34,320 examples: writing programs, repairing mistakes,
requesting a trace, fixing a program after real feedback and ending after PASS.
All generated reference programs are checked on the production microcode core.
Observation text is part of the prompt and receives no target loss.

The two arms start from the same domain checkpoint. One predicts a short plan
before acting; the other predicts actions directly. Both use 3000 optimizer
steps with effective batch 32. Q4-aware training starts at step 2001. Following
a process-memory-limit failure, micro-batches of 16 with two accumulation passes
preserve the effective batch. Completed baselines and domain training are reused.

Tools use an explicit text protocol:

```text
<plan>короткий план</plan><write>60 61 10 50</write><run/>
<plan>проверить текущий код пошагово</plan><trace/>
<done/>
```

The host harness executes the calls, checks actual outputs and supplies the next
observation. Model-written success claims do not pass a task. A correct public
example is followed by hidden inputs. Each turn re-renders the current task,
candidate and latest feedback; the complete trace stays outside the model window.

Expression families are split before augmentation with register names removed
and commutative order normalized. The development set contains 60 unseen
expression tasks plus 12 controls. The final set has 80 unseen expression tasks
plus 18 controls. Controls test new inputs and register allocations of taught
primitives, including disjoint increment ranges for loops. A separate 12-task
natural-Russian transfer check stays outside training and checkpoint selection;
after it exposed poor transfer, a new 24-task audit was frozen for round two.
Whole held-out historical games are not yet an end-to-end success benchmark.

## Commands and artifacts

```sh
python3 research/mk61-agent-20261106/prepare_corpus.py
python3 research/mk61-agent-20261106/emulator.py
python3 research/mk61-agent-20261106/fetch_model.py
python3 research/mk61-agent-20261106/self_test.py
python3 research/mk61-agent-20261106/remote.py status
python3 research/mk61-agent-20261106/remote.py fetch
```

Generated corpus, original weights, provenance and the local preflight report
are under `.build/mk61-agent-20261106/`. Downloads and snapshots do not overwrite
the sibling repository or any other model experiment. Training runs in its own
remote directory; `remote.py status` reads the current phase and progress.

The primary comparison is now original Flourish versus the two fine-tuned
Flourish arms. TinyTalk is left to its separate conversation experiment.
Context extension and native PicoCalc inference remain separate measurements.

To run a supplied task with the exported Q4 checkpoint:

```sh
.build/squeal-chat-20261105/venv/bin/python research/mk61-agent-20261106/try_model.py \
  --model .build/mk61-agent-20261106/export/plan/hf \
  --weights .build/mk61-agent-20261106/export/plan/model.mkq4 \
  --task-file research/mk61-agent-20261106/demo-formula.json
```

The formal example passes. With `demo-task.json` the same addition described
in words produces subtraction and fails. These examples illustrate the observed
language limitation; they are not additional benchmark tasks.
