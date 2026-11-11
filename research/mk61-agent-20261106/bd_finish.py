"""Finalize the diagnostic without touching any training ledger or selected model."""
import contextlib
import io
import json
import time
from bd_common import ROOT,HERE,SOURCE,MODEL,read,write,sha,check_frozen


def main():
    root=ROOT/'server-results';check_frozen()
    assert read(ROOT/'collection.json')['complete']
    post=read(root/'postflight.json');assert post['all_frozen_files_verified']and post['own_containers_running']==[]
    assert sha(SOURCE/'model.mkqb')==sha(MODEL/'model.mkqb')==read(ROOT/'frozen.json')['source_Q4_sha256']
    from ay_common import check_frozen as ac
    from az_common import check_frozen as zc
    from ba_common import check_frozen as bc
    for check in [ac,zc,bc]:check()
    from bd_report import main as report
    with contextlib.redirect_stdout(io.StringIO()):report(root)
    comparison=read(root/'comparison.json');path=HERE/'work-state.json';state=read(path)
    counters={k:state[k]for k in ['completed_training_runs','total_accounted_optimizer_updates_lower_bound']}
    state['latest_spec_factorial_diagnostic']={**state['latest_spec_factorial_diagnostic'],
        'status':'complete','optimizer_updates':0,'teacher_calls':0,'all_own_jobs_complete':True,
        'arms':comparison['arms'],'initial_intent':comparison['initial_intent'],
        'paired':comparison['paired'],'fresh_unique_Q4_prompts':comparison['generations']['fresh_unique_Q4_prompts'],
        'native_feedback_probes':read(root/'native-verification.json')['fresh_feedback_probes'],
        'baseline_replay_exact':True,'weights_unchanged':True,'training_ledger_unchanged':True,
        'report':str(HERE/'SPEC_FACTORIAL_DIAGNOSTIC_RESULTS.md'),'unix_complete':time.time()}
    state.update(phase='spec_factorial_diagnostic_complete',active_experiment=None,all_own_jobs_complete=True,
        all_own_remote_jobs_complete=True,latest_report=str(HERE/'SPEC_FACTORIAL_DIAGNOSTIC_RESULTS.md'),
        next_action='Prioritize condition-to-SPEC understanding. The oracle mechanical controller solves256/256, but automatically using the model own unconfirmed SPEC raises false DONE18->30. Keep unconfirmed proposals separate from independently confirmed completion; next training comparison is narrow SPEC LoRA versus full3M, with a new sealed exam.')
    assert counters=={k:state[k]for k in counters};write(path,state)
    write(root/'finalized.json',{'complete':True,'optimizer_updates':0,'teacher_calls':0,
        'source_and_copied_model_unchanged':True,'previous_rounds_frozen_verified':True,
        'ledger_counters_unchanged':counters,'report_sha256':sha(HERE/'SPEC_FACTORIAL_DIAGNOSTIC_RESULTS.md'),
        'main_profile_not_replaced':True,'unix':time.time()})
    print(json.dumps({'complete':True,'optimizer_updates':0,'model_unchanged':True,'report':state['latest_report']}))


if __name__=='__main__':main()
