import json
from hf_common import ROOT,read,sha,write


def main():
    if(ROOT/'data-frozen.json').exists():return
    stage=json.loads((ROOT/'data-stage.json').read_text());mining=json.loads((ROOT/'mining.json').read_text())
    for n,d in stage['files'].items():assert sha(ROOT/n)==d
    assert sha(ROOT/'dagger-lessons.jsonl')==mining['lessons_sha256']
    assert sha(ROOT/'mining-rollouts.json')==mining['rollouts_sha256']
    assert stage['initial_packet_sha256']==mining['source_packet_sha256']
    files={**stage['files'],**{n:sha(ROOT/n)for n in ['dagger-lessons.jsonl','mining-rollouts.json','mining.json','data-stage.json']}}
    frozen={**stage,'files':files,'private_core_files':{str(p.relative_to(ROOT/'core-source')):sha(p)for p in(ROOT/'core-source').rglob('*')if p.is_file()},
      'episodes':stage['mining_seeds'],'tool_lessons':len(read(ROOT/'tool-lessons.jsonl')),'dagger_lessons':mining['lessons'],
      'actual_error_episodes':mining['counts']['wrong_DONE'],'near_miss_episodes':0,
      'old_retention_exam_is_now_observed_and_partly_replayed':True,'oracle_answers_in_runtime_feedback':False,
      'offline_aggregation_before_optimizer_updates':True,'mining_source_is_fixed_previous_student':True}
    write(ROOT/'data-frozen.json',frozen);print(json.dumps({'frozen':True,'dagger_lessons':mining['lessons']}),flush=True)


if __name__=='__main__':main()
