"""Pre-SGD addition: compositions that consume current X rather than memory."""
import json
import random
import shutil

from hf_common import ROOT,read,sha,write
from hf_tools import seed,lessons
from ha_data import verified
from full_isa_math import UNARY,literal
from full_isa_vm import FullVM
from natural_data import NAMES
from tasks import save_jsonl


def generate(vm,split,count,seed_):
    rng=random.Random(seed_);out=[];seen=set()
    numbers=['0','1','-1','.125','-.875','2','3','.5']if split=='train'else['1','.25','-.5','4']if split=='validation'else['1','.375','-.625','5']
    while len(out)<count:
        c=rng.choice(numbers);op=rng.choice(['square','abs','neg','sin','sqrt']);shape=rng.randrange(3);angle=rng.choice(['RAD','DEG','GRAD'])
        if shape==0:
            expr=[op,['+','R0',{'constant':c}]];code=literal(c)+[0x10,UNARY[op],0x50]
            text=f'Вычисли {NAMES[op]} от (X+{c}).'
            if op=='square'and(split=='train'and rng.random()<.5):text=f'Вычисли (X+{c})*(X+{c}).'
        else:
            binary='-'if shape==1 else'*';expr=[binary,[op,'R0'],{'constant':c}]
            code=[UNARY[op],*literal(c),0x11 if shape==1 else 0x12,0x50]
            text=f'Вычисли {NAMES[op]} текущего X, затем '+('вычти 'if shape==1 else'умножь результат на ')+c+'.'
        if split=='validation':text='Аргумент находится в стеке X. '+text
        elif split=='fresh':text='Число уже в X; составь программу. '+text
        if(angle,text)in seen:continue
        t=verified(vm,expr,text,f'hd-{split}:stack-compose:{len(out)}','composition',split,angle,rng,code=code,source='X')
        if t:t['debug_category']='stack_composition';out.append(t);seen.add((angle,text))
    return out


def main():
    assert not(ROOT/'launch.json').exists()and not(ROOT/'prepared.json').exists()
    if(ROOT/'stack-composition-added.json').exists():return
    shutil.copyfile(ROOT/'data-frozen.json',ROOT/'data-frozen-before-stack-composition.json')
    vm=FullVM();episodes=read(ROOT/'tool-episodes.jsonl');tool_rows=read(ROOT/'tool-lessons.jsonl')
    for split,count,seed_ in [('train',120,6120771),('validation',20,6120772),('fresh',40,6120773)]:
        added=generate(vm,split,count,seed_);rows=read(ROOT/(split+'.jsonl'))+added;save_jsonl(ROOT/(split+'.jsonl'),rows)
        if split=='train':
            light=read(ROOT/'sft-light.jsonl')
            for i,t in enumerate(added):
                small={k:v for k,v in t.items()if k not in ['public_tests','hidden_tests','expression']}
                small['public_tests']=[{'segments':[{'inputs':s['inputs']}for s in case['segments']]}for case in t['public_tests']]
                light.append(small)
                for correct in [False,True]:
                    item=seed(t,vm,len(episodes)+30000,correct=correct);episodes.append(item)
                    values=lessons(t,item,vm)
                    for row in values:row['id']+=':stack-episode'+str(len(episodes))
                    tool_rows+=values
            save_jsonl(ROOT/'sft-light.jsonl',light)
        else:
            items=read(ROOT/(split+'-tool-seeds.jsonl'))
            for i,t in enumerate(added[:4 if split=='validation'else 12]):items.append(seed(t,vm,len(items)+30000,correct=i%4==0))
            save_jsonl(ROOT/(split+'-tool-seeds.jsonl'),items)
            if split=='validation':save_jsonl(ROOT/'development.jsonl',rows)
    save_jsonl(ROOT/'tool-episodes.jsonl',episodes);save_jsonl(ROOT/'tool-lessons.jsonl',tool_rows)
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n in frozen['files']:frozen['files'][n]=sha(ROOT/n)
    frozen.update(counts={s:len(read(ROOT/(s+'.jsonl')))for s in ['train','validation','fresh']},episodes=len(episodes),tool_lessons=len(tool_rows),
                  current_X_compositions_added_before_SGD=True)
    write(ROOT/'data-frozen.json',frozen);write(ROOT/'stack-composition-added.json',{'before_SGD':True,'counts':frozen['counts']})
    print(json.dumps({'counts':frozen['counts'],'episodes':len(episodes),'lessons':len(tool_rows)}),flush=True)


if __name__=='__main__':main()
