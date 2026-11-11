"""Finalize provenance and account only the two completed SGD runs, once."""
import contextlib
import io
import json
import shutil
import time
from bc_common import ROOT,HERE,SOURCE,read,write,sha,check_frozen


def main():
    root=ROOT/'server-results'
    assert read(root/'supplementary-collection.json')['complete']
    assert read(root/'final-postflight.json')['own_containers_running']==[]
    check_frozen()
    from ay_common import check_frozen as ay_check
    from az_common import check_frozen as az_check
    from ba_common import check_frozen as ba_check
    for check in [ay_check,az_check,ba_check]:check()
    selected=read(root/'preselected.json')['selected']
    supplemental=read(root/'specialist-policy.json')
    for role in ['parent','spec','safety']:
        folder=root/'export'/role;before={n:sha(folder/n)for n in ['model.mkqb','model.mka']}
        if role=='safety':
            schema=read(SOURCE/'wire-format.json');schema.update(experiment='semantic-spec-selfcheck-v1',role=role,
                generated_spec_is_not_confirmation_of_request=True,literal_pool_training='dynamic full/extras permutations and distractors')
            write(folder/'wire-format.json',schema)
        runtime=folder/'protocol-source';runtime.mkdir(exist_ok=True)
        for name in ['ay_codec.py','ay_runtime.py','az_runtime.py','ay_chat.py','az_chat.py','az_teacher.py','ay_teacher.py',
                'ax_completion.py','ba_pools.py','bb_canonical.py','bb_session.py','bb_chat.py']:
            shutil.copyfile(HERE/name,runtime/name)
        write(folder/'protocol-source-sha256.json',{p.name:sha(p)for p in runtime.iterdir()if p.is_file()})
        manifest=read(folder/'manifest.json');manifest.update(experiment='semantic-spec-selfcheck-v1',role=role,
            parent_packet_sha256=sha(SOURCE/'model.mkqb'),selection_used_closed_test=False,
            canonical_harness_used_in_closed_exam=False)
        if role=='spec':manifest.update(selected_run=selected['run'],selected_step=selected['step'],
            recovery_alpha=selected.get('recovery_alpha'),adapter_checkpoint_sha256=selected['sha256'])
        if role=='safety':manifest.update(selected_run='seed-b',adapter_checkpoint_sha256=supplemental['checkpoint_sha256'],
            supplementary_profile=True,passes_balanced_retention_guards=False)
        write(folder/'manifest.json',manifest)
        assert before=={n:sha(folder/n)for n in before}
    from bc_report import main as report
    with contextlib.redirect_stdout(io.StringIO()):report(root)
    stats=read(root/'comparison.json');state_path=HERE/'work-state.json';state=read(state_path)
    previous=state['latest_spec_selfcheck_training']
    updates=sum(read(root/run/'training.json')['optimizer_updates']for run in ['seed-a','seed-b']);assert updates==8000
    if not previous.get('ledger_accounted'):
        state['completed_training_runs']+=2
        state['total_accounted_optimizer_updates_lower_bound']+=updates
    state['latest_spec_selfcheck_training']={**previous,'status':'complete','ledger_accounted':True,
        'optimizer_updates':updates,'runs':2,'steps_per_run':4000,'selected':selected,
        'supplementary_selection':supplemental,'all_own_jobs_complete':True,'closed_used_for_selection':False,
        'analysis':stats['analysis'],'data':stats['data'],'parent':stats['parent'],'spec':stats['spec'],
        'supplementary':stats['supplementary_self_profile']['summary'],
        'retired19':{name:value['summary']for name,value in stats['retired19'].items()},
        'supplementary_retired19':stats['supplementary_self_profile']['retired19']['summary'],
        'paired':stats['paired'],'report':str(HERE/'SPEC_SELF_CHECK_RESULTS.md'),
        'native_models':{name:{k:v[k]for k in ['probes','mka_bytes','mka_sha256']}for name,v in read(root/'native-verification.json')['models'].items()},
        'automatic_DONE_goal_met':False,'unix_complete':time.time()}
    state.update(phase='spec_selfcheck_complete',active_experiment=None,all_own_jobs_complete=True,
        all_own_remote_jobs_complete=True,remote_experiment_jobs_complete=True,
        latest_report=str(HERE/'SPEC_SELF_CHECK_RESULTS.md'),latest_training_quality_target_met=False,
        next_action='Review the new closed results: the balanced model translates and repairs better, but false self-DONE is unresolved. Investigate a visible, revisable hypothesis and independent condition-to-spec validation before further generic training.')
    state['latest_training_outcome']={'report':str(HERE/'SPEC_SELF_CHECK_RESULTS.md'),
        'selected_research_artifact':str(root/'export/spec'),'supplementary_self_profile':str(root/'export/safety'),
        'automatic_DONE_goal_met':False,'all_own_jobs_complete':True,'new_optimizer_updates':8000,
        'source_checkpoint_preserved':True,'main_profile_not_replaced':True}
    write(state_path,state)
    write(root/'finalized.json',{'complete':True,'optimizer_updates':updates,'ledger_accounted':True,
        'previous_rounds_frozen':True,'model_bytes_unchanged_by_packaging':True,
        'main_profile_not_replaced':True,'report_sha256':sha(HERE/'SPEC_SELF_CHECK_RESULTS.md'),'unix':time.time()})
    print(json.dumps({'complete':True,'updates':updates,'completed_training_runs':state['completed_training_runs'],
        'total_updates_lower_bound':state['total_accounted_optimizer_updates_lower_bound']}))


if __name__=='__main__':main()
