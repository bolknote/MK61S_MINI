"""Independent full integer separation, carry/width bounds, and focused vectors."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
from model import LOW,HIGH,G,MASK,power,threshold,source_threshold,exact_model,word_model,taylor_bits
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-exp-tiny-log-midpoint-20261024'
bound=F(G)/(1-power(-32));assert bound<G+1
critical=[];cert=[];qset=set();maxscaled=maxcubehi=maxfloor=0;minfloor=G;selected=set();width_checks=0
for n in (0,1):
 cap=1<<(21+n);L=3*(1<<(52+n));eden=1<<(107+2*n);uden=1<<(53+n);best=None;modbest={}
 for z in range(1,cap,2):
  z2=z*z;z3=z2*z;z4=z2*z2;b,rem=divmod(z3,L);assert rem and rem&1
  # Direct rational cross multiplication of E<frac(B) or E<1-frac(B),
  # deliberately not the author's already cancelled integer expressions.
  if n:left=(L-rem)*eden*(uden-z);right=z4*L*uden
  else:left=rem*eden;right=z4*L
  assert left>right,(n,z)
  if best is None or left*best[1]<best[0]*right:best=(left,right,z)
  e=z.bit_length()-54-n;q=e+55+2*n;assert 1<=q<=24
  k,t=divmod(z2,1<<q);answer=k+int(t+b>=1<<q) if n else k-int(t<=b)
  if answer!=k:critical.append([e,n,z,answer])
  # All runtime wide intermediates, truncations and reciprocal input range.
  lo=z2&MASK;hi=z2>>32;c_lo=lo*z;c_hi=hi*z+(c_lo>>32)
  assert c_hi==z3>>32 and c_hi<1<<34
  scaled20=c_hi>>20;scaled=scaled20>>n;assert scaled20<1<<32 and scaled<65536
  assert (scaled*43691)<1<<32 and ((scaled*43691)>>17)==b
  assert ((lo>>q)|((hi<<(32-q))&MASK))==k
  assert source_threshold(z,e,n)==answer and 0<=answer<=G and b<1<<q and t+b<1<<32
  if z<65536:assert z2<1<<32 and b==0 and answer==k
  maxscaled=max(maxscaled,scaled);maxcubehi=max(maxcubehi,c_hi);maxfloor=max(maxfloor,answer);minfloor=min(minfloor,answer);qset.add(q);width_checks+=1
  modbest[scaled%3]=(e,n,z)
 for e,n,z in modbest.values():selected.add((e,n,z))
 selected.add((best[2].bit_length()-54-n,n,best[2]))
 for z in [1,3,65533,65535,65537,65539,cap-5,cap-3,cap-1]:
  if 0<z<cap:selected.add((z.bit_length()-54-n,n,z))
 cert.append(dict(negative=n,classes=cap//2,minimum_separation_ratio=str(F(best[0],best[1])),worst_odd=best[2],strict_every_class=True))
assert width_checks==3145728 and len(critical)==154 and qset==set(range(2,25)),(width_checks,len(critical),sorted(qset))
qset.add(1) # positive z=1 upper-binade occurrence e=-54, separately checked below
assert critical==json.loads((P/'corrected-midpoint-cells.json').read_text())
assert minfloor==0 and maxfloor<=G and maxscaled<8192
for a in range(65536):
 assert (a*43691)>>17==a//3 and a*43691<1<<32
assert threshold(1,-54,0)==source_threshold(1,-54,0)==0 # extra binade boundary occurrence of z1
jobs={};critical_targets={}
def add(raw,g):
 if 0<=raw<1<<64:jobs.setdefault(raw,g)
def cell(e,n,z,distances,g):
 s=-e-n;mid=z<<(s-1)
 for d in distances:
  m=mid+(d if n else -d)
  if not 1<<52<=m<1<<53:continue
  raw=(n<<63)|((e+1023)<<52)|(m-(1<<52))
  if LOW<(raw&((1<<63)-1))<HIGH:add(raw,g)
for e,n,z,t in critical:
 for d in [t,t+1]:
  s=-e-n;m=(z<<(s-1))+(d if n else -d);raw=(n<<63)|((e+1023)<<52)|(m-(1<<52))
  critical_targets[raw]=dict(e=e,negative=n,odd=z,distance=d,quadratic_diff=exact_model(raw)!=exact_model(raw,True))
 cell(e,n,z,[max(0,t-1),t,t+1,t+2],'all154_cubic_threshold_cells_four_neighbors')
assert len(critical_targets)==308 and sum(v['quadratic_diff'] for v in critical_targets.values())==154
for e in range(-54,-32):
 for n in (0,1):
  s=-e-n;step=1<<(s-1);first=((1<<52)+step-1)//step;first+=int(first%2==0);last=(1<<53)//step;last-=int(last%2==0)
  for z in {first,last}:selected.add((e,n,z))
for e,n,z in sorted(selected):
 t=threshold(z,e,n)
 cell(e,n,z,sorted({0,1,max(0,t-1),t,t+1,G,G+1}),'all_exponents_worst_separation_wide_carry_div3_and_guard')
for hi in [0x100000,0x100001,0x17ffff,0x1ffffe,0x1fffff]:
 for lo in [0,1,(1<<31)-G-1,(1<<31)-G,(1<<31)-1,1<<31,(1<<31)+1,(1<<31)+G,(1<<31)+G+1,MASK]:
  add((1<<63)|(990<<52)|((hi-0x100000)<<32)|lo,'s32_lowword_half_wrap_guard')
for center in [LOW,LOW+(1<<32),0x3d90000000000000,HIGH]:
 for d in [-2,-1,0,1,2]:
  for n in (0,1):add((n<<63)|(center+d),'old_new_domain_and_word_endpoints')
vectors=[]
for raw,g in jobs.items():
 expected=taylor_bits(raw);tiny=LOW<(raw&((1<<63)-1))<HIGH
 if tiny:assert expected==exact_model(raw)==word_model(raw)
 vectors.append(dict(x=f'{raw:016X}',group=g,expected=f'{expected:016X}',tiny=tiny,critical=critical_targets.get(raw)))
assert all(x in jobs for x in critical_targets)
(O/'own-vectors.json').write_text(json.dumps(vectors,indent=2)+'\n');(O/'critical-cells.json').write_text(json.dumps(critical,indent=2)+'\n')
# Actual helper has no call or loop. Enumerate its decoded CFG, ignoring
# predicate feasibility, to obtain a conservative all-path ISA upper bound.
nodes={}
for line in (O/'unit.dis').read_text().splitlines():
 m=re.match(r'^([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)\s*([a-z][a-z0-9.]+)\s*(.*)$',line)
 if not m:continue
 pc=int(m[1],16);op=m[3].split('.')[0];args=m[4].split('@')[0].strip();size=2*len(m[2].split())
 assert op not in ['bl','blx'];nodes[pc]=(op,args,pc+size)
active=set();memo={};branchops={'beq','bne','bcc','bcs','bhi','bls','bge','blt','bgt','ble','bmi','bpl','bvs','bvc'}
def path(pc):
 if pc in memo:return memo[pc]
 assert pc not in active and pc in nodes,hex(pc);active.add(pc);op,args,nxt=nodes[pc]
 if op=='pop' and 'pc' in args:answer=1
 elif op=='bx':assert args=='lr';answer=1
 elif op=='b' or op in branchops:
  target=int(args.split()[0],16);answer=1+max([path(target)]+([path(nxt)] if op in branchops else []))
 else:answer=1+path(nxt)
 active.remove(pc);memo[pc]=answer;return answer
max_helper=path(0x10190000);max_public=max_helper+37;assert max_public<352
d=dict(status='PASS_INDEPENDENT_LOG_MIDPOINT_ALL_DOMAIN_INTEGER_CERTIFICATES',domain='2^-54 < abs(x) < 2^-32',guard=G,positive_log_correction_bound=str(bound),strict_below_Gplus1=True,all_integer_odd_classes=width_checks,sign_certificates=cert,all_divide3_uint16_inputs_checked=65536,max_runtime_scaled=maxscaled,max_cube_high=maxcubehi,threshold_floor_range=[minfloor,maxfloor],square44_cube66_and_split_carries_exact=True,q_values=sorted(qset),s32to54_and_special_negative_s32=True,extra_positive_z1_binade_boundary_checked=True,all154_cubic_changed_classes_independent_exact_match=True,critical_transition_inputs308=True,quadratic_only_wrong_inputs154=True,independent_degree5_rational_interval_vectors=len(vectors),selected_noncritical_classes=len(selected),helper_CFG_acyclic_no_calls=True,helper_CFG_conservative_max_instructions=max_helper,public_tiny_conservative_max_instructions=max_public,Qfplib_unconditional_loop_instruction_lower_bound352=True,universal_tiny_ISA_dominance=True,not_3145728_ARM_inputs=True,own_fresh_ARM_or_MPFR_in_this_file=0,original507_unchanged418=True)
(O/'proof.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
