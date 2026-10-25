# Bounded exact software seed correction

The outer entry is still private numerator+1: raw R0=0 and R1=0x3ff00000,
with any binary64 denominator in R2:R3. Only its software inline seed changes.
This macro now explicitly requires R0=0; it is not a generic seed ABI.
The guarded software prefix does not read or change R0 before the macro.

With fixed256-byte table and D in[65536,131071], the unchanged estimate q
differs from floor((2^32-1)/D) by k in[-1,3]. The complete finite domain is
checked by exact integer arithmetic and by actual Thumb under every one of
the16 incoming NZCV combinations. The nonnegative residual path is unchanged.

For a negative signed residual R=(2^32-1)-qD, k is1,2 or3 and
R belongs to[-kD,-(k-1)D-1]. These values are far from signed overflow.
The first SUB q,1; ADD R,D exits on BPL exactly when k=1. Otherwise q is
decremented again and R gains D again. At k=2 that unsigned ADD wraps and
sets carry; at k=3 the residual is still negative and there is no carry.
An immediately following SBC q,R0, with known R0=0, therefore subtracts0
at k=2 and1 at k=3. The returned exact quotient is identical in all cases.

For k=3 only, R7 retains old residual minus D rather than the final positive
residual. R7 has no read between the seed and the second unsigned product,
which overwrites it before use. The existing ADD q,1; LSR q,1 produces the
same R6 and flags before NR refinement, since q lies in[32768,65535] and the
ADD cannot overflow. All other inline live registers and SP are unchanged.

The complete private root path checks raw R0, seed divisor, the one permitted
dead R7 difference before the second product, then every R0-R7/R12/SP/NZCV
and saved28-byte frame after that product. Every following residual,
certificate and pack state is identical. Guards, fallback and RNE decisions
are unchanged. The all-D unit checks exact quotient, private context and the
specified dead residual difference under every incoming flag combination.

The change removes three executed instructions when k=3 and leaves counts
unchanged otherwise. BPL also changes the branch direction for k=1; physical
cycle effects require measurement. There is no claim of universal device
speed parity from instruction counts, nor of whole-library completion.
The seed table, hardware path, READY latency gap, M4 and default M0 stay
unchanged. General pow totality and final source integration remain separate.
