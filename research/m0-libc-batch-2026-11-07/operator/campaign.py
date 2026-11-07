"""One Root grant for install, four qualifications, ALL eight and release.

Derive only the exact finite phases explicitly approved by that parent Go.
No independent lease creation, permission assumption or failed-job replay.
"""
import argparse,json,os,sys,time
from pathlib import Path
import controller as c
from device_guard import UID,need,sha,continuous,elapsed,dump
from supervisor import ExistingLease,run_once
HERE=Path(__file__).resolve().parent;D=c.D
def save_new(p,j):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(j,f,indent=2);f.write('\n')
def phase_plan():
    phases=[dict(index=0,scope='fixture-install',action='flash',indexes=[],script='install.py'),dict(index=1,scope='qualification',action='timing',indexes=[0,1,2,3],script='controller.py')]
    for first in range(0,672,16):phases.append(dict(index=len(phases),scope='timing',action='timing',indexes=list(range(first,min(first+16,672))),script='controller.py'))
    phases.append(dict(index=len(phases),scope='release',action='release',indexes=[],script='controller.py'))
    for p in phases:
        folder=D/'physical-phases-001';stem=str(p['index']).zfill(3)
        p.update(maximum_phase_seconds=900,phase_path=str(folder/(stem+'.phase.json')),grant_path=str(folder/(stem+'.grant.json')),output=str(D/'physical-runs-001'/stem))
    return dict(status='HOST_FINITE_ALL_EIGHT_PLAN_REQUIRES_ONE_ROOT_GO',uid=UID,cwd=str(c.ROOT),phases=phases,functions=['strlen','strcmp','strncmp','memcmp','strnlen','strcpy','strncpy','strncat'],timed_jobs=672,failed_job_replays=0)
def precheck(path):
    g=json.loads(path.read_text());need(g['status']=='ROOT_EXPLICIT_M0_LIBC_BATCH_CAMPAIGN_GO' and g['uid']==UID and g['executor']==c.OWNER and g['allow_executor_derive_exact_phases'] is True,'No explicit Root complete-batch Go')
    need(g['reset_and_old_state_discard_authorized'] is True and g['erase_contents_discard_authorized'] is True and g['previous_state_capture'] is False and g['previous_state_restore'] is False and g['RTC_setters']==0,'Unaccepted reset/discard or forbidden restoration')
    need(g['cwd']==str(Path.cwd().resolve())==str(c.ROOT) and g['python']==str(Path(sys.executable).resolve()),'Unbound campaign executable/cwd')
    need(c.source_closure()<=set(g['source_pins']),'Unpinned imported campaign source');c.check_pins(g['source_pins']);c.check_pins(g['artifact_pins'])
    for k in ('plan','template','build','layout','current_image_acceptance','previous_receipt','previous_supervisor','decoder','python','picotool'):
        need(sha(g[k])==g['artifact_pins'][g[k]],'Unbound campaign input '+k)
    plan=json.loads(Path(g['plan']).read_text());need(plan==phase_plan(),'Finite phase list/argv paths changed')
    need([i for p in plan['phases'] if p['scope']=='timing' for i in p['indexes']]==list(range(672)),'Missing/reordered all-eight matrix')
    accepted=json.loads(Path(g['current_image_acceptance']).read_text());t=json.loads(Path(g['template']).read_text())
    need(accepted['status']=='ROOT_ACCEPTED_M0_LIBC_CURRENT_IMAGE' and accepted['uid']==UID and accepted['template_sha256']==sha(g['template']) and accepted['layout_sha256']==sha(g['layout']),'Current image/layout not accepted')
    need(g['accepted_erase']==dict(begin=t['fixture_erase'][0],end_exclusive=t['fixture_erase'][1]) and g['accepted_extension']==t['extension_requires_independent_root_disposable_acceptance'],'Unaccepted exact fixture sectors/extension')
    need(g['one_time_owned_browser_list_switch_authorized'] is True,'Bootstrap optional-icon/LIST scope missing')
    return g,plan,accepted
class Budget:
    def __init__(self,g):
        self.go=g;self.wall=time.time();self.mach=continuous();self.previous=self.wall
        need(g['not_before_utc_epoch']<=self.wall<=g['start_before_utc_epoch'],'Outside campaign start window')
        need(0<g['finish_before_utc_epoch']-self.wall<=10800,'Campaign finite cap')
    def check(self):
        now=time.time();duration=elapsed(self.mach,continuous())
        need(now>=self.previous and abs(now-self.wall-duration)<=.5,'Campaign clock changed')
        need(now<self.go['finish_before_utc_epoch'],'Campaign budget exhausted');self.previous=now;return now
def execute(path,output):
    g,plan,current=precheck(path);budget=Budget(g);need(not output.exists(),'Campaign output already exists');output.mkdir(parents=True)
    fd=os.open(str(path)+'.USED',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:json.dump(dict(pid=os.getpid(),go_sha256=sha(path)),f)
    previous_receipt,previous_supervisor=g['previous_receipt'],g['previous_supervisor'];fixture=qualification=None
    lease=ExistingLease(g['lease']['path'],g['lease']);steps=[];first_fault=None
    try:
        with lease:
            for p in plan['phases']:
                now=budget.check();c.check_pins(g['source_pins']);c.check_pins(g['artifact_pins'])
                need(g['finish_before_utc_epoch']-now>=p['maximum_phase_seconds']+5,'Insufficient remaining budget for next complete phase')
                phase,grant=Path(p['phase_path']),Path(p['grant_path'])
                argv=[g['python'],str(HERE/p['script']),'--phase',str(phase),'--grant',str(grant),'--output',p['output']]
                j=dict(schema=1,owner=c.OWNER,uid=UID,scope='m0-libc-batch-'+p['scope'],action=p['action'],argv=argv,cwd=g['cwd'],python_executable=g['python'],
                    template=g['template'],build=g['build'],layout=g['layout'],decoder=g['decoder'],picotool=g['picotool'],previous_receipt=previous_receipt,previous_supervisor=previous_supervisor,
                    expected=current['expected'],boot_fields=current['boot_fields'],context_fields=current['context_fields'],usb_binding=current['usb_binding'],identity_wake_authorized=g['identity_wake_authorized'],
                    indexes=p['indexes'],create_namespace=p['scope']=='qualification',initialize_list_browser=p['scope']=='qualification',Flash_writes=0,reset_commands=0,RTC_setters=0,previous_state_capture=False,previous_state_restore=False)
                if p['scope']=='fixture-install':j.update(current_image_acceptance=g['current_image_acceptance'],accepted_erase=g['accepted_erase'],after_boot_fields=g['after_boot_fields'],Flash_writes=1,reset_commands=2,known_predecessor_FS4_path=g.get('known_predecessor_FS4_path'))
                else:j['fixture_acceptance']=str(fixture)
                if p['scope']=='timing':j['qualification']=str(qualification)
                pins=dict(g['artifact_pins'])
                for k in ('previous_receipt','previous_supervisor','fixture_acceptance','qualification'):
                    if k in j:pins[j[k]]=sha(j[k])
                j['pins']=pins;save_new(phase,j)
                gr=dict(status='ROOT_EXPLICIT_PHASE_GO',uid=UID,executor=c.OWNER,phase_sha256=sha(phase),derived_from_campaign_go=c.pin(path),source_pins=g['source_pins'],
                    not_before_utc_epoch=now-1,start_before_utc_epoch=min(now+20,g['finish_before_utc_epoch']),finish_before_utc_epoch=min(now+900,g['finish_before_utc_epoch']),
                    reset_and_old_state_discard_authorized=p['scope']=='fixture-install',erase_contents_discard_authorized=p['scope']=='fixture-install',accepted_erase=g['accepted_erase'],accepted_extension=g['accepted_extension'],accepted_layout_sha256=sha(g['layout']),
                    current_image_acceptance_sha256=sha(g['current_image_acceptance']),fixture_receipt_sha256=sha(fixture) if fixture else None,qualification_sha256=sha(qualification) if qualification else None,
                    one_time_owned_browser_list_switch_authorized=g['one_time_owned_browser_list_switch_authorized'],
                    independently_accepted_predecessor_release_sha256=g['independently_accepted_predecessor_release_sha256'],independently_accepted_predecessor_supervisor_sha256=g['independently_accepted_predecessor_supervisor_sha256'])
                save_new(grant,gr);procdir=output/('process-'+str(p['index']).zfill(3))
                r=run_once(argv,procdir,cwd=g['cwd'],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout_seconds=902,max_log_bytes=16*1048576)
                previous_supervisor=str(procdir/'PROCESS.json');previous_receipt=str(Path(p['output'])/'receipt.json')
                need(r['status']=='PASS_PROCESS_EXIT' and r['EXIT']==0 and r['reaped'] and r['group_gone'] and r['parent_fds_before']==r['parent_fds_after'],'Phase child failed; STOP')
                receipt=json.loads(Path(previous_receipt).read_text());need(receipt['status']=='PASS' and not receipt.get('port_close_errors') and all(s['closed'] and not s['errors'] for s in receipt['cdc_sessions']),'Phase resources not closed')
                steps.append(dict(index=p['index'],scope=p['scope'],receipt=c.pin(previous_receipt),process=c.pin(previous_supervisor)));save_new(output/('step-'+str(p['index']).zfill(3)+'.json'),steps[-1])
                if p['scope']=='fixture-install':
                    current=dict(current,boot_fields=receipt['boot_fields_after'],usb_binding=receipt['usb_binding_after'])
                    fixture=output/'FIXTURE-ACCEPTANCE.json';save_new(fixture,dict(current,status='ROOT_ACCEPTED_M0_LIBC_IMAGE_AND_FIXTURE',derived_from_campaign_go=c.pin(path),fresh_readback=c.pin(previous_receipt),fixture_readback=receipt['fixture_readback']))
                if p['scope']=='qualification':qualification=Path(p['output'])/'QUALIFICATION.json'
                print('phase',p['index'],p['scope'],'PASS, resources closed',flush=True)
    except BaseException as e:first_fault=repr(e);raise
    finally:dump(output/'CAMPAIGN.json',dict(status='PASS_ALL_EIGHT_MATRIX_AWAITING_INDEPENDENT_ROOT_CLOSED' if len(steps)==45 and first_fault is None else 'HOLD_FIRST_FAULT',pid=os.getpid(),first_fault=first_fault,phase_receipts=steps,lease=lease.evidence,campaign_go=c.pin(path),RTC_setters=0,previous_state_capture=False,previous_state_restore=False))
def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign-go',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--write-plan',type=Path);a=p.parse_args()
    if a.write_plan:save_new(a.write_plan,phase_plan())
    else:execute(a.campaign_go,a.output)
if __name__=='__main__':main()
