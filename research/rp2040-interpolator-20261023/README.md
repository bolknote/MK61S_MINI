# RP2040 interpolator arithmetic experiment — 2026-10-23

Status: archived research; V3 and the follow-on measurements finished on
2026-10-23. `COMBINED-HANDOFF.json`, `followon/STATE.json` and
`followon/RESULTS.json` retain the exact historical outcomes and limitations.
**No production selection or new hardware admission is made by this archive.**
The preparation notes below describe their original stage. V2 is retained as a historical
packet with timed-integrity HOLD after an independent MSB counterexample.
The user requested all three experiments and coordination with the chat
«Координатор». That chat owns hardware scheduling. This work owns only this
directory and `.build/rp2040-interpolator-20261023/`. Production sources, the
Git index, firmware and serial ports have not been changed by this experiment.

The experiments cover:

* Exact `32×8→40`, `32×32→64`, and rounded Q62 products using unsigned blend.
* Q31 sqrt/inverse-sqrt initial approximations and a Q32 inverse-sqrt seed.
  Each new interpolation algorithm has a CPU implementation using the same
  endpoints and correction, so algorithm changes cannot masquerade as hardware
  gains. These are seed-stage experiments, not complete binary64 replacements.
* The actual address patterns of `exp_table[512]`, split `log70_low/high`, and
  `refine_log_table[1024][3]`. Synthetic bases are returned as numbers; they are
  never dereferenced. This measures address formation, not full functions or
  table-memory latency.

`generate.py` certifies all 131,072 index/alpha cells with integer endpoint
bounds and analytic Newton error bounds. The Q32 inverse seed bound is
10.404 units; the Q31 sqrt seed bound is 1.586 units and its inverse bound is
5.202. Independent integer oracles and actual Thumb instructions test the
linked APP kernels. A functional SIO model supplies peripheral results only;
instruction counts are not RP2040 cycle counts.

Initial instruction counts favor the existing arithmetic: general wide32 is
22 versus 77 instructions, Q62 approximately 152–158 versus 369–374, and
the existing sqrt seed pair is 56 versus approximately 296. Address formation
saves 1–3 instructions with an already configured interpolator. Exact counts
for each frozen APP are in its `arm-validation.json`. Hardware timing remains
necessary, including configuration and state preservation costs.

Four APPs keep the loaded size below the available A748 RAM headroom:

| APP | Experiment | Loaded image + BSS | Rows |
|---|---|---:|---:|
| IALU | Exact integer/Q62 products | 10,724 B | 18 |
| IRSQ | Inverse-root seed | 11,860 B | 12 |
| ISQRT | Root/inverse-root seed pair | 20,404 B | 12 |
| IADDR | Table-address patterns | 9,500 B | 18 |

The earlier monolithic INTERP.APP is superseded and has no hardware admission.
Packet V1 is also superseded: its rotate/XOR batch checksum erased periodic
result contributions. V2's multiply-based FNV fold plus index passed a repeated
bit0/position7 regression, but an independent actual ARM test found that
128 repeated bit31 errors also cancel. That earlier check established only its
specific bit0 case and did not certify all periodic faults. V2 timed integrity
is therefore HOLD. V3 mixes low and high result words sequentially, with a
right-shift mix after each multiply. Actual ARM4096-step tests detect each of
the 64 result bits at every one of the 32 repeated positions: 2048 negatives,
each with 128 errors. The original V2 MSB counterexample is reproduced and
closed explicitly. This finite test does not prove arbitrary corruption
detection by a 32-bit checksum. Mathematical sources/tables/certificates remain
unchanged; exact new linked APP ELFs are separately requalified because their
literal addresses changed. V3 adds eight loaded bytes to each APP.
The A748 static main-RAM headroom is 30,760 bytes; this is not a guarantee of
the live allocator's largest free block. The frozen accepted loader is tested
against the exact compressed APPs, including CRC rejection and relocation at
two valid addresses. Its 64-byte header and streaming decode avoid a second
whole-image allocation; `calloc(memory_size+7)` and live allocations still
require the operator's preflight. CPU stack remains separately reserved.

Each APP uses 4096-call batches, seven rotating ABBA/BAAB rounds, empty-call
references and V3 result checksums. Raw TIMERAWL microseconds are retained, including
negative paired differences; there is no CPU cycle counter. CLK_SYS/PLL_SYS
registers are read before/after and interpreted for the fixed 12 MHz Pico H
crystal and 125 MHz accepted build. File output and firmware service calls are
outside measured sections. Prepared batches amortise configuration; transaction
batches include saving/configuring/restoring both interpolators on every
candidate call. Interrupts remain enabled. The checksum and loop remain inside
all raw timings, including the empty reference. The V3 decoder performs no
empty-time subtraction and makes no kernel-only speed claim. It requires result
schema3, so historical V2 result bytes cannot be silently admitted as V3.

All ACCUM/BASE/CTRL state on core0 INTERP0/1 and the initially idle divider are
restored and checked after batches. POP is never read. The frozen A748 source,
link map, privilege and ABI audit is in `firmware-proof/report.json`; core1 has
independent banks. The APP rejects an unexpected core, privilege, handler mode,
interrupt mask or busy divider. The target is UID `E6657CD423721C35`, build
`A7483AE6`. A current exclusive hardware handoff is still required.

Reproduce offline:

```sh
python3 research/rp2040-interpolator-20261023/generate.py --check
python3 research/rp2040-interpolator-20261023/prepare.py
python3 research/rp2040-interpolator-20261023/build-app.py --output .build/rp2040-interpolator-20261023/app-v3
.build/picocalc-apps-arm-venv/bin/python research/rp2040-interpolator-20261023/verify.py --variant alu --elf .build/rp2040-interpolator-20261023/app-v3/alu/IALU.elf --output .build/rp2040-interpolator-20261023/app-v3/alu/arm-validation.json --samples 5000
.build/picocalc-apps-arm-venv/bin/python research/rp2040-interpolator-20261023/app-self-test.py --variant alu --output .build/rp2040-interpolator-20261023/protocol-v3b-alu
.build/picocalc-apps-arm-venv/bin/python research/rp2040-interpolator-20261023/checksum-self-test.py --output .build/rp2040-interpolator-20261023/checksum-v3-NEW
python3 research/rp2040-interpolator-20261023/firmware-proof.py --apps .build/rp2040-interpolator-20261023/app-v3/app-manifest.json --output .build/rp2040-interpolator-20261023/firmware-proof-v3
python3 research/rp2040-interpolator-20261023/freeze-v3.py --output .build/rp2040-interpolator-20261023/packet-v3-NEW
```

Repeat the ARM/protocol commands for `rsqrt/IRSQ`, `sqrt/ISQRT` and
`address/IADDR`. Unicorn needs executable-memory permission on this macOS host.
Protocol tests use the exact source with shortened loops and synthetic
timer/filesystem callbacks; shipping APP numerical kernels are tested
separately. Fault cases include wrong core, busy divider, corrupt SIO result,
bad clock/state/result/checksum admission. Failed preparation attempts and old
drafts are not physical measurements.

No new hardware runner is improvised over the legacy ALU HIL script. The
coordinator is supplying the accepted framed CDC/state/RTC/SD preservation
primitives. The hardware packet must preserve the original SD tree/bytes,
calculator/IP/CWD and RTC, use only `/INTRP01`, retrieve `RESULT.bin` after each
APP, remove only its exact created objects, and close serial. No reset, Flash,
firmware replacement or production adoption is needed to collect these data.
The separate adapter-packet-v1 stays frozen as reviewed V2 carrier context; it
hardcodes the V2 manifest and is not a V3 hardware binding. Its five providers
remain null. A future accepted firmware base also needs new exact source/ELF,
ABI, loader, ownership and preservation review before a hardware lease.

## Archive boundary — 2026-10-31

This directory preserves the numerical experiment sources, offline tests and
closed historical handoffs. Absolute paths identify the original evidence in
`.build`; those packets remain preserved outside Git. Historical manifests and
failed attempts are unchanged. Hardware commands below are historical
reproduction notes and carry no current permission to access a device.

The unfinished `display-profile/` and `display-scroll/` diagnostic campaigns are
not included. Their working copies and evidence remain preserved separately;
they are not accepted production changes. No canonical mathematics, SDK or
firmware is modified by this archive. `ARCHIVE.json` records original file
identities; this README adds the archive explanation. One extra blank line at
the end of `followon/exact_oracle.py` is removed, with its Python AST unchanged.
