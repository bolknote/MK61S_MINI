"""Prepare one offline dataset-aggregation pass and a separately seeded exam."""
import json
import random
import shutil

from hf_common import ROOT,PREVIOUS,INITIAL,INITIAL_PACKET,read,sha,write
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from hd_data import stops
from hd_x_data import generate as x_tasks
from hf_tools import seed
from full_isa_vm import FullVM
from tasks import save_jsonl


def fresh_tasks():
    vm=FullVM();fresh=[]
    for fn,n,s in [(basic_tasks,40,61207901),(composite_tasks,40,61207902),(algorithm_tasks,30,61207903),
                   (boundary_tasks,40,61207904),(hard_tasks,80,61207905)]:
        for t in fn(vm,'fresh',n,s):t['id']='hf-fresh:'+str(len(fresh));fresh.append(t)
    for t in x_tasks(vm,'fresh',40,61207906):t['id']='hf-fresh:'+str(len(fresh));fresh.append(t)
    forms=['Никаких расчётов: нужен немедленный программный останов С/П.',
           'В начале исполнения поставь команду С/П и сохрани состояние.',
           'Сделай остановку на С/П до любых других действий.',
           'Требуется первая инструкция С/П, изменять числа нельзя.']
    for i,t in enumerate(stops(vm,'fresh',random.Random(61207907))):
        t['id']='hf-fresh:'+str(len(fresh));t['task']=forms[i%4];t['fresh_template_family']='hf_stop_newwording';fresh.append(t)
    return fresh


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-stage.json').exists():return
    names=['catalog.json','output-token-ids.json','isa-audit.jsonl','isa-development.jsonl','legacy-development.jsonl',
           'observed-user-reproductions.jsonl','observed-previous-language.jsonl','retention-floors.json','observed-retention.jsonl',
           'observed-ablation.jsonl','train.jsonl','validation.jsonl','development.jsonl','sft-light.jsonl','tool-episodes.jsonl',
           'tool-lessons.jsonl','validation-tool-seeds.jsonl']
    for name in names:shutil.copyfile(PREVIOUS/name,ROOT/name)
    shutil.copytree(PREVIOUS/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    path=ROOT/'fresh.jsonl'
    fresh=read(path)if path.exists()else fresh_tasks()
    vm=FullVM()
    save_jsonl(ROOT/'fresh.jsonl',fresh)
    rng=random.Random(61207908);grouped={}
    for t in fresh:grouped.setdefault(t['group'],[]).append(t)
    items=[]
    for values in grouped.values():
        rng.shuffle(values)
        for t in values[:8]:items.append(seed(t,vm,len(items)+40000,correct=len(items)%4==0))
    save_jsonl(ROOT/'fresh-tool-seeds.jsonl',items)
    # Mining is restricted to training seeds, never validation or fresh cases.
    lookup={t['id']:t for t in read(ROOT/'train.jsonl')};by_group={}
    for item in read(ROOT/'tool-episodes.jsonl'):by_group.setdefault(lookup[item['task_id']]['group'],[]).append(item)
    mining=[]
    for values in by_group.values():rng.shuffle(values);mining+=values[:36]
    save_jsonl(ROOT/'mining-seeds.jsonl',mining)
    policy={'steps_each':2000,'validation_interval':500,'effective_batch':128,'context':1024,'lr':1e-5,
            'embedding_lr_factor':.5,'warmup_updates':80,'weight_decay':.01,'learning_rate_scale':{'safe':.5,'active':1.},
            'quotas':{'dagger':40,'tool':16,'legacy':32,'composition':12,'basic':8,'algorithm':4,'primitive':10,'stop':2,'language':4},
            'max_tool_turns':6,'source':'harness-debug-v2/selected-budget',
            'aggregation':'one offline pass on the fixed previous student, only training trajectories',
            'correction_of_wrong_DONE':'full WRITE of verified reference program; no runtime oracle',
            'fresh_used_for_selection':False}
    write(ROOT/'policy.json',policy)
    files=names+['fresh.jsonl','fresh-tool-seeds.jsonl','mining-seeds.jsonl','policy.json']
    stage={'files':{n:sha(ROOT/n)for n in files},'initial_master_sha256':sha(INITIAL/'model.safetensors'),
      'initial_packet_sha256':sha(INITIAL_PACKET),'counts':{'train':len(lookup),'validation':len(read(ROOT/'validation.jsonl')),'fresh':len(fresh)},
      'mining_seeds':len(mining),'fresh_is_newly_seeded_synthetic_not_human_benchmark':True,'before_optimizer_updates':True}
    initial=json.loads((INITIAL.parent/'manifest.json').read_text())
    stage.update(initial_selected_label=initial['strategy']+'-best',initial_selected_step=initial['selected_step'])
    write(ROOT/'data-stage.json',stage);print(json.dumps({k:v for k,v in stage.items()if k!='files'}),flush=True)


if __name__=='__main__':main()
