"""Portable read-only archive consumer. Does not execute historical code or device I/O."""
from pathlib import Path, PurePosixPath
from collections import Counter
import argparse, contextlib, gzip, hashlib, io, json, re, statistics, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--records', action='store_true', help='recount saved finite ARM audit and physical samples')
parser.add_argument('--report', type=Path)
parser.add_argument('--extract-packet', nargs=2, metavar=('LABEL','NEW_DIRECTORY'))
args = parser.parse_args()
def digest_stream(f):
 h, n = hashlib.sha256(), 0
 for b in iter(lambda:f.read(1<<20), b''): h.update(b); n += len(b)
 return h.hexdigest(), n
def sha(p):
 with p.open('rb') as f: return digest_stream(f)[0]
reserved = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
def checked(name):
 p = PurePosixPath(name)
 assert p.parts and not p.is_absolute() and all(s not in ('.','..') for s in p.parts), name
 for s in p.parts:
  assert not reserved.match(s) and s[-1] not in '. ' and not any(c in s for c in '<>:"\\|?*'), name
 result = W.joinpath(*p.parts)
 assert not result.is_symlink(), name
 return result
index = json.loads((W/'checkpoint.json').read_text())
names = set(index['files']) | {'checkpoint.json'}
assert len(names) == len({s.casefold() for s in names})
assert names == {str(p.relative_to(W)) for p in W.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
for name, pin in index['files'].items(): assert sha(checked(name)) == pin, name
provenance = json.loads((W/'provenance.json').read_text())
entries = provenance['archived_files']
by_source = {r['source']:r for r in entries}
omitted = {r['source']:r for r in provenance['omitted_binary_files']}
assert len(by_source) == len(entries) and not set(by_source) & set(omitted)
@contextlib.contextmanager
def stream(row):
 if row['encoding'] == 'identity':
  with checked(row['path']).open('rb') as f: yield f
 else:
  assert row['encoding'] == 'gzip'
  with gzip.open(checked(row['path']), 'rb') as f: yield f
verified = {}
for row in entries:
 key = row['uncompressed_sha256']
 identity = (row['uncompressed_bytes'],row['path'],row['encoding'],row['sha256'],row['stored_bytes'])
 if key not in verified:
  assert (sha(checked(row['path'])),checked(row['path']).stat().st_size) == (row['sha256'],row['stored_bytes'])
  with stream(row) as f: assert digest_stream(f) == (key,row['uncompressed_bytes']), row['source']
  verified[key] = identity
 assert verified[key] == identity
def source_json(source):
 with stream(by_source[source]) as f: return json.load(f)
@contextlib.contextmanager
def source_lines(source):
 with stream(by_source[source]) as f:
  compressed = gzip.GzipFile(fileobj=f,mode='rb') if source.endswith('.gz') else f
  with io.TextIOWrapper(compressed,encoding='utf-8') as text: yield text
manifests = json.loads((W/'manifests.json').read_text())
pins = 0
for source, info in manifests.items():
 assert by_source[source]['uncompressed_sha256'] == info['sha256']
 manifest = source_json(source)
 assert manifest.get('all_producers_terminal',True) and len(manifest['files']) == info['pins']
 parent = str(PurePosixPath(source).parent)
 for name, pin in manifest['files'].items():
  target = parent+'/'+name
  row = by_source.get(target)
  actual = (row['uncompressed_bytes'],row['uncompressed_sha256']) if row else (omitted[target]['bytes'],omitted[target]['sha256'])
  assert actual == (pin['bytes'],pin['sha256']), target
  pins += 1
S = '.build/m0-math-pow-fullword-powerzero-r63-20261028/'
H = '.build/m0-math-r62-r63-ram-hil-20261028/'
V = '.build/m0-math-r62-r63-hil-root-review-20261028-001/'
author = source_json(S+'AUTHOR-RESULT.json')
audit = source_json(S+'joined-audit.json')
root = source_json('.build/m0-math-r63-root-review-20261028-001/ROOT-ACCEPTANCE.json')
assert root['selected_private_baseline'] == 'R63' and not author['canonical_runtime_integrated']
assert root['source_manifest']['sha256'] == by_source[S+'FROZEN.json']['uncompressed_sha256']
assert root['candidate']['sha256'] == omitted[S+'candidate.elf']['sha256'] == author['candidate_ELF_sha256']
assert author['expanded_corpus'] == audit['expanded_corpus']
assert author['expanded_corpus']['R63_losing_pairs'] == 1400 and author['expanded_corpus']['new_losing_states'] == 0
assert author['remaining_expanded_by_kind'] == dict(zero_or_infinity=196,normal_result=483,inverse_root=721)
assert author['all23_other_runtime_objects_byteexact'] and author['default_M0_M4_disabled_controls_byteexact']
assert not index['canonical_runtime_integrated'] and not index['M4_changed'] and not index['goal_complete']
assert index['physical']['remaining_pairs'] == 36
first = source_json(V+'FIRST-PHYSICAL-ROUND-FINAL.json')
assert first['status'] == 'ROOT_JOINT_R62_R63_FIRST_PHYSICAL_SMOKE_AND_EXACT249_RETURN_CLOSED'
hold = source_json(V+'joint-01-RETURN-HOLD-CLOSED.json')
assert 'HOLD' in hold['status']
latest = source_json(H+'current-state-before-calc-clear-001/current-state.json')
assert latest['IP'] == 158, latest
assert not index['physical_return']['volatile_reinit_executed']
report = dict(status='PASS_PORTABLE_R63_CHECKPOINT', archived_files=len(entries),unique_payloads=len(verified),omitted_binaries=len(omitted), verified_manifests=len(manifests),verified_manifest_pins=pins, records_recounted=False, new_device_ARM_MPFR_SDK_calls=0, production_runtime_changed=False, goal_complete=False)
if args.records:
 pairs, previous_losses, current_losses, rows, new_losses = set(),set(),set(),0,0
 with source_lines(S+'joined-pow-audit-records.jsonl.gz') as f:
  for line in f:
   r=json.loads(line); k=(r['x'],r['y']); pairs.add(k); rows+=1
   if r['previously_losing']: previous_losses.add(k)
   if r['currently_losing']: current_losses.add(k)
   new_losses += bool(r['currently_losing'] and not r['previously_losing'])
 assert (len(pairs),rows,len(current_losses),new_losses) == (152937,324446,1400,0)
 assert len(previous_losses) == 1692 and len(previous_losses-current_losses) == 292
 all_pairs, all_states, slow_pairs, targets = set(),set(),set(),set()
 our_calls=all_calls=wrong_reference_calls=queries=0
 speedups=[]; max_stack=0; classes=Counter()
 for batch,expected_slow,expected_targets in [('joint-math-cdc-001',5,14),('joint-01-math-cdc-001',0,12)]:
  batch_slow,batch_targets=set(),set()
  nonce=None
  with source_lines(H+batch+'/records.jsonl') as f:
   for line in f:
    r=json.loads(line)
    if r['kind']=='identity':
     assert nonce is None; nonce=r['value']['nonce']; assert r['value']['math_ok']==1
     continue
    if r['kind'] not in ('calibration','math_case'): continue
    queries+=1; samples=r['samples']; all_calls+=len(samples)
    assert len(samples)==(40 if r['kind']=='math_case' else 10)
    max_stack=max(max_stack,max(s['stack_used'] for s in samples))
    assert all(s['nonce']==nonce and s['id']==r['request_id'] for s in samples)
    if r['kind']=='calibration': continue
    case=r['source_case']; k=(case['x'],case['y']); state=k+(case['SIO'],)
    assert state not in all_states; all_states.add(state); all_pairs.add(k)
    gold=int(case['expected'],16); by_lib={i:[s for s in samples if s['library']==i] for i in range(4)}
    for lib,ss in by_lib.items():
     assert sorted(s['round'] for s in ss)==[0,1,2,3,4,5,6,7,128,129]
     if lib==0:
      assert all(s['bits']==gold and s['flags']==0 for s in ss), state
      our_calls+=len(ss)
     else: wrong_reference_calls+=sum(s['bits']!=gold or s['flags']!=0 for s in ss)
    costs={i:statistics.median(s['cycles'] for s in ss if s['round']<8) for i,ss in by_lib.items()}
    assert all(len({s['cycles'] for s in ss if s['round']<8})==1 for ss in by_lib.values())
    refs=[i for i in (1,2,3) if all(s['bits']==gold and s['flags']==0 for s in by_lib[i])]
    cls='no_correct_reference' if not refs else 'slower' if costs[0]>min(costs[i] for i in refs) else 'no_slower'
    classes[cls]+=1
    if cls=='slower': slow_pairs.add(k);batch_slow.add(k)
    if any(o in ('R62_all_original_targets','R63_all_original_targets') for o in case['origins']):
     assert refs and all(costs[0]<costs[i] for i in refs)
     batch_targets.add(k);targets.add(k);speedups.append(min(costs[i] for i in refs)/costs[0])
  assert len(batch_slow)==expected_slow and len(batch_targets)==expected_targets
 assert (len(all_pairs),len(all_states),our_calls,all_calls,queries,len(slow_pairs),len(targets),wrong_reference_calls,max_stack)==(48,144,1440,5880,156,5,26,1740,2276)
 assert min(speedups)==index['physical']['target_speedup_range'][0] and max(speedups)==index['physical']['target_speedup_range'][1]
 report.update(records_recounted=True, finite_union_pairs=len(pairs),finite_union_states=rows,known_pow_losing_pairs=len(current_losses),new_losing_states=new_losses,physical_pairs=len(all_pairs),physical_states=len(all_states),our_math_calls=our_calls,all_physical_target_calls=all_calls,wrong_reference_calls_retained=wrong_reference_calls,physical_slow_control_pairs=len(slow_pairs),measured_repaired_pairs=len(targets),target_speedup_range=[min(speedups),max(speedups)],physical_state_classes=dict(classes),observed_stack_bytes=max_stack,universal_stack_bound=False)
if args.extract_packet:
 label,dest_name=args.extract_packet
 packets=json.loads((W/'packets.json').read_text()); prefix=packets[label]['directory']+'/'
 dest=Path(dest_name).resolve(); assert not dest.exists(), 'Extraction requires a new directory'
 dest.mkdir(parents=True)
 for row in entries:
  if row['packet']!=label: continue
  assert row['source'].startswith(prefix)
  name=PurePosixPath(row['source'][len(prefix):]); assert not name.is_absolute() and '..' not in name.parts
  target=dest.joinpath(*name.parts);target.parent.mkdir(parents=True,exist_ok=True)
  with stream(row) as src,target.open('xb') as dst:
   for b in iter(lambda:src.read(1<<20),b''): dst.write(b)
 report['extracted_text_packet']=label
if args.report: args.report.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
