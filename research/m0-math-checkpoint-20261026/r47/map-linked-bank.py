"""Static parent/child hotbank mapping; no assertion of literal byte identity."""
from pathlib import Path
import hashlib,json,re,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
roots={'parent':ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026','candidate':W}
assert sha(roots['parent']/'FROZEN.json')=='dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'
TC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
for tag,p in roots.items():
    link=json.loads((p/'link-result.json').read_text())
    assert sha(p/'candidate.elf')==link['images']['candidate']['ELF_sha256']
    (W/(tag+'-bank.dis')).write_text(subprocess.check_output([str(TC/'arm-none-eabi-objdump'),'-d','--section=.scratch_y',str(p/'candidate.elf')],text=True))
images={tag:ElfImage(p/'candidate.elf')for tag,p in roots.items()}
sections={tag:e.named_sections['.scratch_y']for tag,e in images.items()}
banks={tag:e.bytes_at(sections[tag])for tag,e in images.items()}
base=sections['parent'][3];assert base==sections['candidate'][3]==0x20038000
assert len(banks['parent'])==len(banks['candidate'])==4080
different=[i for i,(a,b)in enumerate(zip(banks['parent'],banks['candidate']))if a!=b]
assert len(different)<=4080
links={tag:json.loads((p/'link-result.json').read_text())for tag,p in roots.items()}
def symbol_name(e,value):
    names=[n for n,a in e.symbols.items()if(a&~1)==(value&~1)and not n.startswith('$')]
    assert len(names)==1,(hex(value),names)
    return names[0]
def target_evidence(name):
    origins=[]
    for tag in ['parent','candidate']:
        link=links[tag]
        command=next(c for c in link['commands']if '-o'in c and Path(c[c.index('-o')+1]).name=='candidate.elf')
        objects=[Path(x).name for x in command if x.endswith('.o')]
        found=[]
        for obj in objects:
            fp=link['outputs'][obj]['fingerprint']
            for row in fp['symbols']:
                if row[0]==name and row[2]>0:
                    section=row[5]
                    found.append(dict(object=obj,symbol=row,section=next(x for x in fp['allocated']if x[0]==section),
                        semantic_relocations=[x for x in fp['relocations']if x[0]==section]))
        assert len(found)==1,(tag,name,found)
        origins.append(found[0])
    assert origins[0]==origins[1],name
    result=dict(symbol=name,unchanged_object_symbol_section_and_semantic_relocations=origins[0])
    if name.endswith('exp_tableE'):
        payload={}
        for tag,e in images.items():
            a=e.symbols[name];size=e.sizes[name]
            s=next(s for s in e.named_sections.values()if s[3]<=a<s[3]+s[5])
            payload[tag]=e.bytes_at(s)[a-s[3]:a-s[3]+size]
        assert payload['parent']==payload['candidate']and len(payload['parent'])==4096
        result['linked_table_bytes']=4096;result['linked_table_SHA256']=hashlib.sha256(payload['parent']).hexdigest()
    return result
veneer_offsets=range(0xfa0,0xff0,16)
veneers={};canonical={}
for tag,e in images.items():
    vs={}
    for at in veneer_offsets:
        body=banks[tag][at:at+12];target=struct.unpack_from('<I',banks[tag],at+12)[0]
        assert body==bytes.fromhex('01b40248844601bc604700bf')
        name=symbol_name(e,target)
        vs[base+at]=dict(offset=at,entry=base+at,body_hex=body.hex(),literal_address=base+at+12,
                       literal_target=target,target_symbol=name)
        canonical.setdefault(name,target_evidence(name))
    veneers[tag]=vs
assert {v['target_symbol']for v in veneers['parent'].values()}=={v['target_symbol']for v in veneers['candidate'].values()}
veneer_mapping=[]
for old in veneers['parent'].values():
    new=next(v for v in veneers['candidate'].values()if v['target_symbol']==old['target_symbol'])
    assert old['body_hex']==new['body_hex']
    veneer_mapping.append(dict(target_symbol=old['target_symbol'],old=old,new=new))
def decode_bl(blob,at):
    first,last=struct.unpack_from('<HH',blob,at)
    assert first&0xf800==0xf000 and last&0xd000==0xd000
    sign=(first>>10)&1;j1=(last>>13)&1;j2=(last>>11)&1
    i1=1^(j1^sign);i2=1^(j2^sign)
    offset=(sign<<24)|(i1<<23)|(i2<<22)|((first&1023)<<12)|((last&2047)<<1)
    if sign:offset-=1<<25
    return base+at+4+offset
calls={}
for tag in ['parent','candidate']:
    found={}
    for line in (W/(tag+'-bank.dis')).read_text().splitlines():
        match=re.match(r'\s*([0-9a-f]+):\s+[0-9a-f]+\s+[0-9a-f]+\s+bl\s+([0-9a-f]+)',line)
        if not match:continue
        pc,destination=[int(x,16)for x in match.groups()]
        if destination not in veneers[tag]:continue
        assert decode_bl(banks[tag],pc-base)==destination
        found[pc]=dict(instruction=banks[tag][pc-base:pc-base+4].hex(),veneer=destination,
            target_symbol=veneers[tag][destination]['target_symbol'],Flash_target=veneers[tag][destination]['literal_target'])
    calls[tag]=found
assert set(calls['parent'])==set(calls['candidate'])
call_mapping=[];covered=set()
for pc,old in calls['parent'].items():
    new=calls['candidate'][pc];assert old['target_symbol']==new['target_symbol']
    call_mapping.append(dict(callsite=pc,old=old,new=new,same_named_ultimate_target=True))
    if old['instruction']!=new['instruction']:covered.update(range(pc-base,pc-base+4))
pointers=[]
for at in [0x804,0xba0]:
    old=struct.unpack_from('<I',banks['parent'],at)[0];new=struct.unpack_from('<I',banks['candidate'],at)[0]
    name=symbol_name(images['parent'],old);assert name==symbol_name(images['candidate'],new)
    canonical.setdefault(name,target_evidence(name))
    pointers.append(dict(offset=at,address=base+at,old_pointer=old,new_pointer=new,target_symbol=name,
                         meaning='relocated Flash table'if at==0x804 else'relocated Flash function'))
    covered.update(range(at,at+4))
for at in veneer_offsets:covered.update(range(at+12,at+16))
assert set(different)<=covered
intervals=[]
for offset in different:
    if intervals and intervals[-1]['offset']+intervals[-1]['bytes']==offset:intervals[-1]['bytes']+=1
    else:intervals.append(dict(offset=offset,address=base+offset,bytes=1))
for row in intervals:
    at=row['offset'];size=row['bytes'];row['old_hex']=banks['parent'][at:at+size].hex();row['new_hex']=banks['candidate'][at:at+size].hex()
    if at<0xfa0:
        row['kind']='Flash pointer'if any(p['offset']<=at<p['offset']+4 for p in pointers)else'Thumb BL displacement'
    else:row['kind']='permuted linker veneer Flash target literal'
other_RAM={}
for name in ['.data','.bss']:
    a=images['parent'].named_sections.get(name);b=images['candidate'].named_sections.get(name)
    assert(a is None)==(b is None)
    if a is None:other_RAM[name]=dict(present=False);continue
    assert (a[1],a[3],a[5])==(b[1],b[3],b[5])
    r=dict(type=a[1],address=a[3],bytes=a[5],same_region_shape=True)
    if a[1]!=8:
        x=images['parent'].bytes_at(a);y=images['candidate'].bytes_at(b);assert x==y
        r['stored_bytes_identical']=True;r['SHA256']=hashlib.sha256(x).hexdigest()
    else:r['initialization']='same ELF NOBITS zero-initialized region; no stored bytes claimed'
    other_RAM[name]=r
result=dict(status='PASS_STATIC_LINKED_BANK_SYMBOLIC_TARGET_MAPPING_NOT_LITERAL_IDENTITY',
    parent_FROZEN_sha256=sha(roots['parent']/'FROZEN.json'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    candidate_link_manifest_sha256=sha(W/'link-result.json'),bank_address=base,bank_bytes=4080,
    bank_bytes_identical=banks['parent']==banks['candidate'],changed_bytes=len(different),
    parent_bank_SHA256=hashlib.sha256(banks['parent']).hexdigest(),candidate_bank_SHA256=hashlib.sha256(banks['candidate']).hexdigest(),
    changed_intervals=intervals,all_changed_bytes_explained=True,veneer_mapping=veneer_mapping,
    all_BL_calls_to_veneer_mapping=call_mapping,relocated_pointer_fields=pointers,
    unchanged_target_origin_evidence=list(canonical.values()),other_RAM_regions=other_RAM,
    no_new_RAM_allocation=True,source_R14_additive_correction_sha256='1b1a7076c2ea90e3413999e1fd0c516b9b990177ae656f6cd8e1c77780e5084c',
    new_ARM_calls=0,new_MPFR_calls=0,new_builds=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'bank-map.json').write_text(json.dumps(result,indent=2)+'\n')
print('bank map PASS byteschanged',len(different),'sameultimatecalls',len(call_mapping),flush=True)
