#!/usr/bin/env python3
"""Measure the untouched original TinyTalk Q4 on the same newly opened final audit."""
import argparse
import json
from pathlib import Path
from common import core, load_model, quantize
from evaluate import assess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model',default='/original')
parser.add_argument('--suite',default='reserved-audit2/test.jsonl')
parser.add_argument('--scenarios',default='reserved-audit2/scenarios.json')
parser.add_argument('--selection',default='selection.json')
parser.add_argument('--output',default='baseline-audit2')
parser.add_argument('--device',default='cuda')
parser.add_argument('--seed',type=int,default=84119)
args=parser.parse_args()
selection=json.loads(Path(args.selection).read_text())
assert selection['selected']['goal_met'], 'Freeze a qualified candidate before opening this comparison'
output=Path(args.output);assert not output.exists();output.mkdir(parents=True)
model,tokenizer,device=load_model(args);model.eval().requires_grad_(False)
metadata=quantize.export(model,output/'model.ttq4',{'model':'TheREZOR/TinyTalk','source_sha256':core.digest(Path(args.model)/'model.safetensors')})
quantize.roundtrip(model)
expected={name:p.detach().clone()for name,p in model.named_parameters()}
quantize.restore(model,output/'model.ttq4')
error=max(float((expected[name]-p).abs().max())for name,p in model.named_parameters());assert error==0
del expected
result=assess(model,tokenizer,device,core.read_rows(args.suite),None,output/'grade-cache','baseline',json.loads(Path(args.scenarios).read_text()))
report={'model':'Untouched original TinyTalk after real Q4 packing','parameters':sum(p.numel()for p in model.parameters()),
        'raw_sha256':core.digest(Path(args.model)/'model.safetensors'),'packed_sha256':metadata['file_sha256'],
        'packed_reload_max_abs_error':error,'runtime_context':getattr(model.config,'tinytalk_runtime_context',256),
        'test_sha256':core.digest(args.suite),'scenarios_sha256':core.digest(args.scenarios),'result':result}
core.save(output/'audit.json',report)
print(json.dumps({'direct':result['direct']['pass_rate'],'context':result['context_pass_rate'],
                  'multi_turn':result['multi_turn']['pass_rate'],'malformed':result['malformed']}),flush=True)
