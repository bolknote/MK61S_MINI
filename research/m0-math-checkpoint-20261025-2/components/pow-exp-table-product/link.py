"""Link whole CPP sections at original addresses, with the actual RAM objects."""
from pathlib import Path
import json, subprocess, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0] = [str(W),str(ROOT/'tests')]
from elf_support import read_elf, section_bases, sha
from check_stm32_vectors import ElfImage

tc = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
resident = P / 'firmware/mk61s-picocalc-pico-h.elf'
reference = ElfImage(resident)
for folder in ('m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024'):
    reference.symbols.update(ElfImage(ROOT/'.build'/folder/'candidate.elf').symbols)
compiled = json.loads((W/'compile.json').read_text())
changed = set(compiled['changed_CPP_semantic_relocations'])
assert changed == {'.m0_pow_refine_extension','.scratch_y.m0_pow_hot','.m0_pow_small_y_cold'}
sections,bases,witnesses = section_bases(W/'RP-control-cpp.o', resident)
mapped = {s['name']:next(iter(bases[i])) for i,s in enumerate(sections)
          if s['flags']&2 and s['size'] and len(bases.get(i,set()))==1}
mapped['.m0_pow_dispatch_ordinary'] = 0x10162200
commands, results = [], {}
for label in ('control','candidate'):
    cpp,asm = W/('RP-'+label+'-cpp.o'),W/('RP-'+label+'-asm.o')
    if label == 'control':
        # The accepted private parent overwrites168 bytes of the resident's
        # original182-byte slot. Preserve the remaining14 dead resident bytes
        # inside this input section, before GNU ld places its real RAM stubs.
        # This does not add instructions on any callable parent path.
        section = reference.named_sections['.scratch_y']
        address = 0x20038ee4 + 168
        tail = reference.bytes_at(section)[address-section[3]:address-section[3]+14]
        assert len(tail) == 14
        fixture = W/'RAM-control-fixture.S'
        fixture.write_text('#include "control/native_eabi_m0.S"\n'
            '.section .scratch_y.m0_pow_hot,"ax",%progbits\n.byte '+','.join(str(v) for v in tail)+'\n')
        command = next(c for c in compiled['commands'] if c[c.index('-o')+1].endswith('/RP-control-asm.o'))
        cmd = list(command)
        cmd[cmd.index('-c')+1] = str(fixture)
        asm = W/'RAM-control-fixture.o'
        cmd[cmd.index('-o')+1] = str(asm)
        subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
    ram = W/('RAM-'+label+'.o')
    cmd = [str(tc/'arm-none-eabi-objcopy'),
           '--only-section=.scratch_y.m0_shift_hot','--only-section=.scratch_y.m0_pow_hot',
           '--only-section=.m0_pow_exp_table_transition','--only-section=.ARM.attributes',str(asm),str(ram)]
    subprocess.run(cmd,check=True);commands.append(cmd)
    defined = {r['name'] for p in (cpp,ram) for r in read_elf(p)[1] if r['section']}
    undefined = {r['name'] for p in (cpp,ram) for r in read_elf(p)[1] if not r['section'] and r['name']}
    names = sorted(undefined-defined)
    bindings = {}
    for name in names:
        # The frozen SDK executable exports wrapped EABI/memory names.
        actual = name if name in reference.symbols else '__wrap_' + name
        if actual in reference.symbols:bindings[name] = reference.symbols[actual]
    # Unused translation-unit dependencies are discarded by real section GC.
    # Any unresolved dependency of a retained section is a hard linker error.
    script = ''.join(n+' = '+hex(a)+';\n' for n,a in sorted(bindings.items()))
    flash = [(n,a) for n,a in mapped.items() if not n.startswith('.scratch_y')]
    flash.sort(key=lambda pair:pair[1])
    phdrs = ['s'+str(i)+' PT_LOAD FLAGS(5);' for i in range(len(flash))]
    phdrs += ['ram PT_LOAD FLAGS(5);','transition PT_LOAD FLAGS(5);']
    script += 'PHDRS { '+' '.join(phdrs)+' }\nSECTIONS {\n'
    for i,(name,address) in enumerate(flash):
        item = str(cpp)+'('+name+')'
        if name in changed:item='KEEP('+item+')'
        script += ' '+name+' '+hex(address)+' : { '+item+' } :s'+str(i)+'\n'
    script += ''' .scratch_y 0x20038000 : {
 KEEP('''+str(cpp)+'''(.scratch_y.m0_pow_hot))
 KEEP('''+str(ram)+'''(.scratch_y.m0_shift_hot))
 KEEP('''+str(ram)+'''(.scratch_y.m0_pow_hot))
 } :ram
 .table_transition 0x101b0000 : { KEEP(*(.m0_pow_exp_table_transition)) } :transition
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }
}\n'''
    path = W/(label+'.ld');path.write_text(script)
    cmd = [str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_pow_exp_product',
           '-T',str(path),str(cpp),str(ram),'-Map='+str(W/(label+'.map')),'-o',str(W/(label+'.elf'))]
    subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
    im = ElfImage(W/(label+'.elf'))
    assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
    with (W/(label+'.dis')).open('w') as stream:
        subprocess.run([str(tc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=stream,check=True)
    results[label] = dict(ELF_sha256=sha(W/(label+'.elf')),
        sections={n:[s[3],s[5]] for n,s in im.named_sections.items() if s[2]&2 and s[5]},
        symbols={n:a for n,a in im.symbols.items() if 'veneer' in n or 'exp_table_product' in n})
(W/'link.json').write_text(json.dumps(dict(status='LINKED_NOT_QUALIFIED',images=results,
    source_section_bases=mapped,base_witnesses={sections[i]['name']:v for i,v in witnesses.items()},
    commands=commands,hardware_accessed=False),indent=2)+'\n')
print(json.dumps(results,indent=2))
