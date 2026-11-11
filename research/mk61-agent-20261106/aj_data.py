"""Reuse the sealed v1 course while fixing the proven RUN-00 sampling defect."""
import json
import shutil
from pathlib import Path
from aj_common import ROOT,read,write,sha


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    source=ROOT.parent/'completion-retention-v1';old=json.loads((source/'data-frozen.json').read_text())
    for name,digest in old['files'].items():
        assert sha(source/name)==digest,name
        shutil.copyfile(source/name,ROOT/name)
    shutil.copytree(source/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy=json.loads((ROOT/'policy.json').read_text());policy['run_sampling_indices']=[0,1,2,3]
    policy['valid_RUN_00_omission_corrected']=True
    write(ROOT/'policy.json',policy)
    files={name:sha(ROOT/name)for name in old['files']}
    files['correction-intent.json']=sha(ROOT/'correction-intent.json')
    frozen={**old,'files':files,'reference_course_sha256':sha(source/'data-frozen.json'),
      'all_task_and_label_files_bit_identical_to_v1':True,'only_change':'All available RUN indices, including 00, enter sampling',
      'fresh_exam_results_not_used_to_design_correction':True}
    write(ROOT/'data-frozen.json',frozen)
    print(json.dumps({'frozen':True,'same_tasks_and_labels':True,'RUN_indices':policy['run_sampling_indices']}),flush=True)


if __name__=='__main__':main()
