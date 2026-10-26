"""Check every shared-section byte outside the helper and its alignment."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
images=[ElfImage(W/(s+'-full.o')) for s in ('control','candidate')]
records=[];parts=[]
for image in images:
    target=image.sections.index(image.named_sections['.m0_pow_extension'])
    members={};parts.append(image.bytes_at(image.named_sections['.m0_pow_extension']))
    for section in image.sections:
        if section[1]!=2:
            continue
        strings=image.sections[section[6]]
        names=image.data[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            n,value,size,info,other,index=struct.unpack_from('<IIIBBH',image.data,offset)
            if index==target and size and info&15==2:
                members[image.string(names,n)]=(value&~1,size)
    records.append(members)
assert set(records[0])==set(records[1]) and len(records[0])==4
for name in records[0]:
    if name=='mk61_m0_log_ratio70_slow':
        continue
    a,size=records[0][name];b,new_size=records[1][name]
    assert size==new_size and parts[0][a:a+size]==parts[1][b:b+new_size],name
start=records[0]['mk61_m0_log_ratio70_slow'][0]
assert start==records[1]['mk61_m0_log_ratio70_slow'][0]
ends=[m['pow_fast_log'][0] for m in records]
assert parts[0][:start]==parts[1][:start] and parts[0][ends[0]:]==parts[1][ends[1]:]
assert len(parts[1])-len(parts[0])==212
out=dict(status='PASS_ONLY_HELPER_AND_IMMEDIATE_ALIGNMENT_REGION_CHANGES',
    old_members=records[0],new_members=records[1],changed_extent_parent=[start,ends[0]],
    changed_extent_candidate=[start,ends[1]],all_other_shared_bytes_identical=True,
    source_sha256=hashlib.sha256((W/'native_eabi_m0_log70_center.inc').read_bytes()).hexdigest(),
    candidate_ELF_sha256=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest(),hardware_accessed=False)
(W/'shared-section-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
