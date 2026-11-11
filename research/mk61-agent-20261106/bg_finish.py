"""Finalize the natural-language continuation and account12,000 updates once."""
import contextlib
import io
import json
import time
from bg_common import ROOT,HERE,read,write,sha,check_frozen

def main():
    root=ROOT/'server-results';check_frozen();assert read(ROOT/'collection.json')['complete']
    post=read(root/'postflight.json');assert post['all_frozen_files_verified']and not post['own_containers_running']
    from be_common import check_frozen as be
    from bd_common import check_frozen as bd
    be();bd()
    from bg_package import main as package
    package(root)
    from bg_report import main as report
    with contextlib.redirect_stdout(io.StringIO()):report(root)
    stats=read(root/'comparison.json');path=HERE/'work-state.json';state=read(path);old=state.get('latest_preserve_spec_training',{'ledger_accounted':False})
    updates=sum(stats['training'][a]['optimizer_updates']for a in ['lora','full']);assert updates==12000
    if not old.get('ledger_accounted'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=updates
    preferred=stats['selection']['preferred']
    state['latest_preserve_spec_training']={**old,'status':'complete','ledger_accounted':True,'optimizer_updates':updates,
        'selected':stats['selection'],'data_counts':stats['data']['counts'],'models':stats['models'],
        'paired':stats['paired'],'training':stats['training'],'all_own_jobs_complete':True,
        'source_and_previous_rounds_preserved':True,'report':str(HERE/'PRESERVE_SPEC_LORA_FULL_RESULTS.md'),
        'native':{a:{k:v[k]for k in ['probes','mka_bytes','mka_sha256','input_embedding_weights_changed']}for a,v in stats['native']['models'].items()},
        'unix_complete':time.time()}
    state.update(phase='preserve_SPEC_LoRA_vs_full_complete',active_experiment=None,all_own_jobs_complete=True,
        all_own_remote_jobs_complete=True,remote_experiment_jobs_complete=True,
        latest_report=str(HERE/'PRESERVE_SPEC_LORA_FULL_RESULTS.md'),latest_training_quality_target_met=False,
        next_action='Review false DONE, corruption of correct starts and successful repairs separately on the new Q4 exam. Preserve the sealed-test discipline and keep unconfirmed interpretation separate from verified execution.')
    state['latest_training_outcome']={'report':str(HERE/'PRESERVE_SPEC_LORA_FULL_RESULTS.md'),
        'selected_research_artifact':str(root/'export'/preferred),'both_branches':[str(root/'export'/a)for a in ['lora','full']],
        'automatic_DONE_goal_met':False,'all_own_jobs_complete':True,'new_optimizer_updates':updates,
        'source_checkpoints_preserved':True,'main_profile_not_replaced':True}
    write(path,state);write(root/'finalized.json',{'complete':True,'optimizer_updates':updates,'ledger_accounted':True,
        'previous_rounds_frozen_verified':True,'main_profile_not_replaced':True,
        'report_sha256':sha(HERE/'PRESERVE_SPEC_LORA_FULL_RESULTS.md'),'unix':time.time()})
    print(json.dumps({'complete':True,'updates':updates,'preferred_preclosed':preferred,
        'completed_training_runs':state['completed_training_runs'],'total_updates_lower_bound':state['total_accounted_optimizer_updates_lower_bound']}))

if __name__=='__main__':main()
