"""Portable read-only archive consumer; never imports or executes producers."""
from pathlib import Path, PurePosixPath
from collections import Counter
import argparse, contextlib, gzip, hashlib, json, re, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--records', action='store_true')
parser.add_argument('--report', type=Path)
args = parser.parse_args()
def digest_stream(f):
    h, n = hashlib.sha256(), 0
    for b in iter(lambda: f.read(1 << 20), b''):
        h.update(b); n += len(b)
    return h.hexdigest(), n
def digest(p):
    with p.open('rb') as f:
        return digest_stream(f)[0]
reserved = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
def path(name):
    p = PurePosixPath(name)
    assert p.parts and not p.is_absolute() and all(q not in ('.', '..') for q in p.parts), name
    for q in p.parts:
        assert not reserved.match(q) and q[-1] not in '. ' and not any(c in q for c in '<>:"\\|?*'), name
    result = W.joinpath(*p.parts)
    assert not result.is_symlink(), name
    return result
index = json.loads((W / 'checkpoint.json').read_text())
names = set(index['files']) | {'checkpoint.json'}
assert len(names) == len({s.casefold() for s in names})
assert names == {str(p.relative_to(W)) for p in W.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
for name, pin in index['files'].items():
    assert digest(path(name)) == pin, name
provenance = json.loads((W / 'provenance.json').read_text())
entries = provenance['archived_files']
by_source = {r['source']: r for r in entries}
assert len(by_source) == len(entries)
verified = {}
@contextlib.contextmanager
def original_stream(row):
    if row['encoding'] == 'identity':
        with path(row['path']).open('rb') as f:
            yield f
    else:
        assert row['encoding'] == 'gzip'
        with gzip.open(path(row['path']), 'rb') as f:
            yield f
for r in entries:
    key = r['uncompressed_sha256']
    if key not in verified:
        assert digest(path(r['path'])) == r['sha256'] and path(r['path']).stat().st_size == r['stored_bytes']
        with original_stream(r) as f:
            actual, n = digest_stream(f)
        assert actual == key and n == r['uncompressed_bytes'], r['source']
        verified[key] = (n, r['path'], r['encoding'], r['sha256'], r['stored_bytes'])
    assert verified[key] == (r['uncompressed_bytes'], r['path'], r['encoding'], r['sha256'], r['stored_bytes']), r['source']
def source_json(source):
    with original_stream(by_source[source]) as f:
        return json.load(f)
omitted = {r['source']: r for r in provenance['omitted_binary_files']}
assert len(omitted) == len(provenance['omitted_binary_files'])
packets = json.loads((W / 'packets.json').read_text())
pins = 0
for label, p in packets.items():
    if not p['FROZEN_sha256']:
        continue
    source = p['original_directory']
    assert by_source[source+'/FROZEN.json']['uncompressed_sha256'] == p['FROZEN_sha256']
    m = source_json(source+'/FROZEN.json')
    assert len(m['files']) == p['frozen_pinned_files']
    for name, pin in m['files'].items():
        original = source+'/'+name
        r = by_source.get(original)
        if r:
            assert (r['uncompressed_sha256'], r['uncompressed_bytes']) == (pin['sha256'], pin['bytes']), original
        else:
            r = omitted[original]
            assert (r['sha256'], r['bytes']) == (pin['sha256'], pin['bytes']), original
        pins += 1
report = dict(status='PASS_PRIVATE_INTERMEDIATE_CHECKPOINT', stored_files=len(names), original_payloads_verified=len(entries), unique_payloads_verified=len(verified), frozen_manifest_pins_verified=pins, compiled_binaries_deliberately_omitted=len(omitted), portable_case_unique_paths=True, source_to_archive_path_mapping_verified=True, original_FROZEN_bytes_preserved=True, no_external_archive_or_live_source_dependency=True, new_ARM_MPFR_calls=0, hardware_accessed=False, integration_GO=False, goal_complete=False)
def equal64(got, expected):
    got, expected = int(got, 16), int(expected, 16)
    if expected & 0x7fffffffffffffff > 0x7ff0000000000000:
        return got & 0x7fffffffffffffff > 0x7ff0000000000000 and bool(got & (1 << 51))
    return got == expected
def records(label, filename):
    source = packets[label]['original_directory']+'/'+filename
    with original_stream(by_source[source]) as raw, gzip.GzipFile(fileobj=raw) as f:
        for line in f:
            yield json.loads(line)

def packet_json(label, name):
    return source_json(packets[label]['original_directory']+'/'+name)
def equal(got, expected, width=64, integer=False):
    if integer:
        return int(got,16) == int(expected,16)
    if width == 64:
        return equal64(got,expected)
    got,expected=int(got,16),int(expected,16)
    if expected & 0x7fffffff > 0x7f800000:
        return got & 0x7fffffff > 0x7f800000 and bool(got & (1<<22))
    return got == expected
def integer_result(op):
    return op in ('d2iz','d2uiz','d2lz','d2ulz') or op.startswith('dcmp')
def refs(row):
    return [n for n in row['outputs'] if n not in ('candidate','zero-control','prototype_r2') and not n.startswith('parent_R')]
def key(row,op):
    return (row['x'],row.get('y') if op in ('pow','dadd','dsub','dmul','ddiv') or op.startswith('dcmp') else None)
def raw_pin(label,name):
    return by_source[packets[label]['original_directory']+'/'+name]['uncompressed_sha256']
if args.records:
    from collections import defaultdict
    from itertools import zip_longest
    report['recounted_preserved_campaigns']={}
    report['qualification_recounts']={}
    for revision,parent_revision in [('r55','r52')]:
        label=revision+'-qualification'
        author=packet_json(label,'author-result.json')
        audit=packet_json(label,'joined-audit.json')
        terminal=packet_json(label,'producer-terminal.json')
        assert terminal['all_producers_terminal'] and all(j['exit_code']==0 for j in terminal['jobs'].values())
        losses,tested=defaultdict(set),defaultdict(set)
        public_calls=0
        for campaign in ('original507','broad'):
            name=campaign+'-records.jsonl.gz'
            result=packet_json(label,campaign+'.json')
            expected_audit=audit['primary'][campaign]
            relations=defaultdict(list)
            counts=Counter()
            total=wrong=integer_comparisons=calls=0
            oldrows=iter(records(parent_revision+'-qualification',name)) if parent_revision else None
            hists={n:Counter() for n in ('candidate','zero-control')}
            for row in records(label,name):
                total+=1
                op=row['operation']; integer=integer_result(op);width=row['result_width']
                counts[op]+=1
                k=key(row,op);tested[op].add(k)
                cid=row.get('case',row.get('index')); relations[cid]
                assert row['outputs']['candidate']==row['outputs']['zero-control']
                for n,value in row['outputs'].items():
                    correct=equal(value,row['expected'],width,integer)
                    assert correct==row['correct'][n],(label,campaign,total,n)
                    integer_comparisons+=integer
                    if n in ('candidate','zero-control'): assert correct
                    elif not correct: wrong+=1
                for n in refs(row):
                    if not row['correct'][n]:continue
                    c,q=row['instructions']['candidate'],row['instructions'][n]
                    rel='slower' if c>q else 'equal' if c==q else 'strict'
                    relations[cid].append(rel)
                    if c>q:losses[op].add(k)
                calls+=len(row['outputs'])
                if oldrows is not None:
                    old=next(oldrows,None);assert old is not None
                    assert all(row[n]==old[n] for n in set(row)-{'instructions','correct','outputs'})
                    assert row['outputs']==old['outputs']
                    for n in ('candidate','zero-control'):
                        hists[n][row['instructions'][n]-old['instructions'][n]]+=1
                    for n in refs(row):assert row['instructions'][n]==old['instructions'][n]
            if oldrows is not None:
                assert next(oldrows,None) is None
                assert {n:dict(h) for n,h in hists.items()}=={n:{int(k):v for k,v in h.items()} for n,h in expected_audit['candidate_and_control_delta_histograms'].items()}
            classes=Counter('slower' if 'slower' in r else 'equal' if 'equal' in r else 'strict' if r else 'no_correct_reference' for r in relations.values())
            assert total==expected_audit['state_rows'] and dict(counts)==expected_audit['operations']
            assert wrong==expected_audit['wrong_reference_outputs_and_costs_retained']
            assert integer_comparisons==expected_audit['exact_integer_output_comparisons']
            assert classes==expected_audit['all_correct_reference_classification']
            assert classes==result['every_correct_reference_classification' if campaign=='original507' else 'all_case_classification']
            assert calls==sum(result['completed_ARM_calls'].values())
            public_calls+=calls
            report['recounted_preserved_campaigns'][label+'/'+campaign]=dict(state_rows=total,public_ARM_calls_preserved=calls,classes=dict(classes),wrong_reference_rows_retained=wrong,exact_integer_comparisons=integer_comparisons)
            print('RECOUNTED',label,campaign,total,flush=True)
        for phase in ('full','admission','exp','ln'):
            result=packet_json(label,phase+'-result.json')
            old_parent=[n for n in next(iter(records(label,phase+'-records.jsonl.gz')))['outputs'] if n.startswith('parent_R')]
            assert len(old_parent)==1;pn=old_parent[0]
            assert raw_pin(label,phase+'-records.jsonl.gz')==result['records_sha256']
            assert raw_pin(label,phase+'-parent-increases.jsonl.gz')==result['adverse_records_sha256']
            assert raw_pin(label,phase+'-new-losses.jsonl.gz')==result['new_loss_records_sha256']
            adverse=iter(records(label,phase+'-parent-increases.jsonl.gz'))
            oldrows=iter(records(label,'admission-parent-records.jsonl.gz')) if phase=='admission' else iter(records(parent_revision+'-qualification',phase+'-records.jsonl.gz'))
            total=increases=wrong=0
            masks={};current,oldloss=set(),set();hist,paths=Counter(),Counter()
            op='pow' if phase in ('full','admission') else phase
            for row in records(label,phase+'-records.jsonl.gz'):
                total+=1;k=key(row,op);tested[op].add(k)
                bit={'READY':1,'DIRTY':2,'PENDING':4}[row['SIO']]
                assert not masks.get(k,0)&bit;masks[k]=masks.get(k,0)|bit
                assert equal64(row['outputs']['candidate'],row['expected'])
                assert equal64(row['outputs'][pn],row['expected'])
                delta=row['instructions']['candidate']-row['instructions'][pn]
                assert delta==row['parent_instruction_delta'];hist[delta]+=1
                if delta>0:
                    increases+=1;assert next(adverse,None)==row
                for n in refs(row):
                    correct=equal64(row['outputs'][n],row['expected'])
                    assert correct==row['correct'][n]
                    if not correct:wrong+=1;continue
                    if row['instructions'][pn]>row['instructions'][n]:oldloss.add(k)
                    if row['instructions']['candidate']>row['instructions'][n]:
                        current.add(k);losses[op].add(k)
                        assert row['instructions'][pn]>row['instructions'][n]
                if phase=='exp':
                    assert row['outputs']['candidate']==row['outputs']['prototype_r2']
                    assert row['instructions']['candidate']==row['instructions']['prototype_r2']
                    actual=row['actual_'+revision.upper()+'_path_visits']
                    paths['small{small}_incremental{incremental}_fallback{fallback}'.format(**actual)]+=1
                if oldrows is not None:
                    old=next(oldrows,None);assert old is not None
                    assert all(row.get(n)==old.get(n) for n in ('x','y','SIO','expected'))
                    assert row['outputs'][pn]==old['outputs']['candidate']
                    assert row['instructions'][pn]==old['instructions']['candidate']
                    for n in refs(row):
                        assert row['outputs'][n]==old['outputs'][n] and row['instructions'][n]==old['instructions'][n]
            assert next(adverse,None) is None and next(iter(records(label,phase+'-new-losses.jsonl.gz')),None) is None
            if oldrows is not None:assert next(oldrows,None) is None
            assert (total,len(masks),len(oldloss),len(current),increases,wrong)==(result['state_rows'],result['unique_inputs'],result['parent_losing_unique_inputs'],result['candidate_losing_unique_inputs'],result['all_parent_instruction_increase_rows'],result['wrong_Qfplib_state_comparisons_retained'])
            assert hist=={int(k):v for k,v in result['parent_instruction_delta_histogram'].items()}
            if phase=='exp':assert paths==result['actual_exp_path_histogram']
            if phase in ('exp','ln'):assert len(result['all10_division_entry_visits'])==10 and not sum(result['all10_division_entry_visits'].values())
            ar=audit['replays'][phase]
            assert (total,len(masks),len(current),increases,wrong)==(ar['state_rows'],ar['unique_inputs'],ar['candidate_losing_unique_inputs'],ar['all_parent_increase_rows'],ar['wrong_Qfplib_comparisons_retained'])
            public_calls+=total
            report['recounted_preserved_campaigns'][label+'/'+phase]=dict(state_rows=total,unique_inputs=len(masks),losing_unique_inputs=len(current),all_parent_increase_rows=increases,wrong_Qfplib_comparisons_retained=wrong,adverse_streams_exact=True)
            print('RECOUNTED',label,phase,total,len(current),increases,flush=True)
        caller_prefixes=[''] if revision=='r49' else ['','pow-']
        for p in caller_prefixes:
            result=packet_json(label,p+'caller-state-result.json')
            seen=set();cases=defaultdict(set)
            for row in records(label,p+'caller-state-records.jsonl.gz'):
                k=(row['x'],row['SIO'],row['NZCV'],row['R12']);assert k not in seen;seen.add(k)
                assert equal64(row['actual'],row['expected']) and row['instructions']==row['baseline_instructions']
                cases[(row['x'],row['SIO'])].add((row['NZCV'],row['R12']))
            assert len(seen)==result['caller_variation_ARM_calls'] and len(cases)==result['baseline_ARM_calls']
            assert all(len(v)==80 and {a for a,b in v}==set(range(16)) and len({b for a,b in v})==5 for v in cases.values())
            assert result['total_ARM_calls']==len(seen)+len(cases)
            public_calls+=result['total_ARM_calls']
            report['recounted_preserved_campaigns'][label+'/'+p+'caller']=dict(variation_rows=len(seen),baseline_calls=len(cases))
        assert public_calls==audit['actual_fresh_qualification_public_ARM_calls']==author['actual_fresh_qualification_public_ARM_calls']
        assert len(losses['pow'])==author['current_joined_pow_losing_pairs']
        assert [list(k) for k in sorted(losses['pow'])]==audit['remaining_pow_argument_pairs']
        assert all(not v for op,v in losses.items() if op!='pow')
        io=packet_json(label,'private-io-audit.json')
        assert io['denied_primary_open_attempts']==0 and len(io['receipts'])==(9 if revision=='r49' else 10)
        for rec in io['receipts']:
            assert raw_pin(label,rec['path'])==rec['sha256']
            actual=packet_json(label,rec['path']);assert not actual['denied_primary_open_attempts'] and actual['argv']==rec['argv']
            assert actual['primary_source_opens_prohibited'] and not actual['guest_code_or_registers_modified'] and not actual['ROM_models_installed']
        report['qualification_recounts'][revision]=dict(public_ARM_calls_preserved=public_calls,remaining_known_pow_pairs=len(losses['pow']),all_candidates_correct_on_saved_gold=True,all_correct_references_compared=True,source_producers_executed=False)
    source_author=packet_json('r55-source','AUTHOR-SOURCE-RESULT.json')
    for name,pin in source_author['source_required_proofs'].items():
        assert raw_pin('r55-source',name)==pin['sha256']
        assert packet_json('r55-source',name)['status'].startswith('PASS_')
    for name,n in [('saturation-linked-proof.json',64),('center-linked-proof.json',24),('smallfactor-linked-proof.json',26),('native-entry-proof.json',18)]:
        gate=packet_json('r55-source',name)
        assert gate['status'].startswith('PASS_') and len(gate['negative_controls'])==n and all(c['rejected'] for c in gate['negative_controls'])
    current=packet_json('r55-qualification','author-result.json')
    assert current['all21_other_original_objects_exact'] and current['M4_default_objects_exact']
    assert current['changed_object_unaffected_sections_symbols_relocations_exact']
    assert current['text_delta_bytes']==32 and current['scratch_code_delta_bytes']==-8 and current['total_allocated_delta_bytes']==24
    assert current['new_lookup_table_global_RAM_libgcc_bytes']==0
    assert current['current_joined_pow_losing_pairs']==1452 and current['old_same_expanded_corpus_R52_losing_pairs']==1886
    assert current['expanded_corpus_fixed_pairs']==434 and current['fixed_pairs_on_old_R52_corpus']==368
    isolation=packet_json('r55-qualification','section-isolation.json')
    assert isolation['default_M0_M4_exact'] and isolation['division_sections_and_semantic_relocations_exact']
    profile=packet_json('r55-profile','profile.json')
    assert profile['remaining_pairs']==1452 and profile['qualification_FROZEN_sha256']==packets['r55-qualification']['FROZEN_sha256']
    assert sum(profile['categories'][n] for n in ('inverse_root','zero_or_infinity','normal_result'))==1452
    assert not current['physical_cycles_measured'] and not current['universal_correct_rounding_closed']
    assert source_author['R53_rejected_new_correct_reference_loss_pairs']==20 and source_author['R54_rejected_new_correct_reference_loss_pairs']==2
    assert index['selected_private_author_source']=='R55' and not index['canonical_runtime_integrated']
    assert index['HIL_draft_not_board_bootable'] and not index['hardware_accessed']

if args.report:
    p = args.report.resolve()
    assert p != W and W not in p.parents, 'Receipts must be outside the immutable archive.'
    p.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k != 'recounted_preserved_campaigns'}, indent=2))
