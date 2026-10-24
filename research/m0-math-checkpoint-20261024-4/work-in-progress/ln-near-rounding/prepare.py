"""Reuse exact rounding remainders and the signed near-ln residual."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-enclosure-20261024'
assert hashlib.sha256((BASE/'result.json').read_bytes()).hexdigest()=='9c40ecbe12d871cff65e65cf40672c0b9325314ec0828c797f7d19913a89ad02'
for name in ('native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log10.inc',
             'native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','ratio.S'):
    shutil.copyfile(BASE/name,W/name)
old=(BASE/'native_eabi_m0_log70.inc').read_text()
anchor='__attribute__((always_inline)) inline double ln_pack_relative('
assert old.count(anchor)==1
packer='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// The polynomial division remainders give an exact integer bias. The
// known h residual removes its symmetric quotient error from the gate.
__attribute__((always_inline)) inline double ln_near_round_pack(U low,uint32_t high,U sign,
    int32_t bias12,int32_t residue,uint32_t den,bool add,bool exact_center,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t distance=tail>half?tail-half:half-tail;
  bool safe=distance>=4;
  if(!safe && distance) {
    if(exact_center) safe=true;
    else if(bool(tail>half)==add)
      safe=int32_t(den)*(int32_t(12*distance)-bias12)+12*residue>=18*int32_t(den);
    else safe=int32_t(den)*(int32_t(12*distance)+bias12)-12*residue>=21*int32_t(den);
  }
  if(!safe) return ln_refine(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
#endif
'''
new=old.replace(anchor,packer+anchor)
anchor='  U low=log_near_table[index-1][1];uint32_t high=0;\n'
assert new.count(anchor)==1
new=new.replace(anchor,anchor+'''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  int32_t bias12=0,residue=0;
  const uint32_t den=8064U+index;
#endif
''')
anchor='    const U correction=subtract?odd+even:odd-even;\n'
assert new.count(anchor)==1
new=new.replace(anchor,anchor+'''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    const int32_t r2=-int32_t(z&1U);
    const int32_t r3=int32_t(cube)-3*int32_t(third);
    const int32_t r4=int32_t((fourth+2)&3U)-2;
    const int32_t even_bias=6*r2+3*r4;
    bias12=-4*r3+(subtract?-even_bias:even_bias);
    residue=int32_t((uint32_t(delta)<<21)-uint32_t(h)*den);
#endif
''')
anchor='  return ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x);'
assert new.count(anchor)==1
new=new.replace(anchor,'''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  return ln_near_round_pack(low,high,negative?D::Sign:0,bias12,residue,den,subtract==negative,!delta,x);
#else
'''+anchor+'\n#endif')
(W/'native_eabi_m0_log70.inc').write_text(new)
(W/'near-rounding-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
    fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc')))
for name in ('build.py','probe.py','bind-public.py','make-qualification.py'):
    code=(BASE/name).read_text()
    code=code.replace("BASE = ROOT/'.build/m0-log-ratio-dirty-20261024'","BASE = ROOT/'.build/m0-ln-enclosure-20261024'")
    code=code.replace("BASE=ROOT/'.build/m0-log-ratio-dirty-20261024'","BASE=ROOT/'.build/m0-ln-enclosure-20261024'")
    code=code.replace('4e1a6b9151b96b5f9355e75c891c508809cad22d6c67fb9ef33354485acd5dff',
                      '36d1662268eaa35b5bd688fb7c2ff16958c1bc46dd92166dab5722e96b6f62f6')
    code=code.replace("ROOT/'.build/m0-log-ratio-dirty-20261024/remaining-slower.json'",
                      "ROOT/'.build/m0-ln-enclosure-20261024/remaining-slower.json'")
    if name=='probe.py':
        code=code.replace('PASS_PRIVATE_LN_STRICT_ENCLOSURE_PROBE_NOT_QUALIFICATION','PASS_PRIVATE_NEAR_LN_ROUNDING_PROBE_NOT_QUALIFICATION')
    if name=='make-qualification.py':
        code=code.replace('PASS_PRIVATE_LN_STRICT_ENCLOSURE_PROBE_NOT_QUALIFICATION','PASS_PRIVATE_NEAR_LN_ROUNDING_PROBE_NOT_QUALIFICATION')
        code=code.replace('PASS_LN_STRICT_ENCLOSURE_ALL_INPUTS_PROFILED_NOT_PRODUCTION','PASS_NEAR_LN_ROUNDING_ALL_INPUTS_PROFILED_NOT_PRODUCTION')
        code=code.replace("assert retained==len(parent['rows'])==29814","assert retained==len(parent['rows'])==39318")
    (W/name).write_text(code)
(W/'preparation.json').write_text(json.dumps(dict(status='PRIVATE_NEAR_LN_ROUNDING_CANDIDATE',
    source_sha256=hashlib.sha256(new.encode()).hexdigest(),parent_unchanged=True,canonical_or_device_changed=False),indent=2)+'\n')
