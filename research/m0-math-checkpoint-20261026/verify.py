#!/usr/bin/env python3
"""Verify the preserved intermediate state; never execute archived producers."""
from pathlib import Path
from collections import Counter
import argparse,ast,gzip,hashlib,importlib.util,io,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
PREVIOUS=W.parent/'m0-math-checkpoint-20261025-5'
spec=importlib.util.spec_from_file_location('previous_math_checkpoint',PREVIOUS/'verify.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
image_fingerprint=previous.image_fingerprint
SOURCE_SUFFIXES=previous.SOURCE_SUFFIXES
sha=lambda b:hashlib.sha256(b).hexdigest()
def raw(name,directory=W):
    p=directory/name
    return p.read_bytes()if p.exists()else gzip.decompress(p.with_suffix(p.suffix+'.gz').read_bytes())
def report(name,directory=W):return json.loads(raw(name,directory))
def equal(a,b):
    if a==b:return True
    return all((int(v,16)&0x7fffffffffffffff)>0x7ff0000000000000 and int(v,16)&(1<<51)for v in(a,b))
def verify(check_local=False):
    index=report('checkpoint.json');provenance=report('provenance.json');entries=provenance['archived_files'];by_source={r['source']:r for r in entries}
    assert len(by_source)==len(entries)
    assert sha((ROOT/index['base_checkpoint']).read_bytes())==index['base_checkpoint_sha256']
    for name,pin in index['files'].items():assert sha((W/name).read_bytes())==pin,name
    local=0;decoded={}
    for r in entries:
        p=W/r['path'];s=Path(r['source']);assert not s.is_absolute()and '..'not in s.parts and '.git'not in s.parts
        if r['path']not in decoded:
            data=p.read_bytes();assert sha(data)==r['sha256'],r['path'];data=gzip.decompress(data)if r['encoding']=='gzip'else data
            assert len(data)==r['uncompressed_bytes']and sha(data)==r['uncompressed_sha256'];decoded[r['path']]=True
        if check_local:
            original=ROOT/s;assert original.is_file(),str(original)
            assert original.stat().st_size==r['uncompressed_bytes']and sha(original.read_bytes())==r['uncompressed_sha256'],r['source'];local+=1
    def origin(name):
        r=by_source[name];data=(W/r['path']).read_bytes();return gzip.decompress(data)if r['encoding']=='gzip'else data
    r47='.build/m0-math-unified-ddiv-normalized-r47-20261026/'
    status=json.loads(origin(r47+'result.json'));assert not status['selected']and status['selected_qualified_source_remains_R45']and not status['goal_complete']
    assert status['all17_other_objects_M4default_exact']and status['full_primary_and_pow_exp_ln_qualification_pending']
    for name,n in [('normalized-div-proof.json',16),('native-caller-proof.json',12),('div-guard-proof.json',6)]:
        proof=json.loads(origin(r47+name));assert len(proof['negative_controls_rejected'])==n and proof['candidate_ELF_sha256']==status['candidate_ELF_sha256']
    assert json.loads(origin(r47+'source-reversal.json'))['status']=='PASS_R47_TWO_SOURCE_FILES_REVERSE_EXACTLY_TO_R45'
    assert origin(r47+'controls.log').decode().strip().splitlines()==['verify-private-return PASS','verify-guard-controls PASS','verify-loader PASS','verify-disabled PASS']
    campaigns={};all_div_inputs=set();all_div_parent_losses=set()
    for label,records,result_file,expected_inputs,expected_calls,expected_losses,expected_inc in [('direct','div-probe-records.jsonl.gz','div-probe-result.json',2862,25758,0,2568),('expanded','boundary-replay-records.jsonl.gz','boundary-replay-result.json',77282,231846,0,48426),('pow','probe-records.jsonl.gz','probe-result.json',16740,251100,2045,36)]:
        result=json.loads(origin(r47+result_file));inputs=set();states=set();losses=set();parents=set();increased=Counter();rows=0;wrong_refs=0
        with gzip.GzipFile(fileobj=io.BytesIO(origin(r47+records)))as f:
            for line in f:
                r=json.loads(line);pair=(r['x'],r['y'])if label=='pow'else(r['a'],r['b']);key=(*pair,r['SIO']);assert key not in states;states.add(key);inputs.add(pair)
                assert r['correct']['candidate']and equal(r['outputs']['candidate'],r['expected'])
                refs=[k for k in r['instructions']if k.startswith('qfp_')]if label=='pow'else['Qfplib'];assert len(refs)==(3 if label=='pow'else 1)
                for ref in refs:
                    assert r['correct'][ref]==equal(r['outputs'][ref],r['expected'])
                    if not r['correct'][ref]:wrong_refs+=1;continue
                    if r['instructions']['parent']>r['instructions'][ref]:parents.add(pair)
                    if r['instructions']['candidate']>r['instructions'][ref]:losses.add(pair);assert r['instructions']['parent']>r['instructions'][ref]
                if r['instructions']['candidate']>r['instructions']['parent']:increased[key]+=1
                rows+=1
        source_inc=result['all_parent_instruction_increase_rows'];saved=Counter((r['x'],r['y'],r['SIO'])if label=='pow'else(r['a'],r['b'],r['SIO'])for r in source_inc)
        assert increased==saved and len(source_inc)==expected_inc
        assert len(inputs)==expected_inputs and rows==expected_inputs*3 and len(losses)==expected_losses
        assert result['actual_diagnostic_ARM_calls']==expected_calls and result['candidate_wrong']==0 and result['candidate_ELF_sha256']==status['candidate_ELF_sha256']
        assert len(parents)==result['parent_losing_pairs']and sorted(losses)==sorted(map(tuple,result['remaining_losing_argument_pairs']))
        if label!='pow':all_div_inputs.update(inputs);all_div_parent_losses.update(parents)
        campaigns[label]=dict(inputs=len(inputs),state_rows=rows,fresh_ARM_calls=expected_calls,parent_losses=len(parents),candidate_losses=len(losses),all_parent_increase_rows=len(source_inc),incorrect_reference_rows_retained=wrong_refs)
    assert len(all_div_parent_losses)==36936
    assert sum(c['fresh_ARM_calls']for c in campaigns.values())==status['actual_R47_diagnostic_ARM_calls']==508704
    assert status['actual_R47_MPFR_evaluations']==19554 and status['sNaN_policy_shortcuts']==48
    assert status['expanded_division']['gold_R45_Qfplib_cached_frozen_R46']
    r45='.build/m0-math-unified-ddiv-cold-overflow-r45-qualification-20261026/'
    a=json.loads(origin(r45+'author-result.json'));assert a['goal_complete']is False
    return dict(status='PASS_INTERMEDIATE_R45_R47_ARCHIVE',stored_payloads=len(decoded),preserved_original_files=len(entries),local_original_files_checked=local,R47_campaigns=campaigns,R47_division_unique_input_union=len(all_div_inputs),R45_losing_division_union=len(all_div_parent_losses),R47_fresh_diagnostic_ARM_calls=508704,R47_full_public_qualification_pending=True,actual_new_ARM_MPFR_calls=0,hardware_accessed=False,goal_complete=False)
def build(output,tc):
    # Reuse the already committed offline materializer, with this checkpoint's
    # manifest, original-path map and recipes. Its only executable inputs are
    # the recorded compiler/linker commands; archived producers never run.
    tree=ast.parse((PREVIOUS/'verify.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='build')
    env=dict(ROOT=ROOT,W=W,report=report,SOURCE_SUFFIXES=SOURCE_SUFFIXES,gzip=gzip,Path=Path,json=json,subprocess=subprocess,image_fingerprint=image_fingerprint)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'committed_offline_materializer','exec'),env)
    return env['build'](output,tc)
def main():
    p=argparse.ArgumentParser();p.add_argument('--check-local',action='store_true');p.add_argument('--build-output',type=Path);p.add_argument('--toolchain',type=Path);a=p.parse_args();r=verify(a.check_local)
    if a.build_output:
        assert a.toolchain is not None;r['code_rebuild']=build(a.build_output,a.toolchain);(a.build_output/'verification.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
if __name__=='__main__':main()
