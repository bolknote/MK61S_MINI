"""Finalize both exports and account the actual8,000 updates exactly once."""
import contextlib
import io
import json
import time
from be_common import ROOT,HERE,read,write,sha,check_frozen

def main():
    root=ROOT/'server-results';check_frozen();assert read(ROOT/'collection.json')['complete']
    post=read(root/'postflight.json');assert post['all_frozen_files_verified']and not post['own_containers_running']
    from ay_common import check_frozen as ay
    from az_common import check_frozen as az
    from ba_common import check_frozen as ba
    from bd_common import check_frozen as bd
    for check in [ay,az,ba,bd]:check()
    write(root/'extended-holdout-audit.json',read(ROOT/'extended-holdout-audit.json'))
    from be_semantics import audit
    audit(root)
    from be_package import main as package
    package(root)
    from be_report import main as report
    with contextlib.redirect_stdout(io.StringIO()):report(root)
    stats=read(root/'comparison.json');state_path=HERE/'work-state.json';state=read(state_path);old=state['latest_clean_spec_training']
    updates=sum(stats['training'][a]['optimizer_updates']for a in ['lora','full']);assert updates==8000
    if not old.get('ledger_accounted'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=updates
    preferred=stats['selected']['preferred']
    state['latest_clean_spec_training']={**old,'status':'complete','ledger_accounted':True,'optimizer_updates':updates,
        'selected':stats['selected'],'data_counts':stats['data']['counts'],'models':stats['models'],'paired':stats['paired'],
        'training':stats['training'],'source_and_prior_experiments_preserved':True,'all_own_jobs_complete':True,
        'native':{a:{k:v[k]for k in ['probes','mka_bytes','mka_sha256','input_embedding_weights_changed']}for a,v in stats['native']['models'].items()},
        'report':str(HERE/'CLEAN_SPEC_LORA_FULL_RESULTS.md'),'unix_complete':time.time()}
    state.update(phase='clean_SPEC_LoRA_vs_full_complete',active_experiment=None,all_own_jobs_complete=True,
        all_own_remote_jobs_complete=True,remote_experiment_jobs_complete=True,
        latest_report=str(HERE/'CLEAN_SPEC_LORA_FULL_RESULTS.md'),latest_training_quality_target_met=False,
        next_action='Review the sealed Q4 comparison and the separate ordinary-Russian editorial panel; improve ordinary-language transfer if it remains weak. Keep unconfirmed semantic proposals separate from independently confirmed completion.')
    state['latest_training_outcome']={'report':str(HERE/'CLEAN_SPEC_LORA_FULL_RESULTS.md'),
        'selected_research_artifact':str(root/'export'/preferred),'both_branches':[str(root/'export'/a)for a in ['lora','full']],
        'automatic_DONE_goal_met':False,'all_own_jobs_complete':True,'new_optimizer_updates':updates,
        'source_checkpoint_preserved':True,'main_profile_not_replaced':True}
    write(state_path,state)
    write(root/'finalized.json',{'complete':True,'optimizer_updates':updates,'ledger_accounted':True,
        'previous_rounds_frozen_verified':True,'main_profile_not_replaced':True,
        'report_sha256':sha(HERE/'CLEAN_SPEC_LORA_FULL_RESULTS.md'),'unix':time.time()})
    print(json.dumps({'complete':True,'optimizer_updates':updates,'preferred_preclosed':preferred,
        'completed_training_runs':state['completed_training_runs'],'total_updates_lower_bound':state['total_accounted_optimizer_updates_lower_bound']}))

if __name__=='__main__':main()
