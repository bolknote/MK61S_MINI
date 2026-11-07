"""One pre-SGD rebuild after compacting actual, non-oracle observations."""
import json
import shutil
from hd_common import ROOT,read,sha,write
from hd_tools import lessons
from full_isa_vm import FullVM
from tasks import save_jsonl


def main():
    assert not(ROOT/'launch.json').exists()and not(ROOT/'prepared.json').exists()
    old=ROOT/'data-frozen-before-compact-feedback.json'
    if not old.exists():shutil.copyfile(ROOT/'data-frozen.json',old)
    vm=FullVM();lookup={t['id']:t for t in read(ROOT/'train.jsonl')};rows=[]
    for i,item in enumerate(read(ROOT/'tool-episodes.jsonl')):
        values=lessons(lookup[item['task_id']],item,vm)
        for row in values:row['id']+=f':episode{i}'
        rows+=values
    save_jsonl(ROOT/'tool-lessons.jsonl',rows)
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    frozen['files']['tool-lessons.jsonl']=sha(ROOT/'tool-lessons.jsonl')
    frozen['compact_feedback_rebuilt_before_SGD']=True
    write(ROOT/'data-frozen.json',frozen);print(json.dumps({'lessons':len(rows),'before_SGD':True}),flush=True)


if __name__=='__main__':main()
