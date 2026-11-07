from pathlib import Path
import json,subprocess,struct,hashlib,os
B=Path(__file__).resolve().parent;R=B.parents[2];O=B/'regression20-int8-bitplanes';O.mkdir()
# Diagnostic added after the quality gate failed: isolate activation arithmetic from lossless layout repacking.
with (O/'results.jsonl').open('x') as f,(O/'progress.log').open('x') as log:
 p=subprocess.run([str(B/'evaluator'),str(R/'.build/mk61ai/v3/models/full-lut/MODEL.MKA'),str(B/'regression20.tsv'),'--arithmetic=int8','--linear=sram'],stdout=f,stderr=log,timeout=120)
assert p.returncode==0
x=[json.loads(s) for s in (O/'results.jsonl').read_text().splitlines()];y=[json.loads(s) for s in (B/'regression20-int8/results.jsonl').read_text().splitlines()]
assert len(x)==len(y)==20
assert all({k:v for k,v in a.items() if k!='elapsed_us'}=={k:v for k,v in c.items() if k!='elapsed_us'} for a,c in zip(x,y))
(O/'report.json').write_text(json.dumps(dict(status='PASS',scope='supplemental after gate failure; not selection or retraining',identical_functional_rows=20,excluded_fields=['elapsed_us'],regression_independent_of_layout=True),indent=2)+'\n')
h=struct.unpack('<32I',(R/'.build/mk61ai/v3/models/full-lut/MODEL.MKA').read_bytes()[:128]);layers,hidden,intermediate,heads,kv_heads,head_dim,vocab,context,bos,eos=h[4:14]
columns=max(hidden,intermediate,heads*head_dim);floats=3*hidden+2*heads*head_dim+2*kv_heads*head_dim+2*intermediate+context
raw=max(4*max(hidden,head_dim),columns*9//16)
lookup=16*columns
needed=4*floats+raw+columns+8*(columns//32)+lookup+16*(columns*9//16)+8*4+16
before=max(needed,6*2048);hypothetical=max(needed-lookup,6*2048)
result=dict(status='CALCULATION_ONLY_NOT_IMPLEMENTED',quality_gate='FAIL',lut_removed=False,default='LUT_FLOAT32',model_context=context,vocab=vocab,workspace_bytes=before,lut_reserved_bytes=lookup,hypothetical_int8_only_workspace_bytes=hypothetical,hypothetical_sram_saving_bytes=before-hypothetical,kv_bytes_per_token=8*layers*kv_heads*head_dim,kv_total_bytes=8*layers*kv_heads*head_dim*context,kv_location='external PSRAM',workspace_location='internal SRAM',automatic_context_extension=False,note='Removing SRAM lookup does not enlarge external KV allocation, stored RoPE table, model header context, or training length.')
(B/'memory-analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
