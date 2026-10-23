# V145 checked exp endpoints

Private qualified candidate **8498B317**, based on frozen V144/4CA2268A.
It is not installed, committed, pushed or promoted. The coordinated
hardware transaction still names only frozen V138/83CF4AC4 and Qfplib.

The existing exp kernel already computed a Q62 enclosure for tiny
positive results, but then entered the general correctly rounded fallback
whenever the result was subnormal. V145 rounds that complete enclosure
directly to the uniform subnormal grid. It accepts only a strict RNE cell;
an overlapping midpoint still uses the unchanged cr_exp fallback. Zero,
minimum-normal and overflow endpoints have explicit interval checks.
The existing polynomial, coefficients, table and error radius5/10 are
unchanged. Variable shifts in the new helper use32-bit values only.

On the128 independently selected x values in[-746,-700], mean executed
ARM instructions improve from **3,373.02 to593.57**, versus **640.52 for
Qfplib**. All128 owned results match directed MPFR; Qfplib is wrong on105
of these inputs. The23-vector subset where both are correct is preserved
separately. All640 independent exp vectors have no instruction increase;
the five means improve. The three original exp matrix groups each save
one instruction per call. This is emulator evidence, not hardware cycles.

Fresh tests on this exact ELF:

- 176,440 actual ARM helper calls checked against exact integer RNE at
  both ends of the interval:68,075 accepted and108,365 safely declined.
- 58,302 public exp inputs around exact subnormal midpoints, dispatch
  boundaries, random underflow values and IEEE classes:zero errors.
- 40,196 independent random/special exp inputs:zero errors.
- All6,784 independent-domain cases and196 retained tiny pow cases pass
  MPFR. All196 tiny rows and all48 non-exp independent group records,
  including per-vector instructions, remain exactly V144's results.
- The complete original117-group matrix /23,352 cases passes:115 faster,
  two equal, zero slower. Its other116 chunk records remain byte-identical
  as JSON values; only three exp chunks improve. Thirty frozen public pow
  canaries also pass.
- M4 soft/hard ABI preprocessing and all allocated code/data remain
  identical to the original baseline; generic M0 code/data also match.

The fresh directed-MPFR total is **105,478 calls**, including99,138 exp
calls. The176,440 integer property calls and30 retained-oracle canaries
are additional. ARM calls verify callee-saved registers, SP and bounded
writes. All12 selected processes were observed at terminal exit0.
`terminal-observations.json` records those observations.

Every previously selected performance group is retained in the expanded
report: **171 groups /30,304 cases:156 faster,2 equal,13 slower** by raw
mean instructions. The remaining raw deficits are nine huge-argument
trig streams, three subnormal ln/log10/sqrt streams and medium-integer
pow. The full-fractional pow stream also loses on its16-vector subset
where both are correct, despite winning its raw mean. Individual slow
cases remain in other streams. These deficits are not discarded when
Qfplib returns an incorrect value.

The change adds **392 allocated Flash bytes** versus V144:32 more in the
existing exp entry and360 for the new helper. No tables, global RAM or
libgcc archive members are added. Image extent is1,537,400 bytes,392 more;
static RAM198,856, heap30,520 and scratch4,072 remain unchanged. The worst
fresh observed exp stack is488 bytes. V144's separately retained2,404-byte
pow stack observation is not represented as a new measurement here.

Only native_eabi_m0.cpp and the linker script differ from V144, within a
private646-file source tree. The exp entry address stays0x10176E98. Its
coefficient/polynomial prefix is exact. Every other object instruction/data
payload is retained;248 other linked numerical bodies are byte-identical,
and70 differ solely at actual old BL relocations to independently checked
equivalent five-instruction veneers. No other numerical function calls the
public exp entry. Scratch veneer slots are permuted, so scratch bytes and
cache behavior are not claimed identical. Physical cycles remain unmeasured.

`certificate.json` derives the endpoint bounds with exact rational
arithmetic and reruns the unchanged exp enclosure checker. `HANDOFF.json`
and `FROZEN.json` bind the exact image, source, reports and producers.
`verify.py` is read-only and runs from the repository root. Copy the package
and select new output paths before repeating producers, which write their
own reports. Unicorn JIT required execution outside the macOS sandbox;
these tests opened no USB devices.

The V144 package and all approved V138 hashes remain unchanged. Canonical
and release sources remain frozen. V145 is a candidate for a future
separate review; it is not substituted into the current hardware run.
Physical performance/platform/cold/full-restoration acceptance and the
unproved terminating general-pow path remain open. The existing final
undecided1,024-bit pow trap is retained. The overall goal is still active.
