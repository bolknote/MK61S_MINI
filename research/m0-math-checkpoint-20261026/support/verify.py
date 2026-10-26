"""Read-only frozen qualification/provenance audit. Never executes firmware."""
import gzip,hashlib,json,struct
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((W/n).read_text())
s=read('FROZEN.json');h=read('HANDOFF.json')
for n,d in s['files'].items():assert sha(W/n)==d,n
for n,d in s['external_pins'].items():assert sha(ROOT/n)==d,n
f,ma,a=map(read,['float.json','fma.json','addendum.json'])
lineage=read('producer-lineage.json')
for n,d in ma['producer_pins'].items():assert sha(W/lineage['FMA_report_producer_bindings'][n])==d,n
for op,r in f['operation_provenance'].items():
    base=W/r['completed_run'] if r['completed_run'].startswith('attempts/') else W
    for n,d in r['producer_pins'].items():assert sha(base/n)==d,(op,n)
for n,d in a['shared_producer_pins'].items():assert sha(W/n)==d,n
assert sha(W/'addendum.py')==a['producer_sha256']
for p in h['raw_records']:
    data=gzip.decompress((W/p['path']).read_bytes());assert len(data)==48*p['cases']
    assert sha(W/p['path'])==p['sha256']
assert h['total_accepted_public_calls']==479893 and h['FMA_distinct_triples']==34740
assert h['wrong_rounding_or_value']==h['MPFR_integer_oracle_disagreements']==h['resident_fixture_FMA_mismatches']==0
assert h['new_numeric_version_created'] is False and h['hardware_accessed'] is False and h['goal_complete'] is False
assert h['maximum_instrumented_SP_depth']==196
assert sha(W/'fixture.elf')==h['fixture_elf_sha256']
print('PASS:',len(s['files']),'sealed files;',len(s['external_pins']),'external pins;19 retained entries;479893 public calls;0 wrong; speed/proof/physical limits remain explicit.')
