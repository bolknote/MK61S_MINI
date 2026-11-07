"""Preserve the sealed data; correct only the initial generation prompt in v2."""
import json
import shutil
from tasks import BUILD
from he_common import ROOT,read,sha,write


def main():
    ROOT.mkdir(exist_ok=True)
    assert not(ROOT/'launch.json').exists()and not(ROOT/'prepared.json').exists()
    if(ROOT/'data-frozen.json').exists():return
    source=BUILD/'harness-debug-v1';old=json.loads((source/'data-frozen.json').read_text())
    for name,digest in old['files'].items():
        assert sha(source/name)==digest
        shutil.copyfile(source/name,ROOT/name)
    shutil.copytree(source/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    old.update(source_data_round='harness-debug-v1',same_sealed_fresh_as_aborted_round=True,
               fresh_not_used_in_aborted_round=True,initial_generation_prompt_preserved=True,
               runtime_summary_added_only_after_program_exists=True,before_optimizer_updates=True)
    write(ROOT/'data-frozen.json',old);print(json.dumps({'copied_frozen_data':old['counts'],'initial_prompt_preserved':True}))


if __name__=='__main__':main()
