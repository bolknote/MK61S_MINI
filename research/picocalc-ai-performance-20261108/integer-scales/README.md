# Group bias and exact FP16 product candidates

Both images were rebuilt on main660645cf1 to retain the qualified Spectrum
changes. The M3 BIOS, Spectrum APP, AY and ROM were untouched. Two candidate
passes at270 MHz used the same Q4 model, INT8 activations and2+2 token path;
the0.8931125 s/token reference was not rerun.

| Candidate | Decode seconds/token |
|---|---|
| Shared integer group bias |0.847044 /0.8472355 |
| Bias plus exact integer FP16 product |0.8017425 /0.8021775 |

The second candidate is installed as6FC0B45F/F8D9891E. Mean decode time is
10.21% below the reference. The main workspace retains this implementation.

For unsigned Q4 codes, sum((u-8)*x)=sum(u*x)-8*sum(x); group activation sums
are prepared once and reused for all output rows. INT8 reuses the existing
LUT storage and keeps the correction in int32.

For a32-value Q4/INT8 dot, abs(sum)<=32768. Multiplication by the finite
FP16 significand fits int32. One rounded integer-to-FP32 conversion plus an
exact exponent adjustment reproduces float(sum)*half_scale, including
subnormal FP16 scales. Signed zero is preserved; nonfinite inputs use the
original floating multiplication fallback. The following activation-scale
multiply and FP32 accumulation retain their order.

Validation:3,114,112 bit-exact scale checks,700 independent M3/scalar rows
including extremes and half scales, full logits/all modes,64-position KV,
DMA failure/cancel/join/guard checks, full model/UI ASan/UBSan and ARM builds.
On-device tokens and all-row checksums match. Final USB prompts were lost;
the controller retrieved each completed fresh durable report after confirming
RUNTIME=NONE, with model_load_us matching the captured run-specific load
marker. No inference replay or reference execution was performed.

Final state:125 MHz calculator, CLOSED/NONE, own launchers removed,
CDC/MSC/lease closed. These are short-context decode measurements.
