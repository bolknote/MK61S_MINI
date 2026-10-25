// Exact binary64 fused multiply-add. Included inside namespace m0_eabi.
// A 106-bit product is aligned in 128 bits with 21 spare low bits. Alignment
// discards bits only when the operands cannot closely cancel; jam preserves
// the direction of every discarded nonzero tail for the final RNE rounding.
__attribute__((always_inline)) inline Product fma_left(Product p,unsigned n) {
  if(!n) return p;
  if(n>=64) return {p.low<<(n-64),0};
  return {(p.high<<n)|(p.low>>(64-n)),p.low<<n};
}
__attribute__((always_inline)) inline Product fma_right(Product p,unsigned n) {
  if(!n) return p;
  if(n>=128) return {0,U((p.high|p.low)!=0)};
  if(n>=64) return {0,jam(p.high,n-64)|U(p.low!=0)};
  return {p.high>>n,(p.low>>n)|(p.high<<(64-n))|U((p.low<<(64-n))!=0)};
}
__attribute__((always_inline)) inline bool fma_less(Product a,Product b) {
  return a.high!=b.high?a.high<b.high:a.low<b.low;
}
U fused(U a,U b,U c) {
  const U ma=a&D::Magnitude,mb=b&D::Magnitude,mc=c&D::Magnitude;
  U sign=(a^b)&D::Sign;
  if(D::is_nan(a)||D::is_nan(b)) return D::nan(a,b);
  if(D::is_nan(c)) return c|D::Quiet;
  if(ma==D::Infinity || mb==D::Infinity) {
    if(!ma || !mb || (mc==D::Infinity && ((sign^c)&D::Sign)))
      return D::Infinity|D::Quiet;
    return sign|D::Infinity;
  }
  if(mc==D::Infinity) return c;
  if(!ma || !mb) return mc?c:(sign&c&D::Sign);
  int ea,eb;
  const U sa=D::normalize(a,ea),sb=D::normalize(b,eb);
  Product p=multiply(sa,sb);
  const bool top=(p.high&(U(1)<<41))!=0;
  int e=ea+eb+int(top);
  p=fma_left(p,top?21:22); // leading bit 126, no precision loss
  if(mc) {
    int ec;const U sc=D::normalize(c,ec);
    Product q={sc<<10,0};
    if(ec>e) {p=fma_right(p,unsigned(ec-e));e=ec;}
    else q=fma_right(q,unsigned(e-ec));
    if(!((sign^c)&D::Sign)) {
      const U low=p.low+q.low;
      p={p.high+q.high+U(low<p.low),low};
    } else {
      if(fma_less(p,q)) {const Product t=p;p=q;q=t;sign^=D::Sign;}
      const U low=p.low-q.low;
      p={p.high-q.high-U(p.low<q.low),low};
      if(!(p.high|p.low)) return 0;
    }
  }
  const unsigned leading=p.high?clz64(p.high):64+clz64(p.low);
  const unsigned bit=127-leading;
  e+=int(bit)-126;
  const U sig=bit>=55?fma_right(p,bit-55).low:p.low<<(55-bit);
  return D::pack(sign,e,sig);
}
