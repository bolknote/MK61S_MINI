# Late PSRAM sampling at33.3MHz: hardware result,2026-11-10

The late-sampling candidate passed its short private-buffer stress, but did not beat the requested historical **0.606s/token** reference. At270MHz CPU, the two measured decode times were **0.624936 and0.6248685s/token**, about3.12% and3.11% slower. The production default remains the qualified25MHz read profile; the33.3MHz build option remains experimental and OFF.

| Check | Actual device result |
| --- | --- |
| Candidate |7BD2529E /41018F7C, clean main e8b706dbe, committed late-read option only |
| Read clock |346/256 PIO divider,33.295MHz SCK |
| Stress before inference |5000ms,9201 iterations,9201 core1 jobs, reason none, matching CRC, balanced freeze/thaw |
| Decode pass1 |0.624936s/token,2 prefill +2 decode |
| Decode pass2 |0.6248685s/token,2 prefill +2 decode |
| Token/linear-checksum oracle |Exact match in both passes: next0,1295,1295,1295; a420e337,b3204470,ac2726ae,b99f9b54 |
| I2C / freeze errors |0 /0 |
| Heap / stack peaks |85112/108672 heap bytes;25556/32768 stack bytes |
| Final firmware |Exact verified5D0A3631 / B836FE58 restored;125MHz, awake, CALCULATOR/CLOSED/NONE |
| ROMCACHE |All four before/after reads match4653714e321ded6d36ed31a9d9d85d17ca37af44f753db2b37543624645b43f4 |
| Release |Own benchmark APP removed; CDC and shared lease closed |

The model remains the same2093896-byte Q4 file, SHA25667aae98d9ffbd332bbea6e9a7dde9ec003f8213b99d92c555b523c794256d01b. Arithmetic, tokenizer and model data were not changed. The four existing changes remain in the frozen source: fast ordinary chat,64/128/256-context diagnostic, shared activation preparation, and gathered/shared/parallel KV reads. Long-context speed and full KV parity were not remeasured here. Exact token and linear checksums are evidence for these fixed short passes, not a new broad model-quality benchmark.

The candidate uses current full firmware, including the accepted power/Spectrum/M0 work, and is compared with the user-requested archived reference. This result does not isolate the read-clock effect from changes since the historical reference. No old control image or clock sweep was run.

`stress-performance.json` and `performance.json` are unmodified device outputs. `receipt.json` preserves the controller's return-readiness error and its stale candidate `final`: the exact return Flash write and verification succeeded, but the immediate post-reboot status was incomplete. `close-status.txt` and `close-verification.json` independently establish the actual final5D build with a bounded read-only check. Do not treat the stale `final` field as current state.

The preflight records are retained separately. The first attempt refused the then finished/asleep Spectrum foreground; the second hit a HOST drain timeout configuration error. The third successfully woke the already finished APP, then stopped because PHYSICAL_KEYS changed156→157 while it was closed; the cause of that physical event is unknown. That HOLD was preserved before the unchanged controller was started from the ready calculator. The coordinator's later STOP arrived after the first Flash had already begun; the coordinator then explicitly permitted only that already running child to finish. It held one immutable lease across stress, both measurements and the conditional return. No stress or inference was retried.

The package and source pins identify the tested artifacts; archived handoff files describe that past window and do not authorize a new hardware run. No other hardware candidate was started.
