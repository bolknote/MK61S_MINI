"""Prove old linked sections exact and each retained object body relocated only."""
import ast,hashlib,json,shutil,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=Path(__file__).resolve().parent
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
utility=ROOT/'.build/m0-pow-stable-v87-20261022/link-equivalence.py'
assert sha(utility)=='424ff1f38dfad6de78ce0cf25aaaf853641626a76390463eae728b4e44995622'
ns=dict(ElfImage=ElfImage,struct=struct,hashlib=hashlib)
for n in ast.parse(utility.read_text()).body:
    if isinstance(n,ast.FunctionDef) and n.name in ['symbols','payload','target']:
        exec(compile(ast.fix_missing_locations(ast.Module(body=[n],type_ignores=[])),n.name,'exec'),ns)
old=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');new=ElfImage(W/'fixture.elf')
unchanged=[];footer=[]
for name,s in old.named_sections.items():
    if not s[2]&2:continue
    t=new.named_sections[name];assert s[3]==t[3] and s[5]==t[5],name
    if s[1]!=8 and old.bytes_at(s)!=new.bytes_at(t):
        assert name=='.mk61_fw_footer',name
        footer.append(dict(section=name,reason='Resident has sealed footer; diagnostic relink retains unsealed placeholder from original object. Never flashed.',old_sha256=hashlib.sha256(old.bytes_at(s)).hexdigest(),fixture_sha256=hashlib.sha256(new.bytes_at(t)).hexdigest()))
    else:unchanged.append(dict(section=name,address=hex(s[3]),bytes=s[5],nobits=s[1]==8,sha256=None if s[1]==8 else hashlib.sha256(old.bytes_at(s)).hexdigest()))
q=new.named_sections['.qualification_float'];start,end=q[3],q[3]+q[5]
def resolved(address):
    funcs=[s for s in ns['symbols'](new) if s['info']&15==2 and s['value']&~1==address and 'veneer' in s['name']]
    if not funcs:return address,None
    assert all(s['size']==16 for s in funcs)
    b=ns['payload'](new,address,16)
    assert b[:10]==bytes.fromhex('01b40248844601bc6047') and b[10:12] in (bytes.fromhex('00bf'),bytes.fromhex('c046'))
    target=struct.unpack_from('<I',b,12)[0];assert target&1
    return target&~1,dict(address=hex(address),sha256=hashlib.sha256(b).hexdigest(),target=hex(target))
body_records=[];all_covered=set()
for name in ['native_eabi_m0.cpp.o','native_eabi_m0.S.o']:
    path=next((W/'objects').rglob(name));obj=ElfImage(path);syms=ns['symbols'](obj)
    indices={s['index'] for s in syms if s['info']&15==2 and s['name'] in new.symbols and start<=new.symbols[s['name']]&~1<end}
    for index in sorted(indices):
        section=obj.sections[index];source=obj.bytes_at(section)
        funcs=[s for s in syms if s['index']==index and s['info']&15==2 and s['name'] in new.symbols]
        bases={ (new.symbols[s['name']]&~1)-(s['value']&~1) for s in funcs};assert len(bases)==1
        base=bases.pop();actual=bytearray(ns['payload'](new,base,len(source)));relocations=[]
        for rel in obj.sections:
            if rel[1]!=9 or rel[7]!=index:continue
            for at,info in struct.iter_unpack('<II',obj.bytes_at(rel)):
                assert info&255==10,(name,'Unexpected relocation',info&255)
                symbol=syms[info>>8]['name'];target,veneer=resolved(ns['target'](actual[at:at+4],base+at))
                assert target==new.symbols[symbol]&~1,(symbol,hex(target),hex(new.symbols[symbol]))
                relocations.append(dict(offset=at,type='R_ARM_THM_CALL',symbol=symbol,target=hex(target),veneer=veneer))
                actual[at:at+4]=source[at:at+4]
        assert bytes(actual)==source,(name,funcs[0]['name'],'Instruction/data bytes changed outside audited relocations')
        all_covered.update(range(base,base+len(source)))
        body_records.append(dict(object=str(path.relative_to(W)),object_sha256=sha(path),section_index=index,functions=[s['name'] for s in funcs],linked_address=hex(base),bytes=len(source),object_body_sha256=hashlib.sha256(source).hexdigest(),linked_body_sha256=hashlib.sha256(ns['payload'](new,base,len(source))).hexdigest(),relocations=relocations))
support=W/'support';support.mkdir(exist_ok=True)
support_pins={}
for n in ['native_eabi_m0_arm_self_test.py','check_stm32_vectors.py','m0_mpfr_oracle.py']:
    shutil.copy2(ROOT/'tests'/n,support/n);support_pins['support/'+n]=sha(support/n)
source_pins={str(p.relative_to(P/'source')):sha(p) for p in (P/'source/code').glob('native_eabi_m0*') if p.is_file()}
commands=json.loads((P/'build/compile_commands.json').read_text())
selected=[v for v in commands if Path(v['file']).name in ['native_eabi_m0.cpp','native_eabi_m0.S']]
assert len(selected)==2
report=dict(status='PASS_EXACT_OBJECT_AND_LINKED_BODY_AUDIT',fixture_sha256=sha(W/'fixture.elf'),resident_sha256=sha(P/'firmware/mk61s-picocalc-pico-h.elf'),
    unchanged_resident_allocated_sections=unchanged,diagnostic_footer_exception=footer,
    added_section=dict(address=hex(start),bytes=q[5],covered_object_body_bytes=len(all_covered),remaining_alignment_and_veneers=q[5]-len(all_covered)),
    body_records=body_records,source_pins=source_pins,original_compile_commands=selected,support_pins=support_pins,
    producer_sha256=sha(Path(__file__)),utility_sha256=sha(utility),source_recompiled=False,resident_changed=False,hardware_accessed=False,
    scope='Exact original objects and original resident allocated sections; only absent float bodies retained in diagnostic section. All new body relocations checked; this is not a firmware release image.')
(W/'body-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(unchanged),'old allocated sections identical; unsealed diagnostic footer exception;',len(body_records),'retained body sections; every BL target/veneer checked;',q[5],'new diagnostic bytes.')
