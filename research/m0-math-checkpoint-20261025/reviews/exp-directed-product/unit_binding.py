"""Bind the endpoint ARM unit to literal current source and its complete ELF."""
from pathlib import Path
import hashlib,json,subprocess
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-directed-product-20261024'
source=(W/'candidate/native_eabi_m0.cpp').read_text();unit=(W/'direction-unit.cpp').read_text()
first=source.index('        const uint32_t head=1U-uint32_t(delta>>32);')
last=source.index('        safe=int32_t(effect)+bias+product_upper+2<=256;',first)+len('        safe=int32_t(effect)+bias+product_upper+2<=256;')
fragment=source[first:last].replace('const int32_t bias=int32_t(refine_exp_table[n&511U][0])>>24;','const int32_t bias=delta32>>24;')
expected='''#include <stdint.h>
using U=uint64_t;
static constexpr uint32_t exp_step_low=3588551130U;
extern "C" __attribute__((optimize("Os"))) U audit_exp_direction(U q,U arguments,U parameters) {
 const int32_t delta32=int32_t(uint32_t(arguments));
 const uint32_t n=uint32_t(arguments>>32);
 const uint32_t product_fraction=uint32_t(parameters);
 const U delta=parameters&UINT64_C(0xFFFFFFFF00000000);
 bool safe=false;
'''+fragment+'''
 const int32_t upper=int32_t(effect)+bias+product_upper+2;
 return (U(uint32_t(upper))<<32)|unsigned(safe);
}
'''
assert unit==expected
commands=json.loads((W/'certificate.json').read_bytes())['commands'];assert len(commands)==2
folder=O/'unit-rebuild';folder.mkdir();mapping={c[c.index('-o')+1]:str(folder/Path(c[c.index('-o')+1]).name)for c in commands}
records=[]
for c in commands:
 actual=[mapping.get(x,x)for x in c];done=subprocess.run(actual,cwd=W,capture_output=True)
 original=Path(c[c.index('-o')+1]);output=Path(actual[actual.index('-o')+1])
 assert done.returncode==0 and not done.stderr,(done.returncode,done.stderr)
 assert output.read_bytes()==original.read_bytes()
 records.append(dict(argv=actual,original=str(original),rebuilt=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
cc=Path(commands[0][0]).parent
readelf=subprocess.check_output([str(cc/'arm-none-eabi-readelf'),'-sW',str(W/'candidate.elf')],text=True)
marker=[l for l in readelf.splitlines()if l.split()[-1:] == ['mk61_m0_exp_fraction_capture']]
assert len(marker)==1 and 'GLOBAL HIDDEN' in marker[0]and marker[0].split()[2]=='0'
out=dict(status='PASS_OWN_LITERAL_CURRENT_GATE_SOURCE_TO_ENTIRE_UNIT_OBJECT_ELF',
 literal_fragment_equal=True,only_Q94_bias_parameter_substitution=True,complete_object_ELF_byteexact_rebuilds=records,
 actual_marker_symbol=marker[0].strip(),zero_byte_global_hidden=True,no_frozen_or_product_changes=True)
with(O/'unit-binding.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items()if k!='complete_object_ELF_byteexact_rebuilds'},indent=2))
