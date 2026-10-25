"""Compose compatible CPP/core ASM sources, without linking diagnostic overlays."""
from pathlib import Path
import difflib,hashlib,importlib.util,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
T=ROOT/'.build/m0-pow-exp-table-product-20261025';N=ROOT/'.build/m0-exp-near-one-20261024'
assert not(W/'composition.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=W/'source/code';source.mkdir(parents=True,exist_ok=True)
provenance={}
for p in sorted((T/'candidate').iterdir()):
 if p.is_file():
  dest=source/p.name;dest.write_bytes(p.read_bytes());provenance[p.name]=dict(source=str(p.relative_to(ROOT)),sha256=sha(p))
a=(T/'candidate/native_eabi_m0.cpp').read_text().splitlines();b=(N/'candidate/native_eabi_m0.cpp').read_text().splitlines()
changes=[(tag,i,j,k,l)for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()if tag!='equal']
assert len(changes)==2 and all(tag=='insert'for tag,i,j,k,l in changes)
assert b[changes[0][3]].startswith('// Private prototype: |x| in[2^-32,2^-11).')
assert b[changes[1][3]:changes[1][4]]==['  } else if(e<-11) {','    return real(exp_small_rne(a));']
dest=source/'native_eabi_m0.cpp';dest.write_bytes((N/'candidate/native_eabi_m0.cpp').read_bytes())
provenance[dest.name]=dict(source=str((N/'candidate/native_eabi_m0.cpp').relative_to(ROOT)),sha256=sha(dest),compatible_with_table_CPP_except_two_near_one_exp_insertions=True)
(W/'near-one-composition.patch').write_text(''.join(difflib.unified_diff((T/'candidate/native_eabi_m0.cpp').read_text().splitlines(True),dest.read_text().splitlines(True),fromfile='table-product/native_eabi_m0.cpp',tofile='unified/native_eabi_m0.cpp')))
spec=importlib.util.spec_from_file_location('source_fingerprint',ROOT/'research/m0-math-checkpoint-20261025-4/verify.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
recorded=json.loads((T/'compile.json').read_bytes())['commands'];commands=[];outputs={}
for old in recorded:
 target=Path(old[old.index('-o')+1]).name
 if '-candidate-'not in target:continue
 filename=Path(old[old.index('-c')+1]).name;out=W/target.replace('-candidate-','-merged-')
 c=list(old);c[c.index('-c')+1]=str(source/filename);c[c.index('-o')+1]=str(out)
 subprocess.run(c,cwd=W,check=True);commands.append(c)
 parent=(N/target.replace('-cpp.o','.o'))if filename.endswith('.cpp')else T/target
 assert parent.exists(),parent
 assert module.image_fingerprint(out.read_bytes())==module.image_fingerprint(parent.read_bytes()),target
 outputs[out.name]=dict(sha256=sha(out),qualified_comparison=str(parent.relative_to(ROOT)),allocated_bytes_symbols_semantic_relocations_equal=True)
assert len(outputs)==8
result=dict(status='CPP_AND_CORE_ASM_SOURCE_COMPOSED_AND_COMPILED_NOT_LINKED',source_files=provenance,source_CPP_composition_only_two_exp_insertions=True,
 outputs=outputs,commands=commands,RP_CPP_allocated_code_matches_near_one=True,RP_core_ASM_allocated_code_matches_table_product=True,
 default_M0_M4_selected_objects_equal=True,complete_RP_native_root_square_boundary_reciprocal_sources_not_yet_composed=True,
 final_ELF_linked=False,actual_linked_R12_guard_passed=False,loader_layout_guard_passed=False,old168B_overlay_must_not_be_used=True,
 actual_ARM_or_MPFR_calls=0,canonical_M4_Git_device_USB_Flash_changed=False,integration_GO=False,hardware_GO=False,release_GO=False,goal_complete=False)
(W/'composition.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ['source_files','commands','outputs']},indent=2))
