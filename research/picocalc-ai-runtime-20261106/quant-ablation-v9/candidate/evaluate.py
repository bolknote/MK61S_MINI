from pathlib import Path
import sys,json,time,hashlib,subprocess,os,concurrent.futures
B=Path(__file__).resolve().parent;sys.path.insert(0,str(B/'runtime'))
import full_isa_vm
full_isa_vm.ROOT=B/'emulator';full_isa_vm.REPO=Path('/Users/bolk/Projects/MK61S_MINI')
from full_isa_vm import FullVM,check_task
from hf_runtime import Session,prompt
from ha_protocol import assemble,parse_call,encode,constants
from engine import Engine

def read(name):return [json.loads(s)for s in (B/'cases'/name).read_text().splitlines()if s.strip()]
def clean(task):
 t={k:task[k]for k in ['id','task','angle','constants','max_commands','max_frames']if k in task}
 t['public_tests']=[{'segments':[{'inputs':seg['inputs']}for seg in c['segments']]}for c in task['public_tests']]
 return t

def grade(vm,body,task):
 if body is None:return False,None
 try:
  code=assemble(body,task.get('constants')or constants(task['task']),'asm')
  return bool(check_task(vm,code,task)['pass']),code
 except (ValueError,ArithmeticError,RuntimeError,TypeError):return False,None

def worker(mode):
 out=B/('run-'+mode);out.mkdir();vm=FullVM();engine=Engine(mode);started=time.monotonic();count=0
 with (out/'results.jsonl').open('x') as f:
  def save(row):
   nonlocal count
   f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n');f.flush();count+=1
   if count%25==0:print(mode,'completed',count,'elapsed',round(time.monotonic()-started,1),flush=True)
  for suite,name in [('fresh282','fresh.jsonl'),('documented648','documented648.jsonl'),('legacy98','legacy-development.jsonl'),('user27','observed-user-reproductions.jsonl')]:
   for task in read(name):
    text=prompt(clean(task),'asm');r=engine.generate(text);body=None;valid=False
    if not r['error']:
     try:
      kind,body=parse_call(r['reply']);valid=kind=='write'
     except (ValueError,ArithmeticError,RuntimeError):pass
    passed,code=grade(vm,body,task)if valid else(False,None)
    save(dict(suite=suite,id=task['id'],passed=passed,valid=valid,code=code,prompt=text,group=task.get('group'),generation=r))
  bank=read('fresh.jsonl');lookup={t['id']:t for t in bank};seeds=read('fresh-tool-seeds.jsonl')
  for suite,items,scratch in [('tools72',seeds,False),('scratch48',seeds[:48],True)]:
   for index,item in enumerate(items):
    task=lookup[item['task_id']];pool=task.get('constants')or constants(task['task'])
    body=None if scratch else encode(item['initial_code'],pool,'asm')
    session=Session(clean(task),'asm',body=body,vm=vm,gate=True)
    if not scratch:
     session.run(0)
     if item.get('pre_run_all'):
      for i in range(1,len(task['public_tests'])):session.run(i)
    history=[];exhausted=False
    for turn in range(6):
     text=session.request();r=engine.generate(text)
     if r['error']:
      history.append(dict(kind='model_error',prompt=text,generation=r));exhausted=True;break
     kind=session.apply(r['reply']);history.append(dict(session.history[-1],prompt=text,generation=r))
     if session.finished:break
    correct,code=grade(vm,session.body,task)
    save(dict(suite=suite,id=f'{index}:{task["id"]}',task_id=task['id'],passed=bool(correct and session.finished),program_correct=correct,finished=session.finished,false_done=bool(session.finished and not correct),initially_correct=False if scratch else item['intentionally_correct'],code=code,done_attempts=session.done_attempts,done_rejections=session.done_rejections,model_error=exhausted,history=history))
 rows=[json.loads(x)for x in(out/'results.jsonl').read_text().splitlines()];assert len(rows)==1175
 suites={}
 for suite in dict.fromkeys(x['suite']for x in rows):
  xs=[x for x in rows if x['suite']==suite];suites[suite]=dict(total=len(xs),passed=sum(x['passed']for x in xs),false_done=sum(x.get('false_done',False)for x in xs),model_errors=sum(bool(x.get('generation',{}).get('error'))or x.get('model_error',False)for x in xs),valid=sum(x.get('valid',True)for x in xs))
 report=dict(mode=mode,suites=suites,total=len(rows),duration_seconds=time.monotonic()-started,pid=os.getpid(),hidden_references_in_runtime=False)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

def main():
 manifest=json.loads((B/'manifest.json').read_text())
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 assert all(sha(B/p)==h for p,h in manifest['source_pins'].items());assert sha(B/'quality-probe.dylib')==manifest['library_sha256']
 compat=json.loads((B/'compatibility.json').read_text());assert len(compat)==26 and all(x['matched']for x in compat)
 FullVM() # Build and qualify the one frozen emulator before parallel readers.
 (B/'evaluation-plan.json').write_text(json.dumps(dict(status='FROZEN_BEFORE_SCORES',modes=['lut-fp32','int8','swar-int8'],rows_per_mode=1175,strict_nonregression=True,max_worker_seconds=1800,source='harness-debug-v3/selected-budget',actual_model_sha256=manifest['model_mka_sha256']),indent=2)+'\n')
 def launch(mode):
  with(B/(mode+'.log')).open('x')as log:
   p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',mode],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
  (B/(mode+'-process.json')).write_text(json.dumps(dict(reaped=True,exit_code=p.returncode))+'\n')
  if p.returncode:raise RuntimeError(mode+' worker failed')
 with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(launch,['lut-fp32','int8','swar-int8']))
 rows={mode:[json.loads(x)for x in(B/('run-'+mode)/'results.jsonl').read_text().splitlines()]for mode in ['lut-fp32','int8','swar-int8']}
 lookup=lambda a:{(x['suite'],x['id']):x for x in a}
 base=lookup(rows['lut-fp32']);integer=lookup(rows['int8']);swar=lookup(rows['swar-int8']);assert base.keys()==integer.keys()==swar.keys()
 lost=[list(k)for k,x in base.items()if x['passed']and not integer[k]['passed']];gained=[list(k)for k,x in integer.items()if x['passed']and not base[k]['passed']]
 def function(row):
  s=json.loads(json.dumps(row))
  for r in [s.get('generation',{}),*[h.get('generation',{})for h in s.get('history',[])]]:r.pop('reused',None)
  return s
 matches=[k for k in integer if function(integer[k])==function(swar[k])]
 false0=sum(x.get('false_done',False)for x in base.values());false1=sum(x.get('false_done',False)for x in integer.values())
 gate=not lost and false1<=false0
 report=dict(status='PASS_NONREGRESSION_GATE'if gate else'FAIL_NONREGRESSION_GATE',model=manifest['model'],model_sha256=manifest['model_mka_sha256'],source_model_packet_sha256=manifest['model_packet_sha256'],total_per_mode=1175,lost=lost,gained=gained,baseline_false_done=false0,int8_false_done=false1,swar_exact_functional_matches=len(matches),swar_mismatches=[list(k)for k in integer if k not in matches],default_switch_allowed=gate,hardware_io=0,training=0,suites={mode:json.loads((B/('run-'+mode)/'report.json').read_text())['suites']for mode in rows})
 (B/'paired-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
 if '--worker'in sys.argv:worker(sys.argv[-1])
 else:main()
