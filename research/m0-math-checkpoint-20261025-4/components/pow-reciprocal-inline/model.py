"""Pure exact instruction-cost predicates; actual results/costs are measured."""
def inline_saving(D):
 index=(D>>9)-128;u=(1<<32)//(65536+512*index+256)
 p=((D+1)>>1)*u;e=(p-(1<<31))//65536
 estimate=u-(u*e//32768)
 return 5 if estimate<0xffffffff//D else 4

def expected_cost(denominator,parent_cost,products,seeds):
 exponent=(denominator>>52)&2047;magnitude=denominator&0x7fffffffffffffff
 if exponent==0:
  high=magnitude>>32;low=magnitude&0xffffffff
  if magnitude<=(1<<50):return 22 if high<(1<<18)else 24
  return parent_cost+(8 if high>(1<<18)else 11)
 if exponent>2044:return parent_cost+2
 return parent_cost-2*len(products)-sum(inline_saving(D)for D in seeds)
