"""Read-only V164 packet and recursive V163/V161 integrity audit."""
import hashlib,json,subprocess,sys
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
seal=json.loads((work/'FROZEN.json').read_text())
for n,d in seal['files'].items():assert sha(work/n)==d,n
h=json.loads((work/'HANDOFF.json').read_text())
for n,d in h['source_file_hashes'].items():assert sha(work/'source'/n)==d,n
actual={str(p.relative_to(work/'source')) for p in (work/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual==set(h['source_file_hashes']) and len(actual)==654
for n,d in h['references'].items():assert sha(root/n)==d,n
parent=(root/h['upstream_V163']['handoff']['path']).parent
subprocess.run([sys.executable,str(parent/'verify.py')],check=True)
assert len(json.loads((parent/'FROZEN.json').read_text())['files'])==52
for name,p in h['reports'].items():
    report=json.loads((root/p['path']).read_text());status=report.get('status','')
    assert status.startswith(('PASS','PREPARED','OBSERVED','DIAGNOSTIC','INTEGRATION_REQUIRED')),name
elf=root/h['elf']['path'];elf_sha=sha(elf)
for name in ('endpoint-qualification.json','asin-acos-random.json','asin-edges.json','validation.json'):
    r=json.loads((work/name).read_text());assert r['elf_sha256']==elf_sha,name
assert json.loads((work/'matrix-subsets.json').read_text())['owned_elf_sha256']==elf_sha
assert json.loads((work/'result.json').read_text())['elf_sha256']==elf_sha
for name in ('qualify-endpoint.py','qualify-asin-edges.py','compare-cases.py','merge-matrix.py','validate.py','certify.py'):
    outputs={'qualify-endpoint.py':'endpoint-qualification.json','qualify-asin-edges.py':'asin-edges.json',
        'compare-cases.py':'case-comparison.json','merge-matrix.py':'extended-instruction-matrix.json','validate.py':'validation.json','certify.py':'certificate.json'}
    assert json.loads((work/outputs[name]).read_text())['producer_sha256']==sha(work/name),name
assert h['expanded174_groups']==dict(faster=167,equal=2,slower=5,cases=30355)
assert h['correct_reference_subsets']['baseline_V163_distinct_slower_inputs']==508
assert h['correct_reference_subsets']['V164_distinct_slower_inputs']==507
assert h['hardware_accessed'] is False and h['accepted_repaired_Pico_base_integrated'] is False and h['goal_complete'] is False
print('PASS:V164',h['build'],';',len(seal['files']),'sealed files;654 sources;V16352-file and V161 transitive integrity;174 raw167/2/5;508->507 slower inputs;author packet ready,goal open.')
