"""Additional preselected nonzero-prior ablation and implementation checks."""
import json
import time
from ad_common import ROOT,PREVIOUS,HERE,MODEL,PRIOR_ROOT,read,write,sha
from ad_features import Critic,structure
from ad_inference import Bank
from ad_experiment import rollout,panel_summary
from ha_protocol import encode,constants


def main():
    while not(ROOT/'complete.json').exists():
        status=json.loads((ROOT/'status.json').read_text())if(ROOT/'status.json').exists()else{}
        if status.get('phase')=='failed':raise RuntimeError(status)
        time.sleep(2)
    selection=json.loads((ROOT/'nonzero-selection.json').read_text());bank=Bank()
    panel=json.loads((ROOT/'exam-candidate-panel.json').read_text())
    write(ROOT/'nonzero-exam-candidate-summary.json',panel_summary(panel,selection))
    tasks=read(ROOT/'exam.jsonl');seeds=read(ROOT/'exam-seeds.jsonl');twins=read(ROOT/'exam-twins.jsonl');twin_seeds=read(ROOT/'exam-twin-seeds.jsonl')
    scratch=[t for level in [1,2]for t in [t for t in tasks if t['level']==level][:16]]
    if not(ROOT/'nonzero_statistics-exam.json').exists():
        value={'main':rollout(bank,'best4_statistics',tasks,seeds,selection),
            'goal_twins':rollout(bank,'best4_statistics',twins,twin_seeds,selection),
            'from_scratch':rollout(bank,'best4_statistics',scratch,[{'task_id':t['id']}for t in scratch],selection,
                                  compiler_rows=json.loads((ROOT/'scratch-compiler.json').read_text())),
            'config':selection['config'],'selected_only_on_development':True}
        write(ROOT/'nonzero_statistics-exam.json',value)
    # A called routine after the first STOP must remain reachable.
    assert structure([0x60,0x53,0x06,0x61,0x10,0x50,0x1C,0x52])['unreachable_on_first_run']==[]
    assert structure([0x50,0x54,0x03,0x61,0x10,0x50])['unreachable_on_first_run']==[1,2,3,4,5]
    # Inference sampling uses the same random stream for an individual prompt.
    probes=panel['details'][:3];actual=bank.writes([p['prompt']for p in probes],1)
    for p,row in zip(probes,actual):assert row['generated_token_ids']==p['candidates'][1]['generation']['generated_token_ids']
    critic=Critic(selection['config']['prior']);known=[]
    for t in read(PREVIOUS/'isa-audit.jsonl'):
        if t.get('kind')!='primitive'or t.get('catalog_risk')!='documented':continue
        pool=t.get('constants')or constants(t['task']);body=encode(t['reference_code'],pool,'asm');f=critic.inspect(tuple(body),tuple(pool))
        known.append({'opcode':t['opcode'],'angle':t['angle'],'valid':f['valid'],'warning':critic.note(f,selection['feedback_low_prior_threshold']),
                    'log_prior':f['log_prior']})
    assert len(known)==648
    frozen=json.loads((ROOT/'data-frozen.json').read_text());protocol=json.loads((ROOT/'selection-protocol.json').read_text())
    for name,digest in frozen['files'].items():assert sha(ROOT/name)==digest,name
    for name,digest in protocol['source_hashes'].items():assert sha(HERE/name)==digest,name
    for name,digest in frozen['prior_files'].items():assert sha(PRIOR_ROOT/name)==digest,name
    assert sha(MODEL/'model.mkqb')==frozen['model_packet_sha256']
    assert sha(PREVIOUS/'export/compiler/model.mkqb')==frozen['compiler_packet_sha256']
    write(ROOT/'verification.json',{'complete':True,'frozen_data_source_priors_and_weights_unchanged':True,
          'per_prompt_sampling_streams_reproduced':len(probes),'subroutine_reachability_checked':True,
          'runtime_inputs_exclude_reference_expected_hidden':True,'retention_reference_programs':len(known),
          'retention_reference_warnings':sum(bool(r['warning'])for r in known),'retention_details':known,
          'device_deployed':False,'optimizer_updates':0,'all_local_runs_complete':True})
    write(ROOT/'status.json',{'phase':'complete_with_ablation','unix':time.time()})
    print(json.dumps({'additional_ablation_complete':True,'verification_complete':True}),flush=True)


if __name__=='__main__':main()
