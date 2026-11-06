// Refine only the discarded final-product bits of the existing Q62 exp
// pass. Return0 if undecided,1 for the lower binary64 endpoint,2 for the
// upper endpoint. A rejected cell is near its midpoint and cannot cross
// a binade or endpoint under this bounded correction.
__attribute__((optimize("Os"),noinline,cold))
static unsigned exp_round_decide(unsigned index,uint32_t n,U magnitude,unsigned cell) {
  const U base=exp_table[index];
  const uint32_t al=uint32_t(base),ah=uint32_t(base>>32);
  const uint32_t bl=uint32_t(magnitude),bh=uint32_t(magnitude>>32);
  // Dropping the lower16-bit terms of the low product contributes
  // <2^17 to this carry sum, hence <2^-15 Q62 unit to the result.
  uint32_t low=al*bh;
  const uint32_t middle=ah*bl,bottom=(al>>16)*(bl>>16),zero=0;
  uint32_t high;
  // Only the carries and bit31 are needed. SBC starts the adjustment
  // at carry-1; the other carries accumulate modulo2^32, yielding -1..2.
  // This avoids constructing three uint64_t terms or subtracting1 later.
  // Keep the old184-byte cold slot so measured shared code/tables keep
  // their XIP indices. Subsection1 appends sixteen unused bytes after
  // the function and its literal pool; no branch or padding is executed.
  __asm__(".subsection 1\n\t"
          ".fill 8,2,0xbf00\n\t"
          ".subsection 0\n\t"
          ".syntax unified\n\t"
          "adds %[low],%[middle]\n\t"
          "sbcs %[high],%[high]\n\t"
          "adds %[low],%[bottom]\n\t"
          "adcs %[high],%[zero]\n\t"
          "lsls %[low],%[low],#1\n\t"
          "adcs %[high],%[zero]\n\t"
          ".syntax divided"
          : [low] "+&l"(low),[high] "=&l"(high)
          : [middle] "l"(middle),[bottom] "l"(bottom),[zero] "l"(zero)
          : "cc");
  int adjustment=int(high);
  if(cell&2048U) adjustment=-adjustment;
  int distance=int(cell&1023U)+adjustment-512;
  unsigned radius=distance<0?unsigned(-distance):unsigned(distance);
  if(cell&1024U) {
    distance+=adjustment;
    radius=(distance<0?unsigned(-distance):unsigned(distance))>>1;
  }
  // For normalized cells floor(abs(distance)/2)>3 and>2 are exactly
  // abs(distance)>7 and>5. Thus both forms share the same two radii.
  // Only radius3 can benefit from the tighter enclosure; smaller cells
  // need refinement and larger cells already have a uniform decision.
  if(radius!=3) return radius>3?2-(unsigned(distance)>>31):0;
  if(!n) return 0;
  // n!=0 implies e>=-11 and exact x*2^64. Existing Q94 table bits
  // and the exact split-reduction fraction can then certify error<3.
  const uint32_t reduction=n*exp_step_low;
  // |x|<1024 implies n<=2^20. The table fraction distance is<=2^31;
  // this sufficient bound therefore decides without loading that row.
  // exp_step_low is even, so reduction has no discarded half bit.
  bool tight=reduction<0xAFF7FFFCU;
  if(!tight) {
    const uint32_t fraction=refine_exp_table[index][0];
    const uint32_t distance=fraction&0x80000000U?0U-fraction:fraction;
    const uint32_t uncertainty=(reduction>>1)+((n+3U)>>2)+2;
    tight=uncertainty<(27U<<27)-distance;
  }
  return tight?2-(unsigned(distance)>>31):0;
}
