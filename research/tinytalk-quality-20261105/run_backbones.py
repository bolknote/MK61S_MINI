#!/usr/bin/env python3
"""Adapt two fully pretrained language cores to exactly the existing Q4/vocabulary budget."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time
from run_remote import ROOT,container,command,status


def main():
    deadline=time.monotonic()+900
    while not(ROOT/'downloads-complete.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Backbone download')
        time.sleep(3)
    status('pruning_fully_pretrained_backbones')
    def transplant(item):
        gpu,label=item
        command(container(gpu,'transplant_backbone.py','--source','download-'+label,'--tokenizer','/previous',
                          '--data','seed-data','--output',label+'-init'),label+'-init.log')
    with ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(transplant,enumerate(['plain','instruct'])))
    old=ROOT.parent/'round5/language-data';data=ROOT/'language-data';data.mkdir()
    previous=json.loads((ROOT.parent/'round5/tagged-init/tokenizer.json').read_text())
    current=json.loads((ROOT/'plain-init/tokenizer.json').read_text())
    assert previous['model']==current['model'],'Ordinary BPE token IDs must be identical'
    assert (ROOT/'plain-init/tokenizer.json').read_bytes()==(ROOT/'instruct-init/tokenizer.json').read_bytes()
    manifest=json.loads((old/'manifest.json').read_text())
    original_tokenizer_sha=manifest['tokenizer_sha256']
    manifest['tokenizer_sha256']=hashlib.sha256((ROOT/'plain-init/tokenizer.json').read_bytes()).hexdigest()
    manifest['vocab_size']=16406
    manifest['compatibility']={'original_tokenizer_sha256':original_tokenizer_sha,'ordinary_bpe_model_exactly_equal':True,
            'only_added_private_tags_differ':True,'reencoded':False}
    for name in ['train.u16','validation.u16']:os.link(old/name,data/name)
    (data/'manifest.json').write_text(json.dumps(manifest,indent=2))
    status('language_adaptation',token_exposures_per_backbone=50000000,qat=True)
    def language(item):
        gpu,label=item
        command(container(gpu,'pretrain_language.py','--model',label+'-init','--output',label+'-language',
                          '--tokens','50000000','--batch-size','128','--lr','2e-5','--eval-every','1000'),label+'-language.log')
        command(container(gpu,'refresh_intents.py','--model',label+'-language/best','--output',label+'-chat-init'),label+'-refresh.log')
    with ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(language,enumerate(['plain','instruct'])))
    status('language_backbones_ready_for_conversation_training')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        status('failed',error=f'{type(error).__name__}: {error}');raise
