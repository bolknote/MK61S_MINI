"""Preserve the complete source scope and reproduce the five-file patch."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path.cwd();work=Path(__file__).resolve().parent
baseline=root/'.build/m0-pow-root-prefix-v122-20261023'
old=root/'.build/m0-pow-final-parent-v110-20261023'
platform=root/'.build/finish-m0-review-20261022/production-v3-flash-final'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
files=lambda tree:{str(p.relative_to(tree)):p for p in tree.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
ns=dict(hashlib=hashlib)
node=next(n for n in ast.parse((root/'.build/m0-memory-compose-v79-20261021/prepare.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='fingerprint')
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'fingerprint','exec'),ns)
manifest=json.loads((work/'firmware/manifest.json').read_text());current=files(work/'source')
assert ns['fingerprint'](work/'source')==manifest['source_sha256']
scopes={}
for label,tree in [('V122',baseline/'source'),('V110',old/'source'),('final_2EABB2A2',platform/'source')]:
    before=files(tree);assert not before.keys()-current.keys()
    added=sorted(current.keys()-before.keys());changed=sorted(n for n in before if before[n].read_bytes()!=current[n].read_bytes())
    scopes[label]=dict(source_sha256=ns['fingerprint'](tree),modified=changed,added=added,
        unchanged_regular_files=len(before)-len(changed),hashes={n:dict(before=sha(before[n]) if n in before else None,after=sha(current[n])) for n in changed+added})
assert len(scopes['V122']['modified'])==5 and not scopes['V122']['added']
assert len(scopes['final_2EABB2A2']['modified'])==15 and len(scopes['final_2EABB2A2']['added'])==7
historical=json.loads((root/'research/m0-pow-small-cross-20261023/source-scope.json').read_text())['unchanged_non_math']
overlay=set(historical['excluded_overlay_paths'])|set(scopes['V110']['added'])
platform_files=files(platform/'source');non_math=sorted(platform_files.keys()-overlay)
assert len(non_math)==568 and all(platform_files[n].read_bytes()==current[n].read_bytes() for n in non_math)
patch=''
for name in scopes['V122']['modified']:
    patch+=''.join(difflib.unified_diff((baseline/'source'/name).read_text().splitlines(True),current[name].read_text().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
while '\n \n' in patch:patch=patch.replace('\n \n','\n\n')
path=work/'hybrid-from-V122.patch';path.write_text(patch)
stage=Path(tempfile.mkdtemp(prefix='source-patch-reproduction-',dir=work))/'source'
shutil.copytree(baseline/'source',stage,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
command=['git','apply','--whitespace=nowarn','--directory='+str(stage.relative_to(root)),str(path)]
subprocess.run(command[:2]+['--check']+command[2:],cwd=root,check=True);subprocess.run(command,cwd=root,check=True)
reproduced=files(stage)
assert reproduced.keys()==current.keys() and all(reproduced[n].read_bytes()==p.read_bytes() for n,p in current.items())
assert ns['fingerprint'](stage)==manifest['source_sha256']
result=dict(status='PASS_COMPLETE_SOURCE_AND_PATCH_REPRODUCTION',current_source_sha256=manifest['source_sha256'],regular_source_files=len(current),bases=scopes,
    patch=dict(path=str(path.relative_to(root)),sha256=sha(path)),patch_reproduction_all_source_bytes_identical=True,
    unchanged_non_math=dict(count=568,excluded_overlay_paths=sorted(overlay),unchanged_paths=non_math),producer_sha256=sha(__file__))
(work/'source-scope.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS: five-file patch reproduces all',len(current),'source files; full platform15modified+7added;568 other files preserved.')
