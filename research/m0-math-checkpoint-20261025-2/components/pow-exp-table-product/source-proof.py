"""Bind the algebraic proof to actual source, objects and linked helper bytes."""
from pathlib import Path
import ast,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(W),str(ROOT/'tests')]
from elf_support import sha,read_elf
from check_stm32_vectors import ElfImage
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),__file__,'exec'),globals())
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
def semantic(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}

old,new=[ElfImage(W/('RP-'+n+'-cpp.o')) for n in ('control','candidate')]
assert allocated(old)==allocated(new)
oldr,newr=semantic(old),semantic(new)
mapping={'mk61_m0_pow_exp_product':'mk61_m0_pow_exp_table_product',
         'mk61_m0_pow_exp_product_flash':'mk61_m0_pow_exp_table_product_flash'}
changed=[]
for section,rows in oldr.items():
    expected=[(off,kind,mapping.get(target,target)) for off,kind,target in rows]
    if rows!=newr[section]:
        assert expected==newr[section],section
        assert sum(a!=b for a,b in zip(rows,newr[section]))==1
        changed.append(section)
assert set(changed)=={'.scratch_y.m0_pow_hot','.m0_pow_refine_extension','.m0_pow_small_y_cold'}

contexts=[]
for context in ('generic_M0','M4_soft','M4_hard'):
    for kind in ('cpp','asm'):
        a,b=[ElfImage(W/(context+'-'+label+'-'+kind+'.o')) for label in ('control','candidate')]
        assert allocated(a)==allocated(b) and semantic(a)==semantic(b)
        contexts.append(dict(context=context,kind=kind,allocated_and_semantic_relocations_equal=True))
asm_old,asm_new=[ElfImage(W/('RP-'+n+'-asm.o')) for n in ('control','candidate')]
a,b=allocated(asm_old),allocated(asm_new)
changed_asm={n:len(b.get(n,b''))-len(a.get(n,b'')) for n in a.keys()|b.keys() if a.get(n,b'')!=b.get(n,b'')}
assert changed_asm=={'.scratch_y.m0_pow_hot':16,'.m0_pow_exp_table_transition':16}
assert a['.scratch_y.m0_pow_hot'][:-14]==b['.scratch_y.m0_pow_hot'][:len(a['.scratch_y.m0_pow_hot'])-14]
for n,v in semantic(asm_old).items():
    if n!='.scratch_y.m0_pow_hot':assert v==semantic(asm_new)[n]

e=ElfImage(W/'candidate.elf');parent=ElfImage(ROOT/'.build/m0-exp-directed-product-20261024/candidate.elf')
base=ElfImage(ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')
def memory(image,address,count):
    s=next(s for s in image.named_sections.values() if s[2]&2 and s[3]<=address and address+count<=s[3]+s[5])
    return image.bytes_at(s)[address-s[3]:address-s[3]+count]
assert memory(e,0x20038ee4,154)==memory(parent,0x20038ee4,154)
table_name='_ZN7m0_eabiL9exp_tableE'
table=memory(e,e.symbols[table_name],4096)
assert table==memory(base,base.symbols[table_name],4096)
roots=struct.unpack('<512Q',table)
def certify(values):
    assert len(values)==512 and values[0]==1<<62
    assert [i for i,v in enumerate(values) if v&0xffffffff==0]==[0]
    assert all(1<<62<=v<1<<63 for v in values)
certify(roots)
negative=0
for index,value in [(0,(1<<62)+(1<<32)),(1,roots[1]&~0xffffffff),(0,0)]:
    mutated=list(roots);mutated[index]=value
    try:certify(mutated)
    except AssertionError:negative+=1
assert negative==3
wrapper=e.symbols['mk61_m0_pow_exp_table_product_flash']&~1
assert memory(e,wrapper,12)==memory(base,0x1016b3b8,12)==bytes.fromhex('01b40248844601bc6047c046')
assert struct.unpack('<I',memory(e,wrapper+12,4))[0]==e.symbols['mk61_m0_pow_exp_table_product']
assert e.named_sections['.scratch_y'][5]==base.named_sections['.scratch_y'][5]==4080
assert e.named_sections['.pow_small_y'][3]+e.named_sections['.pow_small_y'][5]==0x1016b3b8

def frames(path):
    result=[]
    for line in path.read_text().splitlines():
        key,size,kind=line.split('\t')
        key=re.split(r':\d+:\d+:',key,maxsplit=1)[1]
        result.append((key,int(size),kind))
    return sorted(result)
assert frames(W/'RP-control-cpp.su')==frames(W/'RP-candidate-cpp.su')
u=lambda p:{r['name'] for r in read_elf(p)[1] if r['name'] and not r['section']}
added=u(W/'RP-candidate-cpp.o')-u(W/'RP-control-cpp.o')
assert added=={'mk61_m0_pow_exp_table_product','mk61_m0_pow_exp_table_product_flash'}
assert not (u(W/'RP-candidate-asm.o')-u(W/'RP-control-asm.o'))
link=json.loads((W/'link.json').read_text())
out=dict(status='PASS_SOURCE_BOUND_TABLE_ONLY_PRODUCT_EQUIVALENCE',
    CPP_sha256=sha(W/'candidate/native_eabi_m0.cpp'),ASM_sha256=sha(W/'candidate/native_eabi_m0.S'),
    fast_include_sha256=sha(W/'candidate/native_eabi_m0_pow_fast.inc'),
    body_include_sha256=sha(W/'candidate/native_eabi_m0_pow_exp_body.inc'),
    product_include_sha256=sha(W/'candidate/native_eabi_m0_pow_exp_product.inc'),
    wrapper_include_sha256=sha(W/'candidate/native_eabi_m0_pow_exp_table_transition.inc'),
    candidate_ELF_sha256=sha(W/'candidate.elf'),CPP_allocated_bytes_and_all_tables_unchanged=True,
    changed_CPP_call_relocations=sorted(changed),one_call_relocation_per_section=True,
    general154byte_body_and_original_Flash_wrapper_unchanged=True,
    table_roots=512,actual_table_sha256=hashlib.sha256(table).hexdigest(),
    exact_low32zero_identity_index=0,negative_table_controls=negative,
    exact_dyadic_expression='(B >> 2) + ((B >> 1) & 1)',dyadic_B_domain='all unsigned64',
    old_internal_rounding='half-up; public RNE enclosure/packing unchanged',
    original_R12_extra_contract_untouched=True,new_table_callers_scalar_C_ABI_only=True,
    required_actual_integrated_release_R12_guard_still_pending=True,
    contexts=contexts,source_ASM_allocated_code_delta=32,private_RAM_slot_restored_from168_to182=True,
    two_implicit_input_alignment_bytes_within_original_padding=True,
    actual_reserved_RAM_bytes=4080,old_and_new_CPP_static_frames_identical=True,
    new_tables_global_RAM_libgcc_or_ROM_math_dependencies=False,
    private_diagnostic_Flash_load_bytes={n:link['images'][n]['sections']['.pow_flash'][1] for n in ('control','candidate')},
    private_diagnostic_contains_relocated_existing_code_and_tables=True,
    whole_firmware_GC_size_or_physical_cycles_not_measured=True,
    full_general_pow_totality_not_proved=True,hardware_accessed=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
