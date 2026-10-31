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
  const U cross=U(al*bh)+U(ah*bl)+uint32_t((al>>16)*(bl>>16));
  int adjustment=int((cross+(U(1)<<31))>>32)-1;
  if(cell&2048U) adjustment=-adjustment;
  unsigned guard=3; // Uniform absolute error is strictly below4 Q62.
  // n!=0 implies e>=-11 and exact x*2^64. Existing Q94 table bits
  // and the exact split-reduction fraction can then certify error<3.
  if(n) {
    const uint32_t fraction=refine_exp_table[index][0];
    const uint32_t distance=fraction&0x80000000U?0U-fraction:fraction;
    const uint32_t reduction=n*exp_step_low;
    const uint32_t uncertainty=(reduction>>1)+(reduction&1U)+((n+3U)>>2)+2;
    if(uncertainty<(27U<<27)-distance) guard=2;
  }
  if(cell&1024U) {adjustment*=2;guard=2*guard+1;}
  const int distance=int(cell&1023U)+adjustment-512;
  if(distance>int(guard)) return 2;
  if(distance<-int(guard)) return 1;
  return 0;
}
