"""Freeze the selected Horner schedule into the existing GNU-only source."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
root=Path.cwd();work=Path(__file__).resolve().parent
parent=root/'.build/m0-pow-signed-root-v134-20261023'
prototype=root/'.build/m0-pow-horner-inline-v137-20261023'
record=json.loads((prototype/'build.json').read_text());cpp=prototype/'kernels.cpp'
raw=work/'kernels-clang.s';subprocess.run(record['kernel_command']+['-S',str(cpp),'-o',str(raw)],check=True)
lines=[];forced=0
for line in raw.read_text().splitlines(True):
    if line.lstrip().startswith(('.addrsig','.addrsig_sym')) or re.match(r'^\s*\.eabi_attribute\s+26,',line):continue
    match=re.match(r'^\s*(adds|subs)\s+r([0-7]),\s*r([0-7]),\s*#([0-7])\s*(?:@.*)?$',line)
    if match:
        op,rd,rn,imm=match.groups();word=(0x1C00 if op=='adds' else 0x1E00)+(int(imm)<<6)+(int(rn)<<3)+int(rd)
        line='\t.inst.n\t'+hex(word)+' @ '+line.strip()+'\n';forced+=1
    lines.append(line)
assembly=re.sub(r'(?<![A-Za-z0-9_])\.L([A-Za-z0-9_.$]+)',r'.Lpow_horner_\1',''.join(lines))
path=work/'kernels-gnu.S';path.write_text(assembly)
units=json.loads((parent/'build/compile_commands.json').read_text());compiler=Path(shlex.split(next(r['command'] for r in units if r['file'].endswith('/code/native_eabi_m0.cpp')))[0])
obj=work/'kernels-gnu.o';subprocess.run([str(compiler.with_name('arm-none-eabi-gcc')),'-mcpu=cortex-m0plus','-mthumb','-c',str(path),'-o',str(obj)],check=True)
sys.path.insert(0,str(root/'tests'));from check_stm32_vectors import ElfImage
ns=dict(ElfImage=ElfImage,struct=struct)
for node in ast.parse((root/'.build/m0-pow-stable-v87-20261022/link-equivalence.py').read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in ('symbols','object_payload','payload'):
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),ns)
a,b=ns['object_payload'](prototype/'kernels.o'),ns['object_payload'](obj)
a['allocated']={n:v for n,v in a['allocated'].items() if v};b['allocated']={n:v for n,v in b['allocated'].items() if v}
assert a==b,'GNU kernel bytes or named relocations differ'
assert '.rodata.cst16' not in b['allocated']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
(work/'gnu-equivalence.json').write_text(json.dumps(dict(status='PASS_EXACT_GNU_KERNEL_ALLOCATIONS_AND_NAMED_RELOCATIONS',cpp_sha256=sha(cpp),reference_object_sha256=sha(prototype/'kernels.o'),gnu_object_sha256=sha(obj),assembly_sha256=sha(path),forced_imm3_encodings=forced,allocated_sections=list(a['allocated']),whole_image_byte_identity_claimed=False,new_compiler_dependency=False,producer_sha256=sha(__file__)),indent=2)+'\n')
source=work/'source';assert not source.exists();shutil.copytree(parent/'source',source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
(source/'code/native_eabi_m0_pow_root_prefix.inc').write_text('/* Project-owned bounded Horner pow kernels; frozen GNU Thumb schedule.\n * Exact-base products between roots; strict certification retains refinement.\n * No coefficient or global RAM additions. Clang is an optional reference only. */\n'+assembly)
for name in ['M4-isolation.py','generic-isolation.py','compare-cores.py','preserve-scope.py']:
    shutil.copyfile(parent/name,work/name)
shutil.copyfile(parent/'root64.o',work/'root64.o')
validation=(parent/'validate.py').read_text()
validation=validation.replace("assert b['allocated']['.rodata.cst16']==struct.pack('<QiI',1<<63,0,0).hex()", "assert '.rodata.cst16' not in b['allocated']")
validation=validation.replace("assert reference['allocated']['.rodata.cst16']==b['allocated']['.rodata.cst16']", "assert '.rodata.cst16' not in reference['allocated']")
validation=validation.replace('additional_immutable_Root64_identity_bytes=16','additional_immutable_Root64_identity_bytes=0')
(work/'validate.py').write_text(validation)
meta=json.loads((parent/'preparation.json').read_text());meta.update(status='PREPARED_GNU_ONLY_HORNER_SOURCE',parent='V134',arithmetic_instruction_changes=True,new_tables=0,additional_global_RAM=0,additional_identity_literal_bytes=0,new_compiler_dependency=False,original_cpp_sha256=sha(cpp))
(work/'preparation.json').write_text(json.dumps(meta,indent=2)+'\n')
print('PASS: exact GNU bytes/relocations; selected Horner source prepared;16-byte initializer removed.',flush=True)
