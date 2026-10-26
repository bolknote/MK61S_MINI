"""Resume only literal pack binding after a reviewer wrapper-whitespace mismatch.

The completed guard result is retained; no guard control is repeated here.
"""
import hashlib,json,subprocess
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-near-one-20261024'
def ref(p):p=Path(p);data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
assert json.loads((O/'private-guard-controls.json').read_text())['live_instructions']==88
frag=(W/'small-fragment.cpp').read_text();first=frag.index('  const unsigned shift=unsigned(16-e)');pack=frag[first:frag.rindex('\n}')]
pack=pack.replace('if(unsafe) return bits(exp_refine(real(a),0));','if(unsafe) return UINT64_MAX;')
expected='''#include <stdint.h>
using U=uint64_t;
extern "C" __attribute__((optimize("Os"))) U audit_exp_small_pack(U a,U correction,U error64) {
 const bool negative=bool(a>>63);
 const int e=int((a>>52)&2047U)-1023;
 const uint32_t lo=uint32_t(a),hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U;
 const U m=(U(hi)<<32)|lo;
 const uint32_t error=uint32_t(error64);
'''+pack+'\n}\n'
assert expected==(W/'pack-unit.cpp').read_text()
certificate=json.loads((W/'certificate.json').read_text());d=O/'literal-rebuild';d.mkdir();commands=[];results=[]
for oldcmd in certificate['commands']:
 cmd=list(oldcmd);oldout=Path(cmd[cmd.index('-o')+1]);cmd[cmd.index('-o')+1]=str(d/oldout.name)
 cmd=[str(d/'pack-unit.o')if x==str(W/'pack-unit.o')else x for x in cmd]
 p=subprocess.run(cmd,cwd=W,capture_output=True)
 (d/(oldout.name+'.stdout')).write_bytes(p.stdout);(d/(oldout.name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (d/oldout.name).read_bytes()==oldout.read_bytes()
 commands.append(cmd);results.append(ref(d/oldout.name))
out=dict(status='PASS_LITERAL_SOURCE_PACK_AND_TWO_WHOLE_EXACT_REBUILDS',source=ref(W/'pack-unit.cpp'),
 fragment_sha256=hashlib.sha256(pack.encode()).hexdigest(),commands=commands,results=results,
 only_fallback_sentinel_replaced=True,reviewer_initial_whitespace_assertion_failed_before_any_unit_build=True,
 completed_guard_controls_not_repeated=True,hardware_IO=0,integration_GO=False)
with (O/'literal-unit-binding.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'literal-unit-binding.json'),indent=2))
