"""Account for IPA's lost sign fact after the C++ normal body is outlined."""
from pathlib import Path
import difflib
import hashlib
import json
import re

W=Path(__file__).resolve().parent
def normalized(name):
    text=(W/name).read_text();out=[]
    for line in text.splitlines():
        m=re.match(r'\s*[0-9a-f]+:\s+[0-9a-f ]+\t([a-z][a-z0-9.]*)\s*(.*)',line)
        if not m:continue
        op,operand=m.groups();operand=operand.split('@')[0].strip()
        if op.startswith(('b','ldr')):
            operand=re.sub(r'\b[0-9a-f]+ <[^>]+>','<target>',operand)
            if '[pc,' in operand:operand=re.sub(r'#\d+','#offset',operand)
        out.append(op+' '+operand)
    words=re.findall(r'\b\.word\s+0x([0-9a-f]+)',text)
    relocs=re.findall(r'\b(R_ARM_\w+)\s+(\S+)',text)
    return out,words,relocs
a,wa,ra=normalized('control-raw-object.dis')
b,wb,rb=normalized('candidate-raw-object.dis')
assert wa==wb and ra==rb
changes=[]
for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes():
    if op!='equal':changes.append(dict(kind=op,parent=a[i:j],candidate=b[k:l]))
assert changes==[dict(kind='replace',parent=['lsrs r3, r3, #20'],candidate=['lsls r3, r3, #1','lsrs r3, r3, #21']),dict(kind='insert',parent=[],candidate=['nop '])]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=dict(status='PASS_RAW_BODY_OBJECT_DIFF_ONLY_EXPLICIT_SIGN_MASK_AND_ALIGNMENT',
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    parent_full_object_sha256=sha(W/'control-full.o'),candidate_full_object_sha256=sha(W/'candidate-full.o'),
    normalized_instruction_changes=changes,raw_literal_words_identical=True,raw_relocation_target_names_and_types_identical=True,
    actual_extra_instruction='lsls r3,#1 followed by lsrs#21 implements(high>>20)&2047; old caller proved signzero so compiler emitted lsrs#20.',
    valid_domain_equivalence='For routed positive normals, high bit31 is0, so the two sequences are exactly equal.',
    object_bytes_delta=4,one_extra_runtime_instruction_plus_alignment_nop=True,
    normalization='Displacement/immediate PC load offsets and branch target addresses normalized; all actual literal words and ordered relocation target names/types separately compared.',hardware_accessed=False)
(W/'raw-mask-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
