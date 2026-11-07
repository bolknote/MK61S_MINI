"""Report paired outcomes without silently relaxing the release criterion."""
import argparse
import json
from pathlib import Path
from ab_common import HERE,ARMS,read,write,sha


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    selection=json.loads((root/'preselected.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    data=json.loads((root/'data-frozen.json').read_text());policy=json.loads((root/'policy.json').read_text())
    results={arm:json.loads((root/(arm+'-audit.json')).read_text())for arm in ARMS}
    text=['# 3M Q4: separate actions, diagnosis and iterative preferences','',
          'A bounded paired experiment, not a device release. The original harness-debug-v3 exports and exam results remain unchanged.','',
          'The model uses 7 existing reserved IDs for WRITE/PATCH/RUN/TRACE/DIAG/DONE/UNSURE, 23 HEX-body IDs and the original < row30 as terminator:31 output rows. Russian input vocabulary and all original input embedding rows are bit-identical. No parameter-count increase.','',
          'The synthetic < primer is encoded separately to avoid the space/< BPE merge. A wire action is never fed into KV; the runtime instead inserts the original fixed neural tag header for that chosen action. These headers select no instruction and contain no task answer. A pre-training pilot reproduced131/131 old programs exactly with this adapter and no SGD.','',
          'Training objective: CE(action) + 0.5 × per-example mean CE(HEX arguments) + 0.03 × language replay. Action CE is not divided by answer length. The preference arm additionally uses action-only DPO (beta=0.2, weight=0.5) with the fixed common warmup as reference; argument tokens use the same SFT objective in both arms.','',
          f'Common readout-only warmup: {policy["format_warmup_steps"]} updates; the original backbone is bit-identical after this stage. Each arm: {policy["stages"]} stages × {policy["steps_per_stage"]} updates, batch128, Q4 from update1. Backbone LR2e-6, action readout LR2e-5. Both arms use identical SFT draw digests at every stage. Current-student states refresh after warmup and stages1–2; validation/final tasks never enter these pools.','',
          f'Offline process lessons: {data["expert_lessons"]:,}. Training and development reuse the v1 course,1000 additional training tasks and250 development tasks. A new250-task final set was frozen before v2 SGD, disjoint from v1 and v3 exact task texts. Development and final each have500 episodes (one verified wrong and one semantically correct start per task), with1–4 public inputs. These are new instances of partly familiar families.','',
          'Contracts: preserve memory when that is graded; no implicit PC/one-instruction constraint for ordinary semantic stop tasks. Equivalent correct programs, including verified extra-NOP alternatives, are accepted. Historical exams were not relabelled.','',
          'DIAG is a five-byte hypothesis: cause, proposed expected serialized byte, cited serialized byte, two-byte serialized offset. The runtime returns the actual byte at that offset (or an out-of-bounds fact), even when the citation is wrong. This prevents a mistaken hypothesis from blocking the repair loop. Teacher hypotheses use a verified canonical repair; they do not prove a unique cause. Runtime tools expose only actual public executions. Hidden expected outputs are used solely by offline teachers and grading.','',
          'Strict tool success requires a correct final program, explicit DONE, and execution/stopping of every public case on that program revision. False DONE counts semantically incorrect programs that the raw model declared complete. UNSURE and timeouts are unsolved. No semantic oracle or learned critic overrides raw decisions.','',
          '| Arm | Selected stage | New code generation | Repair + finish | All strict tool successes | False DONE | Premature DONE | UNSURE | ISA retention | Old formulas |',
          '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    summary={}
    for arm,r in results.items():
        t=r['tools'];summary[arm]={'selected_stage':selection['choices'][arm]['stage'],
             'language':[r['language']['passed'],r['language']['total']],
             'tools':{k:v for k,v in t.items()if k!='details'},'isa':[r['isa']['passed'],r['isa']['total']],
             'legacy':[r['legacy']['passed'],r['legacy']['total']],
             'from_scratch':{k:v for k,v in r['from_scratch'].items()if k!='details'}}
        text.append(f'| {arm} | {summary[arm]["selected_stage"]} | {r["language"]["passed"]}/{r["language"]["total"]} | {t["repaired"]}/{t["initially_wrong"]} | {t["passed"]}/{t["total"]} | {t["false_DONE"]} | {t["premature_DONE"]} | {t["abstained"]} | {r["isa"]["passed"]}/648 | {r["legacy"]["passed"]}/98 |')
    text+=['','Validation selection was frozen before the final exam. Release criterion: zero false DONE, at least80% strict tool success, all648 documented opcode/mode cases retained and at least66/98 old formulas. An abstain-all model cannot pass.',
           '',f'Selected research artifact: `{selection["selected_arm"]}`. Validation release criterion met: **{selection["release_eligible"]}**. Final exam does not retroactively change checkpoint selection.','',
           '| Public cases | SFT strict success | SFT false DONE | Preference strict success | Preference false DONE |',
           '|---:|---:|---:|---:|---:|']
    for n in range(1,5):
        left=results['sft']['tools']['by_public_count'][str(n)];right=results['preference']['tools']['by_public_count'][str(n)]
        text.append(f'| {n} | {left["passed"]}/{left["total"]} | {left["false_DONE"]} | {right["passed"]}/{right["total"]} | {right["false_DONE"]} |')
    text+=['','Native verification:','']
    for arm,r in native['models'].items():
        text.append(f'- {arm}: exact Q4 re-export/reload; CPU/B200 {r["cpu_matches"]}/{r["probes"]}; native/B200 {r["native_matches"]}/{r["probes"]}; MKA {r["package_bytes"]:,} B; FP32 KV at1024 {r["cache_bytes"]:,} B; model workspace {r["workspace_bytes"]:,} B.')
    text+=['',f'Allocation-free action parser: {native["parser"]["state_bytes"]} B, {native["parser"]["roundtrips_and_python_masks_matched"]} round trips and allowed-token masks matched Python. Full device peak RAM and speed were not measured. The existing assembler/runtime need additional memory.','',
           'Artifacts: `export/sft`, `export/preference`, `export/selected-research`; CLI: `ab_chat.py --model PATH --angle DEG --inputs JSON [--native] QUESTION`. A model DONE remains a claim: the public-input-only CLI reports `verified_task_success:null`.','',
           'All own GPU jobs ended; source checkpoint, frozen training/evaluation files and private emulator source were checked unchanged. See `postflight.json`.']
    (HERE/'ACTION_ALIGNMENT_V2_RESULTS.md').write_text('\n'.join(text)+'\n')
    write(root/'summary.json',{'selected_arm':selection['selected_arm'],'release_eligible':selection['release_eligible'],
                             'results':summary,'updates_total':policy['format_warmup_steps']+2*policy['stages']*policy['steps_per_stage'],
                             'native_verification_complete':True,'physical_picocalc_measured':False})
    state_path=HERE/'work-state.json';state=json.loads(state_path.read_text())
    if not state.get('action_alignment_v2',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',56)+3
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',236558)+policy['format_warmup_steps']+2*policy['stages']*policy['steps_per_stage']
    state.update(phase='action_alignment_v2_complete',all_own_jobs_complete=True,
                 active_experiment=None,next_action='Assess action-alignment findings; no automatic device deployment.')
    state['action_alignment_v2']={'completed':True,'report':str(HERE/'ACTION_ALIGNMENT_V2_RESULTS.md'),
                                'selected_artifact':str(root/'export/selected-research/model.mka'),
                                'summary':json.loads((root/'summary.json').read_text())}
    write(state_path,state)
    print(json.dumps({'completed':True,'selected_arm':selection['selected_arm'],'release_eligible':selection['release_eligible'],
                      'tools':{arm:summary[arm]['tools']['passed']for arm in ARMS},'report':str(HERE/'ACTION_ALIGNMENT_V2_RESULTS.md')}),flush=True)


if __name__=='__main__':main()
