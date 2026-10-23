"""Verify the sole numeric change and all wrapper/call relocations versus V163."""
import ast,hashlib,json,re,struct,sys
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
utility=root/'.build/m0-pow-stable-v87-20261022/link-equivalence.py'
assert sha(utility)=='424ff1f38dfad6de78ce0cf25aaaf853641626a76390463eae728b4e44995622'
ns=dict(ElfImage=ElfImage,struct=struct,hashlib=hashlib)
for node in ast.parse(utility.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in ('symbols','object_payload','payload','target'):
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),ns)
old,new=[ElfImage(p/'firmware/mk61s-picocalc-pico-h.elf') for p in (parent,work)]
linked_symbols={id(i):ns['symbols'](i) for i in (old,new)}
def resolved(image,address):
    syms=[s for s in linked_symbols[id(image)] if s['info']&15==2 and (s['value']&~1)==address and 'veneer' in s['name']]
    if not syms:return address
    assert all(s['size']==16 for s in syms)
    code=ns['payload'](image,address,16)
    assert code[:10]==bytes.fromhex('01b40248844601bc6047')
    assert code[10:12] in (bytes.fromhex('00bf'),bytes.fromhex('c046'))
    pointer=struct.unpack_from('<I',code,12)[0];assert pointer&1
    return pointer&~1
def equivalent_address(a,b):
    return a==b or any((v&~1)==a and n in new.symbols and (new.symbols[n]&~1)==b for n,v in old.symbols.items())
def branch(code,address,conditional=False):
    i=struct.unpack_from('<H',code)[0]
    if conditional:
        assert i&0xf000==0xd000 and ((i>>8)&15)<14
        d=(i&255)<<1
        if d&256:d-=512
    else:
        assert i&0xf800==0xe000;d=(i&2047)<<1
        if d&2048:d-=4096
    return address+4+d
def section_name(image,index):return next(n for n,s in image.named_sections.items() if s is image.sections[index])
def raw(image,symbol):
    sec=image.sections[symbol['index']];start=(symbol['value']&~1)-sec[3]
    return image.bytes_at(sec)[start:start+symbol['size']]
wrappers={'mk61_m0_asin','mk61_m0_acos','_ZN12compact_math4asinEd','_ZN12compact_math4acosEd'}
changed=[];wrapper_records=[];exact_object=[];exact_linked=[];equivalent_linked=[];objects=[]
for name in ('compact_math.cpp.o','native_eabi_m0.cpp.o','native_eabi_m0_cr.cpp.o','native_eabi_m0.S.o','native_eabi_m0_rp2040.S.o'):
    paths=[next((p/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name)) for p in (parent,work)]
    images=list(map(ElfImage,paths));op=[ns['object_payload'](p) for p in paths]
    assert set(op[0]['allocated'])==set(op[1]['allocated'])
    for label,body in op[0]['allocated'].items():
        if name=='native_eabi_m0.cpp.o' and label=='.m0_asin_extension':continue
        assert body==op[1]['allocated'][label],(name,label)
    for label,rows in op[0]['relocations'].items():
        if name=='native_eabi_m0.cpp.o' and label=='.rel.m0_asin_extension':continue
        assert rows==op[1]['relocations'][label],(name,label)
    syms=[{s['name']:s for s in ns['symbols'](i) if s['info']&15==2 and s['size']} for i in images]
    assert set(syms[0])==set(syms[1])
    for n,a in syms[0].items():
        b=syms[1][n];x,y=[raw(i,s) for i,s in zip(images,(a,b))]
        if n=='asin_checked':
            assert name=='native_eabi_m0.cpp.o' and a['size']==1484 and b['size']==1512 and x!=y
            changed.append(n);continue
        if x!=y:
            assert n in wrappers and len(x)==len(y)==10,(n,len(x),len(y))
            assert x[:4]==y[:4] and x[8:]==y[8:]
            targets=[ns['target'](code[4:8],(s['value']&~1)+4) for code,s in zip((x,y),(a,b))]
            assert all(t==(image.symbols['asin_checked']&~1) for t,image in zip(targets,images))
            wrapper_records.append(dict(name=n,old_object_offset=a['value']&~1,new_object_offset=b['value']&~1,
                target='asin_checked',only_changed_call_offset=4))
        else:exact_object.append(n)
        assert (n in old.symbols)==(n in new.symbols),n
        if n not in old.symbols:continue
        size=old.sizes[n];assert size==new.sizes[n]==a['size'],n
        oa,na=old.symbols[n]&~1,new.symbols[n]&~1
        before,after=[ns['payload'](image,image.symbols[n]&~1,size) for image in (old,new)]
        if before==after:exact_linked.append(n);continue
        normalized=bytearray(after);fixups=[]
        if n in wrappers:
            ot=ns['target'](before[4:8],oa+4);nt=ns['target'](after[4:8],na+4)
            assert ot==old.symbols['asin_checked']&~1 and nt==new.symbols['asin_checked']&~1
            normalized[4:8]=before[4:8];fixups.append(dict(offset=4,type='assembler_resolved_local_BL',target='asin_checked'))
        label=section_name(images[0],a['index']);start=a['value']&~1
        for at,kind,target,value in op[0]['relocations'].get('.rel'+label,[]):
            if not start<=at<start+size:continue
            offset=at-start;width=2 if kind in (102,103) else 4
            if before[offset:offset+width]==after[offset:offset+width]:continue
            if kind==10:
                ot=ns['target'](before[offset:offset+4],oa+offset);nt=ns['target'](after[offset:offset+4],na+offset)
                assert ot is not None and nt is not None
                assert equivalent_address(resolved(old,ot),resolved(new,nt)),(n,offset,target)
            elif kind in (102,103):
                ot=branch(before[offset:offset+2],oa+offset,kind==103);nt=branch(after[offset:offset+2],na+offset,kind==103)
                assert equivalent_address(resolved(old,ot),resolved(new,nt)),(n,offset,target)
            elif kind==2:
                ot,nt=[struct.unpack_from('<I',code,offset)[0] for code in (before,after)]
                assert ot&1==nt&1 and equivalent_address(ot&~1,nt&~1),(n,offset,target)
            else:raise AssertionError((n,offset,kind,'Unexpected linked fixup'))
            normalized[offset:offset+width]=before[offset:offset+width]
            fixups.append(dict(offset=offset,type=kind,target=target))
        assert bytes(normalized)==before,('Unexpected linked numeric byte',n)
        equivalent_linked.append(dict(name=n,old_address=oa,new_address=na,fixups=fixups))
    assert not any(s[1]==8 and s[2]&2 and s[5] for s in images[1].sections)
    objects.append(dict(name=name,old_sha256=sha(paths[0]),new_sha256=sha(paths[1])))
assert changed==['asin_checked'] and {r['name'] for r in wrapper_records}==wrappers
prep=json.loads((work/'preparation.json').read_text());actual={str(p.relative_to(work/'source')):sha(p)
    for p in (work/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual==prep['source_file_hashes'] and len(actual)==654
prior=json.loads((parent/'preparation.json').read_text())['source_file_hashes']
assert set(prior)==set(actual) and [n for n in prior if prior[n]!=actual[n]]==['code/native_eabi_m0_asin.inc']
for n in ('__HeapLimit','__StackBottom','__StackTop','__StackOneBottom','__StackOneTop','__scratch_y_start__','__scratch_y_end__','__end__'):
    assert old.symbols[n]==new.symbols[n],n
assert old.bytes_at(old.named_sections['.scratch_y'])==new.bytes_at(new.named_sections['.scratch_y'])
allocated=[sum(s[5] for s in i.sections if s[2]&2 and s[1]!=8) for i in (old,new)]
manifest=json.loads((work/'firmware/manifest.json').read_text());assert manifest['static_ram_bytes']==198856
assert manifest['flash_bytes']==1560704
assert not re.search(r'libgcc[^\n]*\([^\n)]*\.o\)',(work/'build/mk61s-picocalc-pico-h.elf.map').read_text())
record=dict(status='PASS_ONE_ASIN_BODY_AND_EQUIVALENT_WRAPPERS_AND_LINKED_FIXUPS',objects=objects,
    changed_numeric_body='asin_checked',old_body_bytes=1484,new_body_bytes=1512,
    equivalent_wrapper_symbol_records=wrapper_records,equivalent_physical_wrappers=2,
    unchanged_object_symbol_body_records=len(exact_object),unchanged_object_names=exact_object,
    exact_linked_symbol_body_records=len(exact_linked),exact_linked_names=exact_linked,
    equivalent_linked_symbol_body_records=equivalent_linked,
    old_allocated_bytes=allocated[0],new_allocated_bytes=allocated[1],allocated_bytes_delta=allocated[1]-allocated[0],
    source_file_count=654,only_changed_source='code/native_eabi_m0_asin.inc',new_tables=0,new_global_RAM=0,
    static_RAM_bytes=198856,heap_bytes=30520,scratch_bytes=4080,complete_scratch_bytes_identical=True,
    image_extent_bytes=1560704,libgcc_archive_members=0,physical_layout_unchanged=False,
    elf_sha256=sha(work/'firmware/mk61s-picocalc-pico-h.elf'),producer_sha256=sha(__file__),
    utility=dict(path=str(utility.relative_to(root)),sha256=sha(utility)),
    scope='One source/body changes the proved endpoint radius. Two10-byte wrappers (four alias records) differ only at assembler-resolved BL immediates to the same asin_checked. All other object bytes and every linked difference are checked against V163, including veneer prefix/destination. Symbol counts include aliases; no physical-cycle claim.',
    hardware_accessed=False,production_promoted=False,goal_complete=False)
(work/'validation.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:one numeric body;two equivalent wrappers;',len(exact_linked),'exact linked symbol bodies;',len(equivalent_linked),'equivalent fixup records;allocated delta',allocated[1]-allocated[0],';scratch exact.')
