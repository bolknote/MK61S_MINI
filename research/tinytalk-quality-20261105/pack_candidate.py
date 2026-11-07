#!/usr/bin/env python3
"""Pack any supported candidate with its actual backbone provenance and verify reload."""
import argparse
from pathlib import Path
from common import core,load_model,quantize

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--report',required=True)
parser.add_argument('--device',default='cpu')
parser.add_argument('--seed',type=int,default=7731)
args=parser.parse_args()
model,tokenizer,device=load_model(args);model.eval().requires_grad_(False)
backbone=getattr(model.config,'tinytalk_backbone',{})
origin={'model':backbone.get('repository','TheREZOR/TinyTalk'),'revision':backbone.get('revision','61c79ad139344cdd344a687b35fa8f1c52326154'),
        'source_sha256':core.digest(Path(args.model)/'model.safetensors'),'recipe':'compact conversational fine-tuning with actual Q4 selection'}
metadata=quantize.export(model,args.output,origin);quantize.roundtrip(model)
expected={name:p.detach().clone()for name,p in model.named_parameters()}
quantize.restore(model,args.output)
error=max(float((expected[name]-p).abs().max())for name,p in model.named_parameters());assert error==0
metadata.update(roundtrip_max_abs_error=error,packed_reload_verified=True,native_device_runtime_implemented=False)
quantize.copy_notices(args.model,Path(args.output).parent);core.save(args.report,metadata)
print({'parameters':metadata['parameters'],'file_bytes':metadata['file_bytes'],'sha256':metadata['file_sha256'],'exact_reload':True},flush=True)
