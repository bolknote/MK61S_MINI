# TinyTalk: continuation toward useful short conversation

Active work following the request to continue training beyond the earlier pilot.
This directory is separate from the PicoCalc firmware and the previous model artifacts.

Current status: round19 completed with 79/100, 50/60 and 73/100 on the
three observed direct partitions, and only 18/24 acceptable replies on the
hardest rollout partition. It has not reached the quality target. The gentle
full-weight continuation (round19b) also completed with best step0. Round20
is annotating short learned answer keywords before unchanged public speech;
its 12,000-step QAT run waits for completed labels and their audit. No good
conversation result is claimed by the format preflight or annotation checks.
The third independent audit stays closed; the final runner remains guarded.
Detailed state and source hashes are in `work-state.json`. Later paragraphs
retain experiment history rather than replace these current results.

## What counts as progress

Current selection uses real Q4-rounded weights, greedy decoding, a 128-token
context and at most 40 generated tokens. Early original-size runs used a
256-token context. The development target is:

- at least 80% acceptable answers to ordinary English conversation prompts;
- at least 72% on the contextual subset;
- at least 78% acceptable replies during actual three-turn conversations;
- at most three malformed or unfinished responses across the check.

The grader is the user's local Qwen model, with an absolute intent-sensitive rubric.
These percentages are automated assessments, not measured human satisfaction.
Each run retains prompts, replies, grades, actual conversation histories and source
hashes. Six calibration examples and a 16-example batched good/bad check passed.

The three observed prompt partitions contain 100, 60 and 100 cases, with separate
conversation partitions of 18, 18 and 24 replies. Every partition must pass its
gate separately, at two consecutive training checks. The third independent audit
(100 prompts and eight three-turn scenarios) remains closed during selection.
The final candidate must also pass the observed partitions with FP16 KV storage
before opening that audit. A small relative preference win is insufficient.

## Earlier experiments

1. Targeted continuation: 8000 SFT steps, and 6000 steps combining SFT with DPO.
   Teacher corrections address concrete ideas, actual questions, tone, facts and roles.
   Pair mining retained 2629 acceptable teacher answers paired with failed Q4 replies.
   This round did not meet the quality target; further training on this small corpus
   did not produce a sustained improvement.
2. A larger teacher corpus with more varied wording, useful earlier bot replies,
   simple games, observations, identity, preferences and multi-turn follow-ups.
   Both the original-size and a widened model receive the same data and training schedule.
   Planned schedule: 12000 steps, batch 32, FP32 first, QAT from step 6001, 5% natural
   dialogue replay, and a reduced learning rate for tied word embeddings.
   A 100-example sample passed 95% for final teacher answers and 79% for earlier
   context replies. The latter fail the 95% quality gate, so they are retained only
   as context and receive no target loss. Obvious false physical capabilities and
   malformed speaker/content arrays are also curated before training.
3. A diagnostic continuation with zero embedding learning rate on the first corpus,
   to check whether changing vocabulary representations explains degraded grammar.

For the earlier conversation checkpoint, 100 development prompts gave 29% acceptable
FP32 replies and 39% Q4 replies under the new rubric. This checkpoint was already
trained with QAT, so evaluating its raw weights does not represent its trained
inference format. Q4 was not the principal loss of quality in this comparison.

The original unmodified TinyTalk scored 29% in FP32 and 23% after Q4 on the same
100 development prompts. The new first-round DPO candidate reached 42% after Q4,
with 48% on the contextual subset and 44.4% in three-turn rollouts. These results
are development measurements, not a passed final audit.

## Widened model and memory

`widen.py` expands each feed-forward layer from 512 to 1536 units while preserving
the original hidden width, attention, tokenizer and tied embedding/output matrix.
New output columns start at zero. Initial logits were exactly identical in both
FP32 and Q4 on five diagnostic prompts. A separate gradient check confirmed that
the added units can learn and that validation preserves optimizer Parameters.

| Item | Bytes |
| --- | ---: |
| Widened model, TTQ4v1 file | 5,919,336 |
| Planned compact tokenizer | 921,923 |
| FP16 KV cache, context 256 | 1,048,576 |
| Working reserve | 262,144 |
| Planned total | 8,151,979 |
| Remaining from 8 MiB | 236,629 |

The widened model has **10,383,744 parameters**. This is a design budget: there is
no implemented native PicoCalc runtime or measured device allocation yet. The
tokenizer and working reserve are estimates inherited from the earlier design.
Host evaluation restores packed weights into FP32; this is not native Q4 speed.

## Files

- `work-state.json`: active experiment, remote location and next action.
- `generate.py`, `generate_large.py`, `prepare.py`: teacher corpus and splitting.
- `train.py`, `make_pairs.py`, `common.py`: training and preferences.
- `grade.py`, `evaluate.py`: absolute grading and actual conversation rollouts.
- `widen.py`, `widening-mechanics.json`: capacity initialization and checks.
- `diagnose_precision.py`: FP32/Q4 development comparison.
- `audit_candidate.py`: final audit after development criteria are met.
- `run_remote.py`, `run_large.py`: isolated remote experiment controllers.

Large data, raw checkpoints and packed files are stored under
`.build/tinytalk-quality-20261105/` and in the experiment's own remote directory.
Original weights and the earlier selected model are preserved.


## Later capacity and language experiments

The wider-FFN continuation reached a peak of 58% acceptable direct development
answers, still below the target. Further SFT on the same examples often reduced
training loss while worsening new conversations.

`rebalance.py` reallocates the vocabulary budget to a hidden-width-256,
FFN-width-1024 transformer. The core has 6,311,936 parameters, nearly four times
the original core. Vocabulary selection uses training token frequency and the
complete ancestry of each retained BPE merge. It retains 99.995% of weighted
training tokens, compared with 89.971% for the first 16384 GPT-2 token IDs.
Evaluation texts are not used for that selection. The compact byte/merge table is
an actual serialized artifact; a native tokenizer implementation remains future work.

The general function-preserving initialization idea follows
[Net2Net](https://arxiv.org/abs/1511.05641). Our GPT-Neo construction also adjusts
LayerNorm epsilon and scales for its unscaled QK attention. Before deliberate
symmetry-breaking noise, retained-token FP32 logits matched within 0.000049.
Independent gradient and packed-reload checks passed.

The training corpus was audited by the local teacher: 27,489 of 28,622 non-replay
training targets were accepted. The next training format uses a learned private
conversational-act token before the visible reply. The model predicts that token;
it is not selected by an external inference rule. All private tokens are hidden
by the tokenizer. Stored turn history is rendered as plain visible replies.

A Q4-aware language continuation consumed 100,007,936 tokens from 430,235
[TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories) stories.
Dataset revision: `f54c09fd23315a6f9c86f9dc80f725de7d8f9c64`. Documents were split
by content hash; 200,000 validation tokens are disjoint from training documents.
Validation NLL fell from 3.3341 to 1.8207. This measures language modeling,
not conversational acceptability.

The subsequent conversation curriculum adds 33,000 variable-value exercises:
user/pet names, binding a story answer to the question, missing-detail clarification,
contextual hobby projects, turn-taking without repeating an item, and text-only
activities. Exact development/audit contexts are excluded. Ordinary word embeddings
are frozen during SFT, and one arm also freezes the lower four transformer layers.
The old natural-dialogue replay is not sampled in this phase. These preservation
conditions are asserted at each development check.

At step 2000 the top-four-layer arm reached 65/100 acceptable direct replies,
23/25 contextual replies and 14/18 actual conversation replies. The target is
still unmet. The fresh audit remains unevaluated. Follow `work-state.json` for
active work rather than treating this intermediate result as completion.

The consistent-reply curriculum reached the development target twice in a row.
Round 7 selected top-four-layer SFT step 8000: 83/100 direct, 20/25 contextual,
15/18 conversation replies. The first independent audit did NOT pass: 46/60 direct
and 12/18 conversation replies, with no malformed replies. This candidate is
retained as an intermediate artifact, not described as final good quality.

Round 8 uses 14,400 on-policy turn examples (5,188 additional unique contexts)
generated before the first audit was read. Actual erroneous student replies remain
in the earlier history; targets follow the user's facts. The resulting corpus has
67,184 rows including an unused replay pool. The first audit is now development: both
the original 100 and opened 60 must pass separately, as must both 18-reply conversation
partitions. A new independent 100-prompt/8-conversation audit was reserved before training.
Its prompt SHA256 is `8a16e713d13195b631685c60f2506adf9b92bd453a5b7863b80c0303cce70495`.

An attention diagnostic found exactly duplicated adjacent Q/K/V rows and output
columns left by widening. `activate_attention.py` adds antisymmetric Q/V components
using Q4 integer codes while keeping K/output symmetric initially. They cancel in
the original function but permit gradients in the extra K/output directions.
The B200 preflight preserved training argmaxes and changed logits by at most
6.87e-5. Matched dequantized control and activated models are trained on identical
data. Quality improvement from activation itself is not assumed.

The second independent audit also failed: 39/100 short replies, 9/25 context-family
items and 15/24 actual conversation replies. Untouched original TinyTalk Q4 on the
same suite scored 18/100 and 5/24. The large development scores were therefore not
evidence of good general conversation. All these prompts are now development.

Round 9 changes the language backbone rather than repeating narrow SFT. The full
256-wide pretrained cores of `roneneldan/TinyStories-8M` and
`roneneldan/TinyStories-Instruct-8M` are pruned to the same existing vocabulary and
256 positions: both now have 10,577,920 parameters, runtime context 128. Retained
FP32 logits matched exactly in the transplant preflight. Each received 50,003,968
Q4-aware adaptation token exposures. Validation NLL for this additional training
fell to 1.6177 / 1.5992; this is a language metric, not chat accuracy, and does not
establish disjointness from the public backbone's original pretraining.

The expanded SFT corpus contains 144,746 unique contexts, including an unused
22,516-row replay pool. It combines vetted varied replies, 6,169 adapted public
everyday-dialogue targets (98% reference QA on a 200-row sample), and compositional
name/color/location, speaker-role, missing-information and correction exercises.
All 260 observed evaluation contexts are excluded. Corpus SHA256:
`24b776ea678a4f2f589207f24ab6d51f7f921f171e019eb93d9b2fb3f063b46e`.

An initial public-target generation mistakenly returned role/topic labels because
the output field `target` was ambiguous. That entire attempt was excluded before
training; the replacement literal `answer` field passed 32/32 probe cases.
The exact sources used by each run are archived under that run's `source` folder;
local experimental scripts may have evolved afterwards.

Round 9 completed without meeting the broad conversational target. The best
instructed core scored 84/100, 51/60 and 59/100 on the three observed prompt
partitions; conversation partitions were 17/18, 16/18 and 15/24. These are
automatic absolute teacher judgments, not human accuracy. The same packed
checkpoint restored exactly and matched B200 replies on 16/16 CPU probes.

Round 10 removed private act tokens in a matched ordinary-text ablation. Its
peak broad-prompt score was 60/100; it did not reach the quality target.
Round 11 mined 2,160 actual student mistakes from 6,000 training-only contexts.
Neither DPO nor hard-example SFT improved the worst development partition;
both kept the parent checkpoint as best. All failures and reports are preserved.

A paired precision control on the 100 already observed broad prompts measured
52/100 in raw FP32 and 58/100 after real Q4 packing for the saved tiny candidate.
Thus rounding is not the main explanation for this checkpoint's errors.
A read-only SmolLM2-135M-Instruct control scored 38/100 raw and 39/100 Q4 with
the same short-reply constraint. Its packed weights are 75,822,944 bytes and
are not a resident-8-MiB candidate; no streaming implementation is claimed.

Round 12 tests training all vocabulary weights at two learning rates. Its first
attempt could not access absolute data symlinks from Docker and performed no
weight updates; hardlinked immutable input copies fixed the launch.
Round 13 prepares 24,000 complete three-turn dialogues inspired by public
everyday topics, with more varied user wording and context. The 96-answer
probe passed 89/96. Every full-corpus target is therefore graded and failed
targets excluded before training. Training will compare continuing the best
chat checkpoint with starting again from the adapted language core.

The third independent audit remains closed. Its prompt SHA256 is
`3add12fa3e427355b720672942aa6a95e2ca2f6c3c348843d33854f29efaea0b`.
A separate blind audit checks observed evaluation intents without seeing
student answers; it does not alter the original evaluation files or scores.
The local `chat-candidate.sh` is an explicitly experimental CPU prototype.
The final `chat.sh` remains guarded until a final candidate is selected.

`verify_half_cache.py` additionally checked actual FP16 key/value storage rather
than merely estimating its bytes. All 100 observed broad-prompt token sequences
matched the usual FP32 cache with the saved Q4 candidate. Allocated cache bytes
matched the layer/head/context formula. Attention arithmetic remained host FP32;
this is not a native PicoCalc runtime or speed measurement.

Round 13 generation produced 71,995 usable turns and 63,930 unique contexts
before detailed full screening; the 240-target reference sample scored 89.17%.
The detailed original grader is used on every target. A proposed score-only
screen was rejected after it wrongly accepted two of seven known bad targets;
it has never been used to filter training data or evaluate a student.
Detailed screening concurrency increased from 12 to 24 with all cached requests
preserved and no changes to the rubric or batch contents.

A separate bAbI diagnostic on an initial short-context rendering scored 6/104
for the saved Q4 chat candidate. It measures grounded reading, not broad chat.
The robust training preparation retains the longest recent context that fits,
including preceding distractors; the first supporting fact is not always first.
All supplied supporting facts are preserved. Training names are varied by
gender-consistent bijections; official test names are preserved. The resulting
123,636 training and 12,250 test contexts have no exact overlap. This replaces
the initial support-first variant, which was never used for training.
Archive SHA256: `f7f0bee187efca0d81c3daac1b162cda4eb7f9505dee5ad6846eabbed3dbf92e`.
Source: https://parl.ai/downloads/babi/babi.tar.gz ; data license: CC BY 3.0.

Round 14 is queued after round 13 only if its broad conversational target is
still unmet. Two mixtures test 40% / 65% grounded-reading examples, preserving
natural conversation and earlier acts. Target cross-entropy is averaged within
each example before the batch, so short factual answers retain their intended
row weight. A numerical preflight on real Q4 batches matched the analytical
mean and produced finite gradients. Model size and Q4 format are unchanged.

Full detailed screening retained 58,777 of 63,930 unique natural targets and
removed 5,153 failures. New-target SHA256:
`71c274761cca9d48e0428de65ac2d79b12e99fa7144d665ba7c3acc3e7a6f789`.
The combined round-13 corpus contains 203,313 rows, including 22,513 unused
replay rows; replay sampling remains zero. Combined SHA256:
`129136a56b01f5ae081e850a3c2ae3d54c26d3b965a85c6975c6644de0c38d09`.

Round 12 selected words10 step8000 with 60/100 on the broad observed prompts,
64% in their context-family subset and 14/24 conversation replies; the target
is still unmet. Round 13 now trains both a continuation of that checkpoint and
a fresh copy of the adapted language core on the vetted complete dialogues.

Conversation evaluation now batches independent scenarios at each turn while
preserving each scenario's own generated history and the original grading order.
All 60 reply token sequences, metadata, grader contexts and histories matched
sequential evaluation on both CPU and B200. B200 inference for this control
fell from 9.99s to 1.95s. Detailed grading still uses the same schema, prompt and
thresholds, with 12 parallel requests. This is host evaluation speed only.
Exact run sources are snapshotted in each remote round's `source` directory.

Rounds 13 and 14 completed without meeting the full conversation target. Round
14's selected chat candidate scored 80/100, 55/60 and 61/100 on the three direct
partitions, with 18/18, 16/18 and 17/24 conversation replies. Its other arm's
last checkpoint did acquire grounded reading: 97/104 canonical exact matches
on the separate robust bAbI probe, compared with 0/104 for its chat parent.
That reading score does not establish conversation quality.

Round 15 transfers that reading checkpoint to 39,542 paired conversational
attribute examples. Each identical factual history has one question about a
present attribute and another about an absent attribute. One- and two-fact
histories are both balanced; the original detailed grader accepted all 240
sampled reference answers. New-data SHA256:
`613c7359642a3a8789d21eb3fb6d5b4d3ffae841207038961521126480fd3394`.
The 366,490-row combined corpus retains earlier conversation and reading data.
Two sequential 8,000-step arms compare private act prefixes with ordinary text,
training all weights with Q4 throughout. The prefix arm's best broad-prompt
score was 63/100; it did not meet the full target. The plain arm also scored
63/100 at its selected checkpoint, with weaker overall conversation results.
The third independent audit remains closed and all quality gates are unchanged.

Round 16 continues from round 15's selected prefix checkpoint on a broader
fictional-state curriculum: 123,589 new examples, including 42,272 examples
whose histories correct an earlier fact, plus duration, flavor, count, age,
weather and simple turn-taking games. New-data SHA256:
`5abe8ba5c1c0b3535b56958d3be85a00fdb27afc618e56b4504fefe8b8ea91ab`.
The original detailed grader accepted 505/512 sampled reference answers.
An initial weather/temperature ambiguity was repaired before any student
training; its original data, judgments and prepared merge remain archived.
The new run trains all weights with the same Q4 format, runtime context,
mixture fractions and original three-partition quality gates for up to 12,000
steps. The source checkpoint SHA256 is
`7bbc14fe56f54f56bfae4161a8d8b6d994d767949408be0b16d6fcdcdd373ca1`.

Round 16's intermediate selected checkpoint at step6000 improves the broad
direct partition to 72/100; its broad context subset is 64% and its conversation
partition 16/24, so the full quality target remains unmet.

A separate MLP-capacity preflight expands width1024 to1280 by adding noisy
input units with zero initial output contribution. It has 11,628,544 parameters,
preserves all tested FP32 and Q4 logits exactly, matches all 10 probe reply
token sequences, and restores its packed file exactly. New output units have
nonzero gradients immediately and new input units after the first optimizer
step in an isolated diagnostic; those diagnostic updates are not saved.
Its total memory design estimate is 8,243,985 bytes, including the original
262,144-byte reserve, with 144,623 bytes left from 8 MiB. No native device
measurement or quality improvement is claimed by this preflight.

Round 17 is conditional on round16 still missing its gates. It will distill
6,000 ordinary conversational prefixes with four alternative final requests.
All new references receive detailed grading; a prefix is retained only with
at least three accepted branches. The revised 32-prefix probe accepted 116/124
targets. A first probe wandered into unsuitable adult topics and was excluded;
the revised version uses varied ordinary topics and restricts missing-fact
questions to personal facts, rather than general world knowledge.
It will train the expanded MLP first and a matched compact control if needed,
sequentially. All original gates and the closed third audit remain unchanged.

Round16's final selection remained step6000. Its packed checkpoint restored
exactly and matched 16/16 B200 replies on CPU. Actual FP16 KV storage matched
99/100 broad prompt token sequences. The changed answer still failed to name
the requested song, just as its FP32-cache counterpart did; no scores were
rewritten. Before opening audit3, a qualified checkpoint must additionally pass
every observed direct and rollout partition using the planned FP16 KV storage.
The independent audit must use that storage precision too.

`chat-candidate.sh` now runs the round16 experimental checkpoint. Its raw SHA256
is `bc2731148309bffcceda6311ad55d47e9e544086176153141fab31c2740ff6ea`.
It remains below the full quality target. Its memory design estimate is
7,645,729 bytes; this is not a native PicoCalc execution or speed measurement.

The local candidate now also stores actual KV tensors in FP16 through the
shared chat runner's optional cache factory. All ten saved manual replies
matched the prior FP32-cache replies; the transcript records actual FP16 cache
dtypes. The manual sample still fails ordinary conversation requirements and
is preserved in full. Earlier FP32 and invalid-reset-command attempts are
retained separately. The final runner uses FP16 KV too, but remains guarded.

Round17 generation and full screening completed. It retains 21,575 accepted
final requests from 5,696 shared prefixes, each with at least three accepted
branches. All references were graded: 1,792 failed targets were removed, and
prefixes with fewer than three passing alternatives were discarded.
New-data SHA256:
`b93a132285c7d004a0f1bb2c5453f16ecca38a09ae08dbf7948010f3d49c4e66`.

Expansion of the newer parent exposed an FP32 accumulation-order difference:
4.94e-5 maximum logit difference in full precision and 5.36e-5 with Q4 weights.
An initial 5e-5 numerical assertion stopped preparation before student training.
The original attempt remains archived. All 6,022,240 inherited packed payload
bytes were then checked equal, all 16,384 added output blocks checked zero,
all ten probe token sequences matched, and packed reload error was zero.
The numerical tolerance is now 1e-4 with those exact inheritance checks;
all conversation quality gates are unchanged. Training the expanded 11,628,544
parameter model has started, reusing the completed full screening and data.

Round17's expanded arm completed 8,000 steps without improving on its parent;
the compact control is running. A conditional round18 is prepared to freeze
all 10,577,920 inherited elements and train only the 1,050,624 added MLP
elements. Its optimizer holds larger parameter tensors with masked fixed
regions; the report distinguishes those containers from effective trainable
elements. Inherited slices are restored after each update and all fixed
parameters checked at every validation.

An isolated 12-step AdamW preflight deliberately enabled weight decay and saved
a QAT checkpoint mid-training. Added segments changed, while all 6,022,240
inherited packed payload bytes remained identical. This proves the freezing
mechanism, not conversation improvement. Round18 also screens both earlier
teacher replies in each new dialogue and removes a whole prefix if either
fails. Accepted earlier turns receive their own sampling fraction, addressing
the first-turn gap seen in manual conversation. This preparation waits for the
complete round17 comparison and is skipped if that comparison qualifies.

Round17's compact control also completed with best step0. Its selected wider
baseline has no fine-tuning updates; the one-point difference in the broad
automatic score is not evidence of a learned improvement. Round18 therefore
started screening 11,388 earlier teacher replies, excluding two complete
prefixes by exact observed/closed-context hashes. The third audit is still
closed. A separate analysis of the round16 checkpoint found no history trimming
in any of its 260 direct cases or 60 rollout cases, so increasing its context
window does not explain or resolve those observed failures.


Round18 completed all 10,000 steps. Its selected step3,000 has direct rates
80%, 88.3%, 73%; contextual rates 88%, 100%, 64%; and rollout rates
88.9%, 88.9%, 70.8%. No checkpoint qualified. An independent binary comparison
after GPU training verified all 6,022,240 inherited payload bytes across
108 tensors unchanged; 2,064 added segments changed. The model is not promoted
as an overall replacement for round16: its worst partition improves slightly,
but its combined score falls and some title-generation failures remain.

Round19 adds thirty private answer-form tokens, including name, color, plant,
genre, song title, book title, wish and unknown. The teacher labeled 86,824
already accepted training replies; their spoken text and contexts remain
unchanged. The network selects both private tags from its logits, then generates
the visible reply. A format mask controls only these wire positions and prevents
repeated trigrams in generated speech. Prompt facts remain copyable.

Only 1,058,304 effective elements can change: 1,050,624 added MLP elements and
7,680 new type embeddings. All 10,577,920 inherited elements stay fixed.
The 11,636,224-parameter initializer occupies a design total of 8,249,269 bytes
including the tokenizer, 128-token FP16 KV and 262,144 bytes of reserve;
139,339 bytes remain within 8 MiB. This is not a native firmware measurement.
At step5,000 the hard partition remains 70/100, with 14/24 acceptable rollout
turns. Correct plant suggestions and vanilla recall coexist with ignored
corrections and invented book/song titles. The new untrained-format baseline
is not used to claim an improvement over the earlier model. Audit3 stays closed.


Round19 completed all 10,000 steps; selected step8,000 has direct rates
79%, 83.3%, 73%; contextual rates 92%, 93.3%, 64%; and rollout rates
88.9%, 94.4%, 75%. All inherited 6,022,240 packed payload bytes remain
identical. The packed model restores exactly; 16/16 selected B200 replies
match on CPU. All ten user turns of the earlier manual probe were repeated
with newly generated assistant history and actual FP16 KV. Greeting and
rabbit acknowledgment improve, while entity recall, a corrected scarf color,
a plant follow-up and a good-luck wish still fail or remain awkward.

Round19b lowers the main learning rate to 3e-6 and the embedding multiplier
to 0.1, allowing all weights to adapt to the same answer-form data. Its
reference KL coefficient is 0.05. It runs after round19, not concurrently.

Round20 learns a short answer-content span before a private speech boundary.
It is answer keywords, not a rationale. The existing forty-token total output
limit and 128-token context remain unchanged. Four local format probes and
a 12-step update/save/restore test confirm that private keywords are excluded
from the visible reply, values can be copied into speech, the ten-token key
bound is enforced, and inherited packed bytes stay fixed. This is a structural
preflight on an older local source, not an actual quality measurement.

Of 96 balanced annotation probes, 94 accepted spoken targets and 94 keyword
labels passed their respective checks. Known failed probe rows are excluded
when preparing the new corpus. Labels must be short spans from the accepted
answer, except the explicit unavailable-information keyword. Invalid spans
are retried and then recorded/excluded, with at least 99.5% coverage required.
An executor error initially waited on queued labeling jobs; its cached replies
were preserved and the handling repaired. Our label process is temporarily
paused while the student comparison runs, with a bounded watchdog to resume
it. The user's teacher server is untouched.


Round19b completed 8,000 steps without a better checkpoint. Its best step0
retains the parent's raw weights. Round19's ten manual dialogues also have
10/10 identical raw token sequences with FP16 versus FP32 KV. The actual
interactive runner reproduces all ten batched-probe replies, hides both tags,
and stores KV in FP16. `chat-round19.sh` exposes this unqualified experiment;
`chat-candidate.sh` still points to the earlier round16 comparison prototype.

A separate factorial development diagnostic varies echoing, pronoun updates,
and questions with/without now. The unchanged detailed grader accepts
376/400 replies, including 11/16 reverse entity queries. None of these cases
were trimmed. This narrow score is not the main conversation score and does
not change its gates. Echoing the old value is not generally harmful in this
probe; a proposed general echo-related explanation was not supported.
Rare-name copying and entity relations remain visible failure modes.

The keyword annotation protocol now uses shorter strings for uncached requests,
with the same span validation and explicit-field retries for invalid compact
outputs. On the same 96 source examples, output length falls from 2,746 to
1,216 teacher tokens. Its keyword audit passes 93/96 (96.9%); the full corpus
still requires its separate 768-example audit at 95%. All legacy cached replies
remain available. An earlier compact-format probe lost three spans and was
rejected before use; its artifacts are preserved. The working version explicitly
separates answer keywords from names merely mentioned in context.
