# Ordinary chat, activation reuse and shared GQA reads

The native AI service now selects the qualified two-core INT8 path and enters
270 MHz during ordinary chat generation. Completion, F5 pause, Esc and exit
restore the entry clock. Normal firmware builds include the qualified clock
transition; `--no-ai-fast-clock` disables its build support explicitly.

Q/K/V reuse the same prepared normalized activation vector, and gate/up reuse
their common input. For the frozen ten-layer model this reduces preparations
from 71 to 41 per complete decode step. This changes neither scales nor rounding.

Attention processes two query heads sharing a KV head together. Each head keeps
its original dot-product, softmax and weighted-sum order. The 4-query/2-KV-head
model reads half as many KV bytes. The additional score array costs 2048 bytes
at context512, or4096 bytes at context1024. No KV quantization or eviction is used.

## Quality checks

- ASan/UBSan prefetch/DMA suite: complete logits, token trajectory and KV cache
  match the old preparation/attention path exactly over256 positions.
- Independent old-path oracle: three cold prefills of64/128/256 tokens followed
  by two greedy decode steps; complete logits, checksums and used KV bytes match.
- Native SPEC model, INT8: all eight published Russian fixtures pass with their
  exact expected generated tokens, compiled programs and emulator results.
- Ordinary native UI with simulated clock: start/resume270 MHz; pause, completion,
  cancellation and exit restore125 MHz. Hardware clock lifecycle and long-context validation are tracked separately below.

The exact-equivalence claim concerns the new reuse and attention algorithms
relative to the previous INT8 path. The eight SPEC fixtures are a bounded
regression set, not a general proof that INT8 and FP32 behave identically.

## Long-context measurement

`LONG.CFG` is exactly `AILONG1\n`. `LONG.REF` is produced by
`tests/mk61_ai_long_oracle.cpp` from the pinned model. The normal diagnostic
service runs independent64/128/256-token cold prefills and two decode steps each
at270 MHz, with two cores, INT8,28-row narrow tiles and DMA prefetch.

`LONG.JSON` records cold prefill/time to first token, individual decode latencies,
layer/classifier times, KV bytes, activation preparation/reuse counts, clock
restoration and comparison with the host oracle. Model loading is timed
separately. These synthetic fixed streams measure context cost; they do not
measure conversational task accuracy. No older firmware run is required.

## Hardware short result

The E0CDF5AB/0B15A4C7 build measured0.7291845 and0.7292815 seconds/token
at270 MHz, versus the archived0.783943 reference:6.99% and6.97% lower latency.
Tokens and whole-linear-output checksums matched the archived reference.

The first64-token hardware run chose the same greedy tokens as the host but
had different float hashes. Cross-platform libm rounding is a possible cause;
this does not establish a regression in the reuse algorithms. The revised
long diagnostic additionally compares the old INT8 execution on the same MCU
at the final prefill and two decode positions of each case. These nine control
steps run outside reported model timings and compare next tokens, all-linear
checksums and each current KV row. It reuses the same prior prefix with rewind;
no second model/cache allocation is required. Host tests also validate this
rewind comparison against an independent full-cache reference.

## Final long-context hardware results

Final build5CC4EF8E/318A7C05,270 MHz, two cores, unchanged frozen performance
model MKA-AA8246E1-2093896. Each context is an independent cold prefill;
timings exclude loading and the nine selected old-path verification steps.

| Prompt tokens | Prefill / first token, seconds | Decode, seconds/token |
|---:|---:|---:|
|64|63.626746|1.567663|
|128|180.688461|2.4046235|
|256|575.607019|4.081851|

Model loading took9.270355 seconds separately. All nine same-MCU comparisons
passed; host greedy tokens matched too. Activation preparation counts82 and
reuse counts60 per two decode steps confirm41 preparations and30 reuses/token.
KV read bytes over those two steps were670720/1326080/2636800, half the old path.
Freeze/thaw counts463/463, zero freeze violations; stack peak23488/32768 bytes,
sampled heap peak70856/109544 bytes. All clocks restored to125 MHz.

These results expose the remaining latency cost of long prefills. The short
benchmark is a near-empty-context throughput figure and does not describe
response latency after hundreds of input tokens.

Reproduce the independent host oracle with:

```sh
MK61_AI_TEST_SANITIZERS=1 bash tests/run_mk61_ai_long_tests.sh MODEL.MKA LONG.REF
```

## Installed final image and short placement check

Moving cold diagnostics into a separate flash slot changed code placement.
The installed final image5CC4EF8E/318A7C05 therefore received its own short
candidate-only check:0.770563 and0.771089 seconds/token at270 MHz,1.71% and1.64%
lower latency than0.783943. Archived tokens/checksums matched, no freeze or I²C
errors. The preliminary0.7291845/0.7292815 figures belong to E0CDF5AB and must
not be attributed to the final image. Placement tuning remains a possible
reserve; this change prioritizes an installed image with all four fixes and
working, reproducible long-context diagnostics.

Owned temporary APP directories and LONG.CFG/REF/JSON files were removed from
SD after downloading the receipts. The root model and Spectrum were not changed.
The device was left in the calculator at125 MHz; CDC/MSC/lease were closed.

The user's reported unsupported dash was also corrected to `F5: начать вычисление`.
The HIL exit helper now waits for the180-ms virtual key release before retrying
Esc; repeated held pulses previously suppressed later Esc gestures.
