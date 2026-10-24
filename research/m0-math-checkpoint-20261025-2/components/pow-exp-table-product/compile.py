"""Compile the full intended source and check RP-only object changes."""
from pathlib import Path
import ast, hashlib, json, shlex, struct, subprocess, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
C = ROOT / '.build/m0-exp-directed-product-20261024'
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage
tree = ast.parse((ROOT / '.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'relocs')
exec(compile(ast.Module(body=[fn], type_ignores=[]), __file__, 'exec'), globals())

def allocated(e):
    return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}

def semantic(e):
    return {n:r for n,r in relocs(e).items() if n in allocated(e)}

db = json.loads((P / 'build/compile_commands.json').read_text())
commands, images, contexts = [], {}, []
for context in ('RP', 'generic_M0', 'M4_soft', 'M4_hard'):
    for kind, suffix in [('cpp','cpp'), ('asm','S')]:
        entry = next(r for r in db if r['file'].endswith('/code/native_eabi_m0.' + suffix))
        for label in ('control','candidate'):
            cmd = shlex.split(entry['command'])
            if context != 'RP':
                cmd = [x for x in cmd if x != '-DMK61_M0_RP2040_EABI=1']
            if context.startswith('M4'):
                cmd[cmd.index('-mcpu=cortex-m0plus')] = '-mcpu=cortex-m4'
                cmd[cmd.index('-DMK61_USE_M0_EABI=1')] = '-DMK61_USE_M0_EABI=0'
                if context == 'M4_hard': cmd += ['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
            cmd[cmd.index(entry['file'])] = str(W / label / Path(entry['file']).name)
            output = W / (context + '-' + label + '-' + kind + '.o')
            cmd[cmd.index('-o')+1] = str(output)
            subprocess.run(cmd, cwd=W, check=True)
            commands.append(cmd)
            images[context,kind,label] = ElfImage(output)
        a,b = [images[context,kind,label] for label in ('control','candidate')]
        if context != 'RP':
            assert allocated(a) == allocated(b) and semantic(a) == semantic(b), (context,kind)
            contexts.append(dict(context=context,kind=kind,allocated_bytes_and_semantic_relocations_equal=True))
old,new = [images['RP','cpp',label] for label in ('control','candidate')]
assert allocated(old) == allocated(new)
parent = ElfImage(C / 'RP-candidate.o')
assert allocated(old) == allocated(parent) and semantic(old) == semantic(parent)
oldr,newr = semantic(old),semantic(new)
changed = {n:dict(control=oldr.get(n,[]),candidate=newr.get(n,[])) for n in oldr.keys()|newr.keys() if oldr.get(n,[]) != newr.get(n,[])}
assert changed
a,b = [allocated(images['RP','asm',label]) for label in ('control','candidate')]
asm_changed = {n:[len(a.get(n,b'')),len(b.get(n,b''))] for n in a.keys()|b.keys() if a.get(n,b'') != b.get(n,b'')}
assert set(asm_changed) == {'.scratch_y.m0_pow_hot','.m0_pow_exp_table_transition'}, asm_changed
sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out = dict(status='FULL_INTENDED_OBJECTS_BUILT_NOT_PUBLIC_QUALIFIED', CPP_allocated_bytes_identical=True,
    control_CPP_matches_accepted_C77=True, changed_CPP_semantic_relocations=changed,
    changed_ASM_sections=asm_changed, generic_body154bytes_unchanged=(a['.scratch_y.m0_pow_hot'][:-14] == b['.scratch_y.m0_pow_hot'][:len(a['.scratch_y.m0_pow_hot'])-14]),
    contexts=contexts, commands=commands,
    outputs={p.name:sha(p) for p in sorted(W.glob('*-*-*.o'))}, hardware_accessed=False)
assert out['generic_body154bytes_unchanged']
(W / 'compile.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('commands','outputs','changed_CPP_semantic_relocations')},indent=2))
print('Changed CPP relocation sections:', ', '.join(changed))
