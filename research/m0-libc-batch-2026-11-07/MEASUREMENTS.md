# Measured M0 libc defaults

All 672 matrix APP jobs are exported: 140,448 rows and 8,897,560 raw timer intervals. These defaults select existing measured bodies. Production main `d4b63fff9939fd08d3f620993bf01972adb97f2e`, containing the optimization commit `66a384e774ca6d78c4340f3dfb2f026792eded8e`, was installed as `F8996B0A` / `C315F42E` and passed two timer qualifications and all 16 final hardware guard runs. ROMCACHE was restored with a full readback, the test namespace was removed, and the coordinator independently accepted CLOSED.

| Function | Native Flash | Native gain | Standalone SDK | SDK gain |
|---|---|---:|---|---:|
| `strlen` | word2 | 13.55% | byte4 | 24.95% |
| `strcmp` | byte4 | 20.60% | byte4 | 12.84% |
| `strncmp` | byte4 | 13.18% | byte4 | 13.16% |
| `memcmp` | word2 | 37.28% | word2 | 36.93% |
| `strnlen` | byte4 | 16.52% | byte4 | 16.50% |
| `strcpy` | byte4 | 16.57% | byte4 | 16.54% |
| `strncpy` | byte4 | 26.31% | byte4 | 26.30% |
| `strncat` | byte4 | 26.68% | byte4 | 26.68% |

These are per-function gains under the frozen inverse-(length+1) workload, measured on RP2040 at 125 MHz with a qualified 1 us timer, normal IRQ and recorded cache/clock contexts. The SDK reference is the independent old SDK body. A public shared-runtime forwarder is not a local SDK baseline. Different firmware, power and input strata stay separate. No HOST time or subtracted loop overhead enters these figures.

`strlen` differs by role. Native word2 gains 13.55% in the primary workload, 12.71% on short inputs and 20.27% with equal length weights. Native byte4 was within the primary noise envelope but lost 69.02% with equal length weights. Standalone SDK byte4 gains 24.95%, 15.02% and 39.16% in those regimes; SDK word2 loses 5.70% on short inputs. Complete per-candidate short/long regression maps remain in the evidence package. An aggregate gain does not imply every individual input is faster.

Jobs 588 and 639 passed strict semantic/report validation; their timing is excluded after a reconnect/input boundary. Neither job was replayed. Other controlled segments are compared with the matching primary input subset, preserving all seven raw groups and explicit runtime N/A masks.

Native functions stay in Flash because the SRAM benefit was unresolved. No SRAM is added. The exact accepted AE2 source was rebuilt byte-for-byte before applying only the two M0 source files. The historical role-specific HOST composite `5DC48C46` / `E4529C63` has 120,368 bytes static RAM and 109,008 bytes heap against the unchanged 108,544 minimum. Native strlen word2 adds 32 bytes of text relative to the superseded all-byte4 choice; the padded 1,790,272-byte BIN size is unchanged. The superseded `BE6EAEC0` image must not be installed.

Both the clean committed-main snapshot and the exact AE2 composite build successfully. Actual native ELF/BIN bodies match the measured leaves; runtime26 points directly to slots 19/20/21/25. Normal packed standalone/shared SDK images contain the selected bodies and four real runtime tails. Actual M4 SDK translation units are byte-identical before/after this M0 policy; its Flash reserve contract is unchanged. The optimization commit changes only its own sources, tests and research records. The installed main also contains the separately accepted Spectrum protocol commit.

The installed `F8996B0A` image uses 120,384 bytes static RAM and has 108,992 bytes heap, meeting the unchanged 108,544-byte minimum. Firmware and fixture writes each matched their complete readbacks. The final guard covers 3,024 rows and 177,548 raw 1 us intervals: every function has short and long inputs on standalone and shared Flash routes. These results form a separate validation stratum; the table above retains the original campaign's selection metrics. The physical timer was requalified on both final routes, and all seven raw groups were retained.

The original install HOLD preserves an early `KBD=WAIT`, `PANEL_INIT=0`, uninitialized LCD snapshot. A separate read-only completion first stopped at the normal `SLEEP_USB` admission state, then an independently authorized identity wake and two strict RUN status reads passed. The final ROMCACHE restore used one write, a full 77,824-byte readback, a bounded six-second startup wait, one identity and two strict status reads. Final BUILD/CRC/heap, KBD/panel/LCD/DMA, QPI, 125/48 MHz clocks, physical-key counter and idle M3/error fields all passed. Original campaign jobs were not replayed. All processes were reaped, CDC descriptors and the existing coordinator lease closed, and `/M0LIBC-N7B1` was removed. The final image and valid ROMCACHE were handed to the next hardware owner after independent CLOSED.

Explicit per-function selector 0 retains its fallback. A nonzero `MK61_M0_LIBC_UNROLL` retains the diagnostic override. Shared runtime defaults retain native delegation. The semantic-package builder now forces all explicit SDK selectors to 0 for its historical baseline, so enabling production defaults cannot silently change that control. Its build-only checks also compare actual default native/SDK bodies with the independently forced candidate leaves.

Recheck the saved data without device access:

```sh
python3 research/m0-libc-batch-2026-11-07/stratified.py \
  --evidence-root .build/m0-libc-batch-20261107-v1 \
  --current .build/m0-libc-batch-20261107-v1/amendment-v10 \
  --campaign .build/m0-libc-batch-20261107-v1/amendment-v10/run-001/campaign/CAMPAIGN.json \
  --output /tmp/m0-libc-analysis
python3 tests/m0_libc_batch_selection_test.py
python3 tests/m0_libc_batch_analysis_test.py
```

The output directory must be new. Raw artifacts stay under `.build`; [MEASUREMENTS.json](MEASUREMENTS.json) records their hashes, selected regression counts, build proofs and final CLOSED evidence. Hardware validation for these defaults is complete. Restoring ROMCACHE invalidated the temporary fixture, so future experiments need a fresh qualified allocation. The historical execution checkout remains retained at the coordinator's request until a separate passive-pin archive and cleanup are accepted.
