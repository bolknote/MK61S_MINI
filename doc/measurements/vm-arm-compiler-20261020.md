# BASIC/FOCAL ARM compiler research: findings and closure

Date: 2026-10-20. Research branch: `feature/vm-arm-compiler`.
Source base: `9800654d238e19ba61fb3e796de6ca4f5729acb2`, not latest main.

Decision: stop this resource-bounded JIT approach as a production candidate.
Save the measurements and conclusions only. At the user's request, the
experimental compiler, emitters, fixtures and scripts have been removed from
the worktree; they are not included in this commit. Do not merge experimental
code into main or deploy it. No production code or memory limits were changed.

## Method and scope

The workload was unmodified Turochamp, level 2, opening book disabled: 25 entry
symbols, 24 unique modules, a verified LVP1 package of ordinary LBV2 images
occupying 48,256 bytes. All complete routes agreed on e2-e3, score 54, 420 nodes,
7662 module invocations and 205013 service polls. Numeric banks/tags, reference
registers, I/O-event hashes and module-route hashes were compared as well.

Target execution used Cortex-M4 Thumb-2 instructions in Unicorn, compiled with
GCC 14.2.1 and `-Os`, hard-float ABI. Counts below are executed ARM instructions,
**not CPU cycles or measured calculator seconds**. Emulator wall time is not a
hardware benchmark. The ARM whole-search probe used BINARY64 with owned math;
both BINARY64 and CORE received host correctness checks. These results do not
establish CORE hardware performance.

Verified bytecode was directly readable throughout. Filesystem OPEN, source
decompression, cold compilation, physical drawing, USB and keyboard latency
were excluded. No physical calculator was accessed or flashed. The oversized
full-AOT images were measured with an enlarged emulator mapping solely to
diagnose their cost; they did not fit a real Classic. The adaptive experiments
used the Classic F411's 512-KiB Flash and 128-KiB SRAM address ranges.

Each comparison has its own matched VM baseline. The small differences between
baseline counts below come from fixture layout/initialization, not a measured
production optimization between experiments.

## Full offline compilation

The existing frontend and verifier produced temporary LBV2 IR. Offline lowering
then generated C++ labels, direct control-flow edges, constants/resources and
shared numeric/I/O handlers; GCC emitted actual Thumb-2 instructions. The
native-only executable contained neither VM dispatch nor a reference bytecode
image. Existing Value layouts, arithmetic backends and language call/loop
semantics were retained. This was fixed-address offline AOT, not an on-device
compiler, relocatable APP or native-code sandbox.

| Representation | Program representation bytes | Whole-search ARM instructions |
|---|---:|---:|
| Compact bytecode + optimized VM | 48,256 | 638,045,264 |
| Shared-handler AOT | 856,905 | 524,685,814 |
| AOT with guarded int32 register blocks | 1,019,893 | 310,509,934 |

The shared-handler AOT saved 17.77% of instructions but expanded the program
17.76 times. Its representation included 769,296 bytes of code and 87,609 bytes
of constants/metadata. An earlier fully expanded form occupied 2,941,595 bytes.
Even individual native functions could exceed a 24-32-KiB executable working
set. Keeping code on external NOR would not make it directly executable.

The register variant added 1121 blocks covering 5127 static logical operations.
Unboxed int32 intermediates and combined guards reduced instruction count by
51.33% relative to VM, but the representation grew to 21.14 times bytecode size.
The optimized helpers alone occupied 136,440 bytes of text; the cold per-op
fallback and resume machinery were still present. This is a measurement of
these conservative compilers, not a lower bound on all native compilation.

Both full representations exceed Classic's entire 512-KiB internal Flash.
There was no deployable APP, on-device loader or board timing. A VM/native
instruction ratio of 2.055 is not evidence of a twofold calculator speedup.
CORE showed no meaningful host speedup in this test.

Correctness checks included BASIC/FOCAL calls and loops, I/O/yield, DATA,
graphics events, cancellation, relocated continuations and logical budgets.
The register variant passed 5984 differential ASan/UBSan scenarios per backend,
including overflow, signed zero, nonfinite/fractional inputs, late bounds
failures, aliases, error PCs and service cadence. Full host chess A/B/A matched
for both arithmetic backends. These checks did not qualify native stack/IRQ
headroom or physical USB/keyboard latency.

Details: [initial AOT](chess-arm-aot-poc-20261020.json),
[register AOT](chess-arm-aot-registers-20261020.json).

## Program-independent adaptive compilation

An intermediate offline-profiled hybrid was rejected: program-specific hot
lists are not an acceptable universal runtime policy. The subsequent adaptive
compiler used ordinary verified LBV2, generic frontend hints and bounded runtime
hotness only. It did not use a chess whitelist, trained PC list, precompiled
native sidecar or generated per-program runtime C++.

After eight visits, a small on-target emitter could compile an eligible integer
block into a borrowed executable workspace. It performed no speculative file
I/O and invoked no external compiler. Cold/unsupported blocks and failed guards
fell back to the optimized VM. All bank/control writes were delayed until
guards succeeded; overflow, signed zero, types, bounds, aliasing, service
quantum, logical budget and FOCAL frame limits retained their VM semantics.

The unchanged loan was 1152 bytes within the existing 8192-byte workspace,
starting at offset 1992 after ExecutionState and before the live Flash writer
and persistent values. Short mode used 16 heat entries and three LRU slots of
240 code bytes; all target cache data occupied 1024 bytes. Long mode used eight
heat entries and one 864-byte code slot, with 1032 bytes total cache data.
Neither mode introduced an additional global code-cache allocation.

Default mode revoked the cache at every executor entry. A separate retained-loan
mode measured callers that could preserve both workspace and immutable raw
LBV2 identity. Reader-backed/paged images and unversioned LBV1 could not retain
compiled code across entries. This was not complete resident loan/APP-swap
integration; CRC was a sampling hash, not executable-cache identity.

| Matched comparison | VM instructions | Adaptive instructions | Change |
|---|---:|---:|---:|
| Short blocks, revoke on entry | 638,165,574 | 665,290,729 | +4.25% |
| Short blocks, retained loan | 638,165,574 | 669,378,820 | +4.89% |
| Long traces, revoke on entry | 638,165,564 | 658,776,643 | +3.23% |
| Long traces, retained loan | 638,165,564 | 660,175,019 | +3.45% |

The longer traces kept up to three delayed scalar destinations in r8-r10,
forwarded reads and combined up to 24 logical operations across LINE/static
BASIC jumps. They stopped at I/O, calls, FOCAL unwinding or array-store
dependencies and rejected unsafe scalar/array aliasing conservatively.

Bytecode/package size stayed 48,256 bytes. The short and long compilers
added roughly 5.7 and 6.3 KiB of Flash/readonly code in standalone fixtures;
fixture static RAM stayed 8520 bytes on both matched routes. This did not mean
unchanged stack use: touched stack watermarks rose from VM's 920 bytes to
1648/1664 in short mode and 2304/2312 in long mode. Per-function frame checks
are not proof of total-stack or interrupt headroom.

The real monolithic LANGVM loaded-image gate also failed:

| Variant | Loaded bytes | Unchanged limit | Over limit |
|---|---:|---:|---:|
| Stock | 20,412 | 20,480 | 0 |
| Short adaptive compiler | 25,948 | 20,480 | 5468 |
| Long-trace compiler | 26,612 | 20,480 | 6132 |

These are loaded image/BSS figures, not compressed APP file sizes. The stock
linker rejected both experimental APPs; no deployable APP was produced and no
budget was relaxed. Packing or splitting a compiler would not by itself remove
its runtime cost.

Both backends passed 6048 differential scenarios and 37,596 direct leaf cases
each, plus policy checks and full host chess VM/adaptive/VM in both retention
modes. The long mode added 5120 multi-assignment scenarios per backend:
100 native successes, 2460 atomic denials and 2560 alias fallbacks. Tests covered
late guard failures, unchanged state on rejection, exact continuation and
service cadence. Emitted opcode forms were independently checked against the
GNU ARM assembler. This is semantic evidence, not device latency qualification.

Details: [short adaptive compiler](chess-adaptive-thumb-20261020.json),
[long traces and cost attribution](chess-adaptive-traces-20261020.json).

## Why stop rather than pack the compiler

Already-generated native blocks were substantially cheaper than integer_span
on identical logical work. An equal-weight generic corpus of arithmetic,
arrays, division, branches and FOCAL loops gave 87.23% fewer instructions for
short blocks and 89.78% fewer for long ones. This excluded compiler, cache lookup
and outer guards. It was a fragment diagnostic, not a whole-search estimate.
Every successful sample also had an untimed full-VM correctness oracle.

An exhaustive diagnostic of all 241 compilable chess entries produced 674
same-span comparisons, 16 atomic denials and 33 native-supported samples whose
operations the span did not support. The latter were full-VM checked but
excluded from direct-span speed sums. None of these diagnostic inputs or
weights was used for runtime selection.

Dynamic attribution of the same long-trace ELF and complete execution found:

| Component | Executed ARM instructions |
|---|---:|
| Runtime compiler | 17,122,231 |
| Manager/attempt, excluding compiler and generated code | 11,816,055 |
| Generated SRAM instructions | 1,529,847 |
| Complete adaptive search | 658,776,643 |

Hypothetically subtracting *all* compiler and manager/attempt cost leaves
629,838,357 instructions: only 1.30% fewer than VM's 638,165,564 at this same
native coverage. This is not a realizable free-check implementation, an
unlimited/perfect-cache bound or proof that native compilation cannot help.
It shows that packing this implementation or polishing its current manager
cannot deliver the intended minimum 20% whole-search reduction by itself.

The narrow native paths are cheap, but too little total work reaches them under
this cache/policy combination. The continuation criterion failed and the APP
still exceeded its limit. Further size-packing or moving the cold emitter into
another APP was therefore not pursued. Keep VM as the production path; a future
native experiment would need a materially different coverage/cost argument
and benefits on multiple programs before deployment work is justified.

## Archive interpretation

The four JSON reports preserve the measurement-time facts, hashes, paths and
chronological decisions. Their `changes_committed: false` fields describe the
time of the experiment, before this documentation-only commit. Earlier
`next_direction`/`next_action` text (including keeping sources) is superseded by
the closure decision above and the user's instruction to remove prototype code.

Source paths, commands and hashes inside those reports are historical provenance,
not links to runnable tools retained here. The code is intentionally not part
of this archive; the reports alone are insufficient to reproduce the prototype
from this commit. No generated native images, executable binaries, test sources
or experimental build/runtime scripts are committed with the research.
