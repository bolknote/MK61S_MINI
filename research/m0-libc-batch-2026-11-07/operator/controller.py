"""One finite all-eight phase using the existing qualified CDC operator.

No device IO at import. Exact Root Go, immutable input closure, predecessor
closure and a fresh image/boot/USB/timer binding are required before opening.
"""
import argparse,hashlib,json,os,re,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
R=HERE.parent;ROOT=HERE.parents[2]
D=Path('/Users/bolk/Projects/MK61S_MINI/.build/m0-libc-batch-20261107-v1')
GUARD=Path('/Users/bolk/Projects/MK61S_MINI/.build/m0-exp-physical-20261106-001/hil')
sys.path[:0]=[str(HERE),str(R),str(GUARD),str(ROOT/'tests'),str(ROOT)]
from device_guard import Gate,Port,UID,need,sha,dump
from hil_c5_stack import read_file,write_file
from check_stm32_vectors import ElfImage
from prepare import pin,request,ROWS,ROUTES,NAMESPACE
import wire
OWNER='01a17a32-c316-7880-86b9-969da392543c'
def field(text,name):
    values=re.findall(r'(?<!\S)'+re.escape(name)+r'=([^\s]+)',text);need(len(values)==1,'Missing/ambiguous C5 '+name);return values[0]
def source_closure():
    roots=(HERE,R,GUARD,ROOT/'tests',ROOT/'tools',ROOT/'dev/lib')
    return {str(Path(m.__file__).resolve()) for m in sys.modules.values() if getattr(m,'__file__',None) and str(m.__file__).endswith('.py') and any(Path(m.__file__).resolve().is_relative_to(p) for p in roots)}
def check_pins(pins):
    for p,h in pins.items():need(sha(p)==h,'Changed reviewed input '+p)
def predecessor(j,g):
    before=json.loads(Path(j['previous_receipt']).read_text());proc=json.loads(Path(j['previous_supervisor']).read_text())
    standard=proc.get('status')=='PASS_PROCESS_EXIT' and proc.get('EXIT')==0 and proc.get('reaped') and proc.get('group_gone') and proc.get('parent_fds_before')==proc.get('parent_fds_after')
    accepted=g.get('independently_accepted_predecessor_release_sha256')==sha(j['previous_receipt']) and g.get('independently_accepted_predecessor_supervisor_sha256')==sha(j['previous_supervisor'])
    need((before.get('status')=='PASS' and standard) or accepted,'Predecessor not independently released')
    return before
def precheck(phase,grant,output):
    j=json.loads(phase.read_text());g=json.loads(grant.read_text())
    need(j['schema']==1 and j['scope'] in ('m0-libc-batch-qualification','m0-libc-batch-timing','m0-libc-batch-release') and j['owner']==OWNER and j['uid']==UID,'Wrong complete-batch phase')
    need(j['action']==('release' if j['scope'].endswith('release') else 'timing') and j['Flash_writes']==j['reset_commands']==j['RTC_setters']==0,'Forbidden action')
    need(j['argv']==[str(Path(sys.executable).resolve()),str(Path(__file__).resolve()),'--phase',str(phase),'--grant',str(grant),'--output',str(output)] and j['cwd']==str(Path.cwd().resolve())==str(ROOT),'Unbound physical argv/cwd')
    need(g['status']=='ROOT_EXPLICIT_PHASE_GO' and g['executor']==OWNER and g['uid']==UID and g['phase_sha256']==sha(phase),'No exact Root Go')
    need(source_closure()<=set(g['source_pins']),'Unpinned imported operator source');check_pins(g['source_pins']);check_pins(j['pins'])
    for k in ('template','build','fixture_acceptance','previous_receipt','previous_supervisor','decoder'):need(sha(j[k])==j['pins'][j[k]],'Unbound named input '+k)
    need(j['pins'][str(Path(sys.executable).resolve())]==sha(sys.executable),'Unpinned Python')
    t=json.loads(Path(j['template']).read_text());build=json.loads(Path(j['build']).read_text());accepted=json.loads(Path(j['fixture_acceptance']).read_text())
    need(accepted['status']=='ROOT_ACCEPTED_M0_LIBC_IMAGE_AND_FIXTURE' and accepted['uid']==UID and g['fixture_receipt_sha256']==sha(j['fixture_acceptance']),'No fresh complete-batch fixture admission')
    need(accepted['template_sha256']==sha(j['template']) and all(accepted[k]==j[k] for k in ('expected','boot_fields','context_fields','usb_binding')),'Changed actual handoff')
    need(j['expected']['crash']=='NONE' and set(j['boot_fields'])=={'BOOTS','RESET_REASON','BOOT_WATCHDOG'} and
         j['context_fields']['SYS_HZ']=='125000000' and j['context_fields']['PERI_HZ']=='48000000' and j['context_fields']['PLL_MASK']=='3','Incomplete/unsupported boot, crash or clock handoff')
    manifest=json.loads(Path(t['candidate_manifest']['path']).read_text())
    need(manifest['build_id'].upper()==j['expected']['build'].upper() and manifest['firmware_integrity']['crc32'].upper()==j['expected']['crc'].upper() and t['candidate_firmware']['bytes']==j['expected']['bytes'],'Resident source/status mismatch')
    need(t['namespace']==NAMESPACE and len(t['functions'])==8 and t['timed_APP_runs']==672 and t['rounds']==7 and len(t['runtime_words'])==26,'Changed all-eight scope')
    refs=[t[k] for k in ('candidate_firmware','candidate_ELF','candidate_manifest','fixture')]+[v[k] for v in build['products'] for k in ('APP','ELF')]
    for ref in refs:need(pin(ref['path'])==ref and j['pins'][ref['path']]==ref['sha256'],'Artifact drift')
    previous=predecessor(j,g);jobs=j['indexes'];qualification=j['scope'].endswith('qualification')
    if qualification:need(jobs==[0,1,2,3] and j['create_namespace'],'One complete four-route qualification required')
    elif j['scope'].endswith('timing'):
        need(not j['create_namespace'] and 1<=len(jobs)<=16 and jobs==list(range(jobs[0],jobs[0]+len(jobs))) and 0<=jobs[0]<=jobs[-1]<672,'Contiguous finite all-eight jobs required')
        need(jobs[0]==(previous.get('completed_jobs',[])[-1]+1 if previous.get('completed_jobs') else 0),'Skipped/replayed job')
        q=json.loads(Path(j['qualification']).read_text());need(q['status']=='PASS_FOUR_M0_LIBC_PHYSICAL_QUALIFICATIONS' and len(q['routes'])==4 and g['qualification_sha256']==sha(j['qualification'])==j['pins'][j['qualification']],'Physical timer/context not bound')
        for route in q['routes'].values():need(pin(route['raw']['path'])==route['raw'],'Qualification raw changed')
    else:need(not jobs and not j['create_namespace'] and previous.get('completed_jobs',[])[-1:]==[671],'Release before complete all-eight matrix')
    return j,t,build,previous
def status_guard(status,j,physical=None,allow_sleep=False,expected_service='CLOSED',known_predecessor_fs=False,own_icon=False):
    e=j['expected'];values=dict(BUILD=e['build'].upper(),FIRMWARE_CRC='valid',EXPECTED=e['crc'].upper(),ACTUAL=e['crc'].upper(),IMAGE=str(e['bytes']),CRASH=e['crash'],MATH_TEST='OK',failures='0',SERVICE=expected_service,RUNTIME='NONE',RUN='0',BUSY='0',USB_DISK='0',USB_SCREEN='OFF',DIRTY='0',APP_BUFFERS='0',APP_BUFFER_BYTES='0',APP_EXTERNAL_BYTES='0',APP_WINDOWS='0',KBD='OK',PANEL_INIT='1',SYS_HZ='125000000',PERI_HZ='48000000',PLL_MASK='3',SD='OK')
    values.update(j['boot_fields']);values.update(j['context_fields'])
    for name,want in values.items():need(field(status,name)==str(want),'C5 drift '+name)
    need(re.search(r'(?<!\S)RP2040 125 MHz(?!\S)',status),'CPU profile changed')
    errors=re.findall(r'(?m)(?:^|\s)FS_ERROR=\[([^\]\r\n]*)\]',status)
    if known_predecessor_fs:
        need(j.get('known_predecessor_FS4_path') and 'PATH=['+j['known_predecessor_FS4_path']+']' in status,'FS4 is not from the accepted predecessor path')
        need(errors in ([''],['File or directory not found (4)']),'Unclassified predecessor FS error')
    elif own_icon:
        need(expected_service=='BROWSER' and 'PATH=['+NAMESPACE+'/BATCH0.APP]' in status,'Optional-icon scope is not own browser')
        need(errors in ([''],['File or directory not found (4)']),'Unclassified own optional-icon error')
    else:need(errors==[''],'Filesystem error; no explicit clearing')
    need(field(status,'POWER_MODE')=='RUN' or allow_sleep and j['identity_wake_authorized'] and field(status,'POWER_MODE')=='SLEEP_USB','Power context changed')
    count=field(status,'PHYSICAL_KEYS');need(count.isdecimal(),'Invalid physical counter');count=int(count)
    if physical is not None:need(count==physical,'Physical input during campaign')
    return count
def admit(p,g):
    j=g.j;first=p.status();physical=status_guard(first,j,allow_sleep=True,known_predecessor_fs=bool(j.get('known_predecessor_FS4_path')))
    need(p.binding==j['usb_binding'],'USB binding changed');g.final['status_before']=first;p.commands()
    need('UID='+UID in p.command('identity'),'Wrong UID')
    if j.get('known_predecessor_FS4_path'):
        # Necessary namespace collision check; normal successful read only.
        listing=p.command('ls /',timeout=20);g.final['admission_root_listing']=listing
        need(NAMESPACE[1:].casefold() not in listing.casefold(),'New namespace already exists')
    status_guard(p.status(),j,physical);g.final['physical_keys']=physical;return physical
def owned_files(p,refs):
    listing=p.command('ls '+NAMESPACE);names=re.findall(r'^f\t[^\t\r\n]+\t([^\r\n]+)',listing,re.M)
    need(not re.search(r'^d\t',listing,re.M) and len(names)==len(refs) and set(names)==set(refs),'Foreign/change in owned namespace')
    for name,ref in refs.items():
        raw=read_file(p,NAMESPACE+'/'+name);need(len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'],'Owned file changed '+name)
def owned_viewer(p):
    status=p.status();need(field(status,'RUNTIME')=='NONE' and field(status,'SERVICE')=='VIEWER' and field(status,'DIRTY')=='0' and 'PATH=['+NAMESPACE+'/BATCH0.APP]' in status,'Unexpected foreground after own APP')
def own_return(p,j,physical,g):
    owned_viewer(p);p.send(b'\x1e');p.pump(.03);p.send(b'\x1b');p.pump(.1);browser=p.status()
    if j.get('initialize_list_browser') and not g.final.get('browser_list_initialized'):
        need(g.grant_data['one_time_owned_browser_list_switch_authorized'],'No Root scope for one volatile F8')
        status_guard(browser,j,physical,expected_service='BROWSER',own_icon=True)
        claim=D/'OWNED-BROWSER-LIST-ONCE.claim';fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as out:json.dump(dict(pid=os.getpid(),phase=sha(g.phase),key='0x88',retries=0),out)
        p.send(b'\x88');p.pump(.1);status_guard(p.status(),j,physical,expected_service='BROWSER');g.final['browser_list_initialized']=True
    else:status_guard(browser,j,physical,expected_service='BROWSER')
    p.send(b'\x1b');p.pump(.1);status_guard(p.status(),j,physical);p.commands()
def parse_raw(g,raw,req,t,app,stem):
    path=g.out/(stem+'.bin');path.write_bytes(raw) # preserve before any check
    need(len(raw)==wire.REPORT_BYTES,'Truncated first report')
    h=struct.unpack_from('<256I',raw);e=ElfImage(Path(app['ELF']['path']));base=app['report']['load_address']+h[212]-e.symbols['header']
    decoded=g.out/(stem+'.decoded');proc=g.command([g.j['decoder'],app['APP']['path'],str(decoded),hex(base)],timeout=10);need(proc.returncode==0 and not proc.stderr,'Pinned decoder failed')
    parsed=wire.parse_report(raw,req,t,app,decoded.read_bytes(),allow_fault=True);dump(g.out/(stem+'.json'),parsed)
    need(parsed['status']=='PASS_RAW_ALL_GROUPS','First APP fault/incomplete group '+str(h[2:4]));return parsed,pin(path)
def execute(g,t,build,previous):
    j=g.j;qualification=j['scope'].endswith('qualification');q=None if qualification or j['action']=='release' else json.loads(Path(j['qualification']).read_text())
    refs={} if j['create_namespace'] else previous['owned_files'];routes={};completed=[];intervals=0
    per_route=(len(t['cases'])+ROWS-1)//ROWS;need(per_route==168,'Unexpected route matrix')
    with Port(g) as p:
        physical=admit(p,g)
        if j['create_namespace']:
            need(NAMESPACE[1:].casefold() not in p.command('ls /',timeout=20).casefold(),'Namespace collision')
            need('ERROR' not in p.command('mkdir '+NAMESPACE),'mkdir failed')
        else:owned_files(p,refs)
        for index in j['indexes']:
            g.check();claim=D/'journal'/('qualify-' if qualification else 'job-')/str(index).zfill(3);claim.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as out:json.dump(dict(pid=os.getpid(),phase=sha(g.phase),retries=0),out)
            route=index if qualification else index//per_route;app=build['products'][route];rawapp=Path(app['APP']['path']).read_bytes()
            if refs.get('BATCH0.APP',{}).get('sha256')!=app['APP']['sha256']:write_file(p,NAMESPACE+'/BATCH0.APP',rawapp)
            req=request(t,route,None if qualification else index%per_route,None if qualification else q['routes'][app['route']]['context'])
            (g.out/(('qualify-' if qualification else 'job-')+str(index).zfill(3)+'-input.bin')).write_bytes(req);write_file(p,NAMESPACE+'/INPUT.bin',req)
            if 'RESULT.bin' in refs:
                old=read_file(p,NAMESPACE+'/RESULT.bin');need(hashlib.sha256(old).hexdigest()==refs['RESULT.bin']['sha256'],'Stale result changed')
                need('ERROR' not in p.command('rm "'+NAMESPACE+'/RESULT.bin"'),'Own stale result removal failed')
            status_guard(p.status(),j,physical)
            answer=p.command('open "'+NAMESPACE+'/BATCH0.APP"',timeout=180)
            (g.out/(('qualify-' if qualification else 'job-')+str(index).zfill(3)+'-answer.txt')).write_text(answer)
            markers=re.findall(r'(?<!\S)APP_FLOW_RESULT=([0-9]+)',answer)
            owned_viewer(p);p.commands();raw=read_file(p,NAMESPACE+'/RESULT.bin')
            stem=('qualify-' if qualification else 'job-')+str(index).zfill(3);parsed,rawref=parse_raw(g,raw,req,t,app,stem)
            need(markers==['0'],'Missing/duplicate/nonzero APP result')
            own_return(p,j,physical,g);status_guard(p.status(),j,physical)
            refs={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in [('BATCH0.APP',rawapp),('INPUT.bin',req),('RESULT.bin',raw)]}
            if qualification:routes[app['route']]=dict(context=parsed['header'][24:30],raw=rawref,actual_APP_base=parsed['actual_APP_base'])
            else:
                completed.append(index);intervals+=sum((9 if row['function'] in t['runtime_slots'] else 8)*7 for row in parsed['rows'])
            print(index,app['route'],'PASS',len(parsed['rows']),'rows',flush=True)
        owned_files(p,refs);g.final.update(status_after=p.status(),owned_files=refs,completed_jobs=completed,actual_raw_intervals=intervals,final_mode='NATIVE',namespace_retained=NAMESPACE)
        status_guard(g.final['status_after'],j,physical)
    g.noholders(g.final['native_binding'])
    if qualification:dump(g.out/'QUALIFICATION.json',dict(status='PASS_FOUR_M0_LIBC_PHYSICAL_QUALIFICATIONS',routes=routes))
def main():
    p=argparse.ArgumentParser()
    for k in ('phase','grant','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();g=None
    try:
        j,t,build,previous=precheck(a.phase,a.grant,a.output);g=Gate(a.phase,a.grant,a.output)
        g.final.update(child_pid=os.getpid(),Flash_writes=0,reset_commands=0,RTC_setters=0,previous_state_capture=False,previous_state_restore=False,crash_clear=False)
        execute(g,t,build,previous);g.finish(True)
    except BaseException as e:
        if g:g.finish(False,repr(e))
        raise
if __name__=='__main__':main()
