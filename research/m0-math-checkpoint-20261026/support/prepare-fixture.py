"""Relink pinned V164 objects with unused float entries retained; no rebuild."""
import hashlib,json,shlex,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
PARENT=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BUILD=PARENT/'build'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(PARENT/'HANDOFF.json')=='5ac1145af551dbe631c06a971fc9229659cf92ed4417de5d370e0bae889dc77f'
assert sha(PARENT/'FROZEN.json')=='de4afedeb9d3efb513158f01f3bb81d3602e3b3639c903672354c4bd70738392'
cache=(BUILD/'CMakeCache.txt').read_text().splitlines()
ninja=next(v.split('=',1)[1] for v in cache if v.startswith('CMAKE_MAKE_PROGRAM:'))
commands=subprocess.check_output([ninja,'-C',str(BUILD),'-t','commands','mk61s-picocalc-pico-h.elf'],text=True)
lines=[v for v in commands.splitlines() if ' -o mk61s-picocalc-pico-h.elf ' in v]
assert len(lines)==1
original_tokens=shlex.split(lines[0]);start=next(i for i,v in enumerate(original_tokens) if v.endswith('/arm-none-eabi-g++'))
end=next(i for i in range(start,len(original_tokens)) if original_tokens[i]=='&&')
command=original_tokens[start:end]
assert command.count('-o')==1
objects=[];pins={};replacements={}
for token in command[1:]:
    if token.endswith(('.o','.a')):
        p=Path(token);p=p if p.is_absolute() else BUILD/p
        assert p.is_file(),p
        q=WORK/'objects'/p.relative_to(BUILD) if p.is_relative_to(BUILD) else WORK/'objects/external'/p.name
        q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        assert sha(p)==sha(q)
        replacements[token]=str(q);objects.append(str(q.relative_to(WORK)))
        pins[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)]=sha(p)
assert len(objects)>100
linker=WORK/'linker';linker.mkdir(exist_ok=True)
scripts=[PARENT/'source/ports/picocalc/m0_math_extension.ld',BUILD/'picocalc-memmap.ld',BUILD/'pico_flash_region.ld']
for p in scripts:
    q=linker/p.name;shutil.copy2(p,q);pins[str(p.relative_to(ROOT))]=sha(p)
    replacements[str(p)]=str(q)
q=linker/'m0_math_extension.ld';ld=q.read_text()
marker='    /* Do not move the pre-existing long-call veneer group after adding code. */'
assert ld.count(marker)==1
diagnostic_section='''    /* Diagnostic-only retention. No resident section or code is changed. */
    .qualification_float 0x10180000 : {
        *native_eabi_m0.cpp.o*(.text.__aeabi_f*)
        *native_eabi_m0.cpp.o*(.text.__aeabi_i2f .text.__aeabi_ui2f)
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj23ELj8EE*)
        *native_eabi_m0.S.o*(.text.mk61_m0_sqrtf)
    } > FLASH
'''
q.write_text(ld.replace(marker,diagnostic_section+marker))
for i,token in enumerate(command):
    if token in replacements:command[i]=replacements[token]
    elif token.startswith('-Wl,-Map='):command[i]='-Wl,-Map='+str(WORK/'fixture.map')
    else:
        for old,new in replacements.items():
            if old in token and old.endswith('.ld'):command[i]=token.replace(old,new)
command[command.index('-o')+1]=str(WORK/'fixture.elf')
retained=['__aeabi_'+v for v in ['fadd','fsub','frsub','fmul','fdiv','fcmpeq','fcmplt','fcmple','fcmpge','fcmpgt','fcmpun','f2iz','f2uiz','i2f','ui2f','d2f','f2d']]+['mk61_m0_sqrtf','mk61_m0_fma']
command[1:1]=['-Wl,-L'+str(linker)]+['-Wl,--undefined='+v for v in retained]
pins[str((PARENT/'firmware/mk61s-picocalc-pico-h.elf').relative_to(ROOT))]=sha(PARENT/'firmware/mk61s-picocalc-pico-h.elf')
metadata=dict(status='PREPARED_PINNED_OBJECT_RELINK',retained=retained,objects=objects,
    original_link_command=lines[0],executed_compiler_command=command,external_input_pins=pins,
    compiler_sha256=sha(Path(command[0])),producer_sha256=sha(Path(__file__)),
    diagnostic_linker_section=diagnostic_section,diagnostic_linker_sha256=sha(q),
    resident_changed=False,source_recompiled=False,UF2_BIN_HEX_created=False,hardware_accessed=False)
(WORK/'preparation.json').write_text(json.dumps(metadata,indent=2)+'\n')
with (WORK/'fixture-link.log').open('w') as out:
    result=subprocess.run(command,cwd=WORK,stdout=out,stderr=subprocess.STDOUT)
assert result.returncode==0,(result.returncode,'Inspect fixture-link.log; no production files were written')
nm=Path(command[0]).with_name('arm-none-eabi-nm')
undefined=subprocess.check_output([str(nm),'-u',str(WORK/'fixture.elf')],text=True)
assert not undefined,undefined
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
elf=ElfImage(WORK/'fixture.elf');assert all(v in elf.symbols for v in retained)
metadata.update(status='PASS_RETAINED_ENTRY_FIXTURE_LINK',fixture_sha256=sha(WORK/'fixture.elf'),
                map_sha256=sha(WORK/'fixture.map'),undefined_symbols=[],retained_addresses={v:hex(elf.symbols[v]) for v in retained})
(WORK/'preparation.json').write_text(json.dumps(metadata,indent=2)+'\n')
print('PASS: retained',len(retained),'entries; identical input objects',len(objects),'; diagnostic ELF only; no source recompilation/resident mutation.')
