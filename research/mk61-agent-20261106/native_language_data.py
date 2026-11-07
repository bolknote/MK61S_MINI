"""Pinned Russian shards, document-hash splits and a tokenizer-matched uint16 stream."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

from tasks import BUILD

ROOT=BUILD/'native-mixed-v1'


def request(url):
    with urllib.request.urlopen(url,timeout=90)as f:return json.load(f)


def main():
    ROOT.mkdir(parents=True,exist_ok=True);out=ROOT/'language';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():print('Language data complete');return
    deps=ROOT/'pydeps';sys.path.insert(0,str(deps))
    if importlib.util.find_spec('pyarrow')is None:
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(deps),'pyarrow==21.0.0'],check=True)
        importlib.invalidate_caches()
    import pyarrow.parquet as pq
    import numpy as np
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False)
    sources=[];started=time.monotonic();counts={'train':0,'validation':0};documents={'train':0,'validation':0}
    streams={s:(out/(s+'.u16')).open('wb')for s in counts}
    index=(out/'documents.jsonl').open('w');seen=set()
    for repo,folder,license_name in [('wikimedia/wikipedia','20231101.ru','CC-BY-SA-3.0 / GFDL'),('deepvk/cultura_ru_edu',None,'Apache-2.0')]:
        meta=request('https://huggingface.co/api/datasets/'+repo);revision=meta['sha']
        files=[x['rfilename']for x in meta['siblings']if x['rfilename'].endswith('.parquet')and'train'in Path(x['rfilename']).name and(folder is None or x['rfilename'].startswith(folder+'/'))]
        files.sort();chosen=files[0]
        source_dir=out/'sources';source_dir.mkdir(exist_ok=True);path=source_dir/(repo.split('/')[0]+'-'+Path(chosen).name)
        url='https://huggingface.co/datasets/'+repo+'/resolve/'+revision+'/'+chosen+'?download=true'
        if not path.exists():
            print(json.dumps({'downloading':repo,'file':chosen}),flush=True)
            temp=path.with_suffix('.part')
            with urllib.request.urlopen(url,timeout=180)as remote,temp.open('wb')as local:
                while block:=remote.read(4*1024**2):local.write(block)
            temp.replace(path)
        before=counts.copy();source_docs=0;limit={'train':before['train']+50000000,'validation':before['validation']+131072}
        parquet=pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=128,columns=['text']):
            texts=batch.column(0).to_pylist()
            kept=[]
            for text in texts:
                if not isinstance(text,str):continue
                text=re.sub(r'\s+',' ',text).strip();identity=hashlib.sha256(text.encode()).hexdigest()
                if identity in seen or len(text)<200:continue
                letters=re.findall('[a-zа-яё]',text,re.I);cyrillic=len(re.findall('[а-яё]',text,re.I))
                if cyrillic/max(1,len(letters))<.6:continue
                split='validation'if int(identity[:8],16)%100==0 else'train'
                if counts[split]>=limit[split]:continue
                seen.add(identity);kept.append((text,identity,split))
            encoded=tokenizer([x[0]for x in kept],add_special_tokens=False)['input_ids']if kept else[]
            for (text,identity,split),ids in zip(kept,encoded):
                ids=(ids+[tokenizer.eos_token_id])[:limit[split]-counts[split]]
                if len(ids)<32:continue
                np.asarray(ids,dtype='<u2').tofile(streams[split]);counts[split]+=len(ids);documents[split]+=1;source_docs+=1
                index.write(json.dumps({'sha256':identity,'source':repo,'split':split,'tokens':len(ids)})+'\n')
            if source_docs and source_docs%500<128:
                value={'phase':'tokenizing','source':repo,'tokens':counts,'documents':documents,'seconds':time.monotonic()-started}
                (out/'status.json').write_text(json.dumps(value)+'\n');print(json.dumps(value),flush=True)
            if all(counts[s]>=limit[s]for s in counts):break
        sources.append({'repository':repo,'revision':revision,'file':chosen,'license':license_name,'url':url,
          'file_bytes':path.stat().st_size,'file_sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),
          'tokens':{s:counts[s]-before[s]for s in counts}})
    for stream in streams.values():stream.close()
    index.close()
    if counts['train']<50000000 or counts['validation']<131072:raise ValueError('Insufficient Russian language data')
    manifest={'sources':sources,'tokens':counts,'documents':documents,'split':'Whole normalized document SHA256 modulo100; validation bucket0',
      'same_document_never_both_splits':True,'tokenizer_sha256':hashlib.sha256((BUILD/'flourish-original/tokenizer.json').read_bytes()).hexdigest(),
      'files':{s:hashlib.file_digest((out/(s+'.u16')).open('rb'),'sha256').hexdigest()for s in counts},
      'prior_original_model_pretraining_may_include_these_public_documents':True,'seconds':time.monotonic()-started}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','tokens':counts})+'\n');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
