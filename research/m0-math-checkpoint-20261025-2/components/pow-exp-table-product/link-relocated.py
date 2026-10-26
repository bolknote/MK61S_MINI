"""Build real pow code in free diagnostic Flash, keeping its public/RAM entries."""
from pathlib import Path
import json, shutil, subprocess, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0] = [str(W), str(ROOT/'tests')]
from elf_support import read_elf, sha
from check_stm32_vectors import ElfImage

tc = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
resident = ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
reference = dict(resident.symbols)
for folder in ('m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024'):
    reference.update(ElfImage(ROOT/'.build'/folder/'candidate.elf').symbols)
compiled = json.loads((W/'compile.json').read_text())
commands, images = [], {}
for label in ('control','candidate'):
    folder = W/('fixture-'+label)
    folder.mkdir(exist_ok=True)
    for src in (W/label).iterdir():
        if src.suffix in {'.S','.inc'}:shutil.copyfile(src,folder/src.name)
    for name,section in [('native_eabi_m0_pow_square.inc','.m0_pow_square_exact_only'),
                         ('native_eabi_m0_pow_rsqrt.inc','.m0_pow_rsqrt_fast_only')]:
        p=folder/name;s=p.read_text()
        assert '.m0_pow_dispatch_extension' in s
        p.write_text(s.replace('.m0_pow_dispatch_extension',section))
    if label=='control':
        s=resident.named_sections['.scratch_y'];address=0x20038ee4+168
        tail=resident.bytes_at(s)[address-s[3]:address-s[3]+14]
        assert len(tail)==14
        p=folder/'native_eabi_m0.S'
        p.write_text(p.read_text()+'\n.section .scratch_y.m0_pow_hot,"ax",%progbits\n.byte '+','.join(str(v) for v in tail)+'\n')
    # The accepted S/R entry is196 bytes in the resident220-byte region.
    # Keep its dead tail so the real dispatcher-to-RAM veneer stays put.
    public_tail_address = 0x101614cc + 196
    text_section = next(s for s in resident.named_sections.values()
                        if s[3]<=public_tail_address<s[3]+s[5])
    public_tail = resident.bytes_at(text_section)[public_tail_address-text_section[3]:public_tail_address-text_section[3]+24]
    assert len(public_tail)==24
    p=folder/'native_eabi_m0.S'
    p.write_text(p.read_text()+'\n.section .m0_pow_dispatch_extension,"ax",%progbits\n.byte '+','.join(str(v) for v in public_tail)+'\n')
    source=folder/'native_eabi_m0.S';full=W/('fixture-'+label+'.o')
    original=next(c for c in compiled['commands'] if c[c.index('-o')+1].endswith('/RP-'+label+'-asm.o'))
    cmd=list(original);cmd[cmd.index('-c')+1]=str(source);cmd[cmd.index('-o')+1]=str(full)
    subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
    asm=full
    sections=['.m0_pow_dispatch_extension','.m0_pow_square_exact_only','.m0_pow_rsqrt_fast_only',
              '.scratch_y.m0_shift_hot','.scratch_y.m0_pow_hot','.m0_pow_exp_table_transition','.ARM.attributes']
    cpp=W/('RP-'+label+'-cpp.o')
    defined={r['name'] for p in (cpp,asm) for r in read_elf(p)[1] if r['section']}
    undefined={r['name'] for p in (cpp,asm) for r in read_elf(p)[1] if not r['section'] and r['name']}
    bindings={}
    for n in sorted(undefined-defined):
        actual=n if n in reference else '__wrap_'+n
        if actual in reference:bindings[n]=reference[actual]
    # Resolve existing non-pow runtime entries to their real frozen resident
    # implementations. Linker assignments preserve the original calls while
    # GC removes these duplicate full-source ASM sections from this overlay.
    asm_sections,asm_symbols=read_elf(asm)
    selected=set(sections)
    for row in asm_symbols:
        index=row['section'];n=row['name']
        if row['bind'] and 0<index<len(asm_sections) and asm_sections[index]['name'] not in selected:
            actual=n if n in reference else '__wrap_'+n
            if actual in reference:bindings[n]=reference[actual]
    cpp_sections,cpp_symbols=read_elf(cpp)
    for row in cpp_symbols:
        index=row['section'];n=row['name']
        if row['bind'] and 0<index<len(cpp_sections) and cpp_sections[index]['name']=='.m0_pow_dispatch_extension':
            assert n in reference,n
            bindings[n]=reference[n]
    script=''.join(n+' = '+hex(a)+';\n' for n,a in sorted(bindings.items()))
    script+='''PHDRS { flash PT_LOAD FLAGS(5); entry PT_LOAD FLAGS(5); square PT_LOAD FLAGS(5); rsqrt PT_LOAD FLAGS(5); ram PT_LOAD FLAGS(5); }
SECTIONS {
 .pow_entry 0x101614cc : { KEEP(ASM_DISPATCH) } :entry
 .pow_square 0x10161e00 : { KEEP(*(.m0_pow_square_exact_only)) } :square
 .pow_rsqrt 0x10162800 : { KEEP(*(.m0_pow_rsqrt_fast_only)) } :rsqrt
 .pow_refine 0x10168000 : { KEEP(CPP_REFINE) } :refine
 .pow_small_y 0x1016ad00 : { KEEP(CPP_SMALL_Y) } :small_y
 .pow_flash 0x101b0000 : { *(.m0*) *(.text*) *(.rodata*) } :flash
 .scratch_y 0x20038000 : {
 KEEP('''+str(cpp)+'''(.scratch_y.m0_pow_hot))
 KEEP('''+str(asm)+'''(.scratch_y.m0_shift_hot))
 KEEP('''+str(asm)+'''(.scratch_y.m0_pow_hot))
 } :ram
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }
}\n'''
    # The CPP dispatch section shares the ASM section's name. Consume it in
    # diagnostic Flash rather than the fixed public entry range.
    script=script.replace('rsqrt PT_LOAD FLAGS(5); ram',
                          'rsqrt PT_LOAD FLAGS(5); refine PT_LOAD FLAGS(5); small_y PT_LOAD FLAGS(5); ram')
    script=script.replace('CPP_REFINE',str(cpp)+'(.m0_pow_refine_extension)')
    script=script.replace('CPP_SMALL_Y',str(cpp)+'(.m0_pow_small_y_cold)')
    script=script.replace('ASM_DISPATCH',str(asm)+'(.m0_pow_dispatch_extension)')
    ld=W/(label+'-relocated.ld');ld.write_text(script)
    cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_fast','-T',str(ld),
         str(cpp),str(asm),'-Map='+str(W/(label+'-relocated.map')),'-o',str(W/(label+'.elf'))]
    subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
    image=ElfImage(W/(label+'.elf'))
    assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
    assert image.symbols['mk61_m0_pow_fast']==reference['mk61_m0_pow_fast']
    assert image.symbols['mk61_m0_pow_exp_product']==0x20038ee5
    assert image.named_sections['.scratch_y'][5]==4080
    assert image.named_sections['.pow_entry'][5]==220
    assert image.named_sections['.pow_small_y'][5]==1720
    assert image.named_sections['.pow_refine'][3]+image.named_sections['.pow_refine'][5]<=0x1016ad00
    assert image.named_sections['.pow_flash'][3]+image.named_sections['.pow_flash'][5]<=0x10200000
    with (W/(label+'.dis')).open('w') as stream:
        subprocess.run([str(tc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=stream,check=True)
    images[label]=dict(ELF_sha256=sha(W/(label+'.elf')),
        sections={n:[s[3],s[5]] for n,s in image.named_sections.items() if s[2]&2 and s[5]},
        symbols={n:a for n,a in image.symbols.items() if 'veneer' in n or 'exp_table_product' in n})
out=dict(status='REAL_WHOLE_SOURCE_POW_LINKED_NOT_NUMERICALLY_QUALIFIED',images=images,
    original_public_entry_and_4080byte_RAM_extent_preserved=True,
    only_existing_pow_code_and_tables_relocated_to_free_diagnostic_Flash=True,
    no_manual_branch_patches_or_arithmetic_mocks=True,commands=commands,hardware_accessed=False)
(W/'link.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
