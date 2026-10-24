This review accepts only the new normal error4/tail511/positive-input/below
branch and the private shared-product delta. The already accepted inverse,
square, global radius, tiny/IEEE/refinement and adaptive-table proofs are reused
only after exact object/relocation/table binding. The rational calculations in
proof.py are independent of the producer's certificate result.

Let S=2^64, R<0, m=-R, Z=m²/S, and z the compensated square. The accepted
square bound is -1<=Z-z<1. Write v=2^44(r/6+r²/24+r³/120), and T for its
source integer approximation. Re-evaluation of the quantization terms gives
|v-T|<2.497143741<5/2. For t>=3, the source quadratic/t upper is a*t+b+c/t;
its convexity bounds it by its endpoint values on the entire protected t
interval, both below 1/3. The linear term exceeds t/3. The t=0,1,2 cases have
zero quadratic/fifth terms. Thus T<=0 for every negative residual, not just
the sampled inputs. Also v<0 and 1/2+v/2^44>0.

For M=-T, D=R+floor(z/2)-floor(z*M/2^44). Combining square error and z parity
contributes strictly less than 1 to true-polynomial minus D. The negative
floor contributes no positive error in this direction. The remaining
coefficient error is at most (5/2)z/2^44. Positive input with D<0 implies
n>0, R<0, and exact Q64 input scaling. If
f=((n*step_low) mod 2^32)/2^32, the reduction contributes at most
(n/2^33)/(1-1/1400)-f*(1-1/1400). The positive Taylor remainder plus the first
term is <1/256 Q64 units over the whole protected domain. Therefore
E-D < 1+(5/2)z/2^44-f*(1-1/1400)+1/256.

For b=-D, b>=m-z/2>=m(1-h/2)-1/2. The source H=1-high32(D) equals
1+ceil(b/2^32) modulo unsigned arithmetic; g=ceil(H/1024) gives
b+1/2<g*2^42. Consequently z/(g²*2^20)<6/5. The source's ceil(3g²/2^16)
therefore bounds the coefficient term in Q8. With f8=floor(256f),
max(f8-1,0)/256 <= f*(1-1/1400). Thus D8/256 is a strict upper for E-D.
All source products are bounded: g<=2939, curvature<=396; the largest effect
product plus its rounding constant fits uint32. The intentional n*step_low
and negative-displacement head operations are unsigned modular arithmetic.

Let A be the loaded Q62 table entry, T13 the retained partial-product integer,
P=floor((T13+2^63)/S), and F=(T13>>32) mod 2^32. The low 32 bits of T13 are
zero. In the certified A<2^63, b<2^54 domain, P-A*b/S <= rho, where
rho=(F>>31)-F/2^32: omitted products are nonnegative. This numerical oracle
is not asserted for unrestricted raw64 arguments; their parent/new scalar
equivalence instead follows from the instruction bijection.

The accepted adaptive bound gives A/S<(floor(q/2^48)+24)/65536. All 512 actual
Q62 and Q94 loaded table entries were recertified by strict integer 512th-power
inequalities. Their signed bias B0 and the exponential cross term obey the
retained cross bound <1/256. Hence
V-q < (D8/256)*top/65536+B0+rho+1/256.
The source effect is the upward-rounded first term in Q8; its bias is the
floor of 256B0; its product_upper is exactly ceil(256rho). Two further Q8 units
strictly cover bias quantization and the cross bound. Thus upper<=256 implies
V<q+1 strictly, including the equality boundary of the integer test. Since
tail511 places that midpoint at q+1 and unchanged radius4 excludes q-1023,
the unchanged normal pack returns the correct RNE value. Index0 cannot enter
this branch: a nonzero negative correction sets error6; zero correction has
tail0. Undecided inputs retain the byte-identical refinement.

R12 is not an extra result provided by scalar C ABI. For this exact linked
image, the real Flash veneer tail-jumps to the RAM leaf and preserves LR;
the leaf captures F before rounding and returns directly. The production
guard proves two STR instructions before the zero-byte GLOBAL HIDDEN capture
marker. This review additionally proves that all 88 instructions lying on a
marker-to-real-F-consumer path contain no R12 touch or call. Its guard controls
reject clobber/read/call/return/PC-write/escape/cycle alternatives. Integration
must rerun this linked-object closure on its actual new ELF, fresh disassembly,
veneer, compiler and flags. This component receipt is not integration approval.
