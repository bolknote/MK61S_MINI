"""Package the actual audited packets, retaining learned Q2 amplitudes."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile

import torch
from transformers import AutoModelForCausalLM

from lowbit import MAGIC
from native_quant import attach, restore_scales, export, plain_master
from tasks import BUILD


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def packet(path):
    data=Path(path).read_bytes()
    assert data[:8]==MAGIC
    length=struct.unpack('<I',data[8:12])[0]
    return json.loads(data[12:12+length]),data[12+length:]


def main():
    root=BUILD/'native-mixed-v1'
    assert json.loads((root/'complete.json').read_text())['completed']
    winner=json.loads((root/'winner-before-fresh.json').read_text())
    assert not winner['fresh_opened_for_selection']
    torch.set_num_threads(2)
    histories={arm:json.loads((root/(arm+'-sft/training.json')).read_text())for arm in ['q4','mixed']}
    assert histories['q4']['actual_sample_counts']==histories['mixed']['actual_sample_counts']
    assert histories['q4']['optimizer_steps_by_context']==histories['mixed']['optimizer_steps_by_context']
    manifests={}
    for arm in ['q4','mixed']:
        source=root/(arm+'-sft/best'); actual=root/(arm+'-final.mkqb')
        result=json.loads((root/(arm+'-fresh.json')).read_text())
        assert sha(actual)==result['packed']['sha256']
        assert (root/'winner-before-fresh.json').stat().st_mtime<=actual.stat().st_mtime
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False)
        attach(model,arm);restore_scales(model,source)
        header,payload=packet(actual)
        with tempfile.TemporaryDirectory()as tmp:
            repacked=Path(tmp)/'repacked.mkqb';export(model,repacked,arm)
            again,again_payload=packet(repacked)
            assert payload==again_payload and header['tensors']==again['tensors'], 'Export changed audited weights/scales'
        folder=root/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,folder/'hf',dirs_exist_ok=True)
        shutil.copyfile(actual,folder/'model.mkqb')
        raw=plain_master(model);config=raw.config
        token_bytes=2*config.num_hidden_layers*config.num_key_value_heads*config.head_dim*2
        training=json.loads((root/(arm+'-sft/training.json')).read_text())
        manifest={
            'arm':arm,'format':arm,'parameters':sum(p.numel()for p in raw.parameters()),
            'packed_bytes':actual.stat().st_size,'payload_bytes':len(payload),'packed_sha256':sha(actual),
            'payload_sha256':hashlib.sha256(payload).hexdigest(),
            'checkpoint_files':{str(p.relative_to(source)):sha(p)for p in source.rglob('*')if p.is_file()},
            'learned_scale_count':result['packed']['learned_group_scale_count'],
            'audited_packet_copied_without_requantization':True,'reexport_payload_identical':True,
            'selection_file_precedes_audited_packet':True,
            'best_step':training['best_step'],'validation_key':training['best_key'],
            'model_context':config.max_position_embeddings,'fp16_kv_bytes_per_token':token_bytes,
            'fp16_kv_bytes':{str(n):n*token_bytes for n in [512,1024,2048]},
            'standard_mk61':{'program_bytes':105,'registers':'R0..R9,Ra..Re','extensions_enabled':False},
            'host_evaluation_activations_and_kv':'FP32','native_device_measured':False,
            'fresh_used_for_selection':False,'source_model':'akanemind/Flourish-3M',
            'source_revision':'33b38dfec202c39c3698f7f2d1a9933a34a2de1a',
            'original_weights_sha256':'3bd64747ce1d4709f58d1522c95e390fd2dc5b1bc21b7e02ab18a99e9c676990',
            'warning':'This is an expanded and re-trained experimental model, not a native-device benchmark.'}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        manifests[arm]=manifest
    selected=root/'export/selected-budget'
    shutil.copytree(root/'export'/winner['arm'],selected,dirs_exist_ok=True)
    provenance=root/'provenance';provenance.mkdir(exist_ok=True)
    for relative in ['initial/manifest.json','initial-active/manifest.json','language/manifest.json',
                     'teacher/manifest.json','course/manifest.json']:
        path=root/relative
        if path.exists():shutil.copyfile(path,provenance/relative.replace('/','-'))
    result={'selected_arm':winner['arm'],'selection':winner,'exports':manifests,
            'matched_sample_and_context_counts_verified':True,
            'fresh_used_for_selection':False,'native_device_measured':False}
    (root/'final-export.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'selected':winner['arm'],'exports':{a:m['packed_sha256']for a,m in manifests.items()}}),flush=True)


if __name__=='__main__':main()
