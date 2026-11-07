from pathlib import Path
import json,hashlib,subprocess,concurrent.futures
B=Path(__file__).resolve().parent;R=B.parents[2];S=R/'.build/mk61ai/swar-v5/source';P=B/'eval-swar.cpp'
t=(B/'eval.cpp').read_text();old='      else if (!std::strcmp(arithmetic_name, "fp32")) arithmetic = Arithmetic::FLOAT32;'
assert old in t
t=t.replace(old,'      else if (!std::strcmp(arithmetic_name, "swar-int8")) arithmetic = Arithmetic::SWAR_INT8;\n'+old);P.write_text(t)
sources=['mk61_ai_model.cpp','mk61_ai_linear.cpp','mk61_ai_tokenizer.cpp','mk61_ai_harness.cpp','mk61_ai_tools.cpp','mk61_ai_agent.cpp','mk61_ai_grammar.cpp','mk61emu_core.cpp']
E=B/'evaluator-swar'
subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-DMK61_CORE_STANDALONE=1','-DMK61_CORE_HOT_TABLES_IN_SRAM=0','-I'+str(S/'code'),*[str(S/'code'/s) for s in sources],str(B/'kernels.o'),str(P),'-o',str(E)],check=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=dict(scope='User requested SWAR+INT8 quality extension after original gate failed; no tuning or selection',executable_sha256=sha(E),base_executable_sha256=sha(B/'evaluator'),source_change='CLI parser only: allow arithmetic=swar-int8',datasets={n:sha(B/(n+'.jsonl')) for n in ['regression20','fresh64']},expected='same exact functional results as INT8; all84 rows count')
(B/'swar-extension-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def run(label):
 out=B/(label+'-swar-int8');out.mkdir()
 with (out/'results.jsonl').open('x') as f,(out/'progress.log').open('x') as log:
  p=subprocess.run([str(E),str(R/'.build/mk61ai/swar-v5/MODEL-NIBBLE.MKA'),str(B/(label+'.tsv')),'--arithmetic=swar-int8','--linear=sram'],stdout=f,stderr=log,timeout=240)
 a=[json.loads(x) for x in (B/(label+'-int8')/'results.jsonl').read_text().splitlines()];b=[json.loads(x) for x in (out/'results.jsonl').read_text().splitlines()]
 assert p.returncode==0 and len(a)==len(b)
 keep=lambda row:{k:v for k,v in row.items() if k not in ['elapsed_us','arithmetic']}
 mismatches=[(x['id'],keep(x),keep(y)) for x,y in zip(a,b) if keep(x)!=keep(y)]
 report=dict(status='PASS_EXACT_FUNCTIONAL_MATCH' if not mismatches else 'MISMATCH',total=len(b),passed=sum(x['passed'] for x in b),passed_examples=sum(x['passed_tests'] for x in b),total_examples=sum(x['tests'] for x in b),valid_replies=sum(x['valid_replies'] for x in b),replies=sum(x['replies'] for x in b),identical_functional_rows=len(a)-len(mismatches),mismatches=mismatches,excluded_fields=['elapsed_us','arithmetic'])
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(label,json.dumps(report,ensure_ascii=False),flush=True);return report
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:reports=dict(zip(['regression20','fresh64'],pool.map(run,['regression20','fresh64'])))
(B/'swar-report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
assert all(r['status']=='PASS_EXACT_FUNCTIONAL_MATCH' for r in reports.values())
