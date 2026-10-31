"""The memchr matrix inside an already admitted, exclusively owned Pico session.

No port is opened here. The outer operator supplies the existing raw CDC
transport, native identity/health checks, Flash backup/rollback and RTC return.
Only three newly created /MCHR-Q0x directories can be mutated by this stage.
"""
import json
from pathlib import Path
import re
import struct
from types import SimpleNamespace

from session import Hold, sha
from transfer import read_file, write_file
import run as bench


def clean(reply):
    if re.search(r'(?im)^(?:ERROR\b|(?:mkdir|rmdir|rm|fsput):|Usage:)', reply):
        raise Hold('Pico matrix command failed: '+reply)
    return reply


def corpus_cases(corpus):
    result=[]
    for source in corpus['sources']:
        values=corpus.copy()
        values.update(cpu='m0',sources=[source],values=corpus['flash_values'] if source else corpus['values'])
        result+=bench.cases(SimpleNamespace(**values))
    return result


def run_app(port, context, row, proof, oracle, output, guarded):
    """Run one fixed APP; retain the first failure and use exact point cleanup.

    context is the operator's existing SDPort policy adapter. Its `state`
    exposes only the current directory and SHA-pinned small files. Atomic
    mkdir plus its correlated success establishes ownership, even if a public
    listing omits an unrelated hidden name. rmdir never removes children.
    """
    output=Path(output);output.mkdir(exist_ok=False)
    directory=row['directory']
    if directory not in ('/MCHR-Q01','/MCHR-Q02','/MCHR-Q03'):
        raise Hold('Unexpected memchr APP namespace')
    app=Path(row['app']).read_bytes()
    if sha(app)!=row['app_sha256']:raise Hold('Pico matrix APP changed')
    context.directory=directory;context.app_path=directory+'/CHRBEN.APP'
    context.state=dict(install_reserved=True,backup_helper_created=False,
                       cleanup_authorized=False,backup_helper_expected={})
    report=dict(status='RUNNING',directory=directory,shared=row['shared'],placement=row['placement'],
                groups=[],created=False,cleanup_pending=False,known_files={})
    versions={};recognized_results=[];failure=None

    def save():
        report['known_files']={p:[dict(bytes=len(b),sha256=sha(b)) for b in values] for p,values in versions.items()}
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')

    def put(name,data):
        guarded();path=directory+'/'+name
        if name not in ('CHRBEN.APP','INPUT.bin'):raise Hold('Unowned Pico write')
        context.state['backup_helper_expected'][path]=sha(data)
        versions.setdefault(path,[]).append(data);save()
        write_file(port,path,data)
        if read_file(port,path)!=data:raise Hold('Pico matrix readback differs: '+path)

    before=context.capture(port,'before',output)
    initial_root=context.listing(port,'/')
    if directory.casefold() in {r['path'].casefold() for r in initial_root}:
        raise Hold('Pico benchmark namespace already exists')
    (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    save()
    try:
        report.update(mkdir_intent=True,cleanup_pending=True);save()
        guarded();clean(port.command('mkdir "'+directory+'"'))
        report.update(created=True,cleanup_pending=True);save()
        context.state['backup_helper_created']=True
        put('CHRBEN.APP',app)
        cases=corpus_cases(row['corpus']);chunks=[cases[i:i+7] for i in range(0,len(cases),7)]
        for index,inputs in enumerate(chunks):
            guarded();context.health(port.status())
            # The APP header includes its BSS/buffers. Loader adds seven
            # bytes for alignment; mallinfo is actual device evidence.
            heap=context.heap(port)
            request=proof['memory_bytes']+7
            needed=((request+8+7)&~7)+16
            if min(heap['HEAP_FREE'],heap['HEAP_TOP'])<needed:
                raise Hold('Actual Pico loader allocation does not fit: '+repr((heap,request,needed)))
            full=bool(index==0 and row['corpus']['full_hardware_correctness_sweep'])
            data=struct.pack('<4I',0x4d434852,1,len(inputs),int(full))
            data+=b''.join(struct.pack('<6I',*values) for values in inputs)+bytes(24*(7-len(inputs)))
            put('INPUT.bin',data)
            validator=oracle.validator(inputs,proof,full);recognized_results.append(validator)
            report['active_group']=dict(index=index,inputs=inputs,full=full,heap_before=heap,
                                        loader_request=request,caller_contiguous_budget=needed);save()
            context.state['backup_helper_expected'].setdefault(directory+'/RESULT.bin',None)
            guarded();port.open(context.app_path)
            port.wait_text(b'APP_FLOW_RESULT=',port.app_start,timeout=180)
            port.wait_text(b'mk61> ',port.app_start,timeout=10)
            # Existing source-proven viewer -> browser -> closed exit. It
            # requires a successful owned APP return before sending keys.
            port.calculator()
            raw=read_file(port,directory+'/RESULT.bin')
            (output/f'{index:03d}.bin').write_bytes(raw)
            if not validator(raw):raise Hold('Unrecognized Pico APP result; retain it')
            versions.setdefault(directory+'/RESULT.bin',[]).append(raw)
            group=oracle.decode(raw,inputs,proof,full);group['index']=index
            group['heap_before']=heap;report['groups'].append(group)
            report.pop('active_group',None);save()
            print('PASS Pico memchr',directory,'batch',index+1,'/',len(chunks),'checks',group['checks'],flush=True)
        report['benchmark_status']='PASS'
    except BaseException as error:
        failure=error;report.update(benchmark_status='FAIL',failure=repr(error));save()
    finally:
        if report['created']:
            try:
                # No blind Escape/cancel or recursive rm on a failed APP.
                if port.app_inflight:raise Hold('Owned APP did not return; outer rollback must recover first')
                context.health(port.status())
                current=context.listing(port,directory)
                expected={directory+'/'+name for name in ('CHRBEN.APP','INPUT.bin','RESULT.bin')}
                if any(r['kind']!='file' or r['path'] not in expected for r in current):
                    raise Hold('Unknown namespace entries retained')
                owned={}
                for item in current:
                    path=item['path'];data=read_file(port,path)
                    known=data in versions.get(path,[])
                    if path==directory+'/RESULT.bin':known=known or any(test(data) for test in recognized_results)
                    if not known:raise Hold('Unknown namespace content retained: '+path)
                    owned[path]=data
                context.state['backup_helper_expected']={p:sha(b) for p,b in owned.items()}
                context.state['cleanup_authorized']=True
                report['cleanup_plan']={p:sha(b) for p,b in owned.items()};save()
                for path,data in owned.items():
                    guarded()
                    if read_file(port,path)!=data:raise Hold('Owned Pico file changed before removal')
                    clean(port.command('rm "'+path+'"'))
                if context.listing(port,directory):raise Hold('Pico namespace is not empty')
                guarded();clean(port.command('rmdir "'+directory+'"'))
                if context.listing(port,'/')!=initial_root:raise Hold('Visible root namespace changed')
                after=context.capture(port,'after',output)
                context.compare(before,after)
                report.update(cleanup_pending=False,cleanup_status='PASS')
            except BaseException as error:
                report.update(cleanup_failure=repr(error),cleanup_status='HOLD')
                if failure is None:failure=error
        report['status']='PASS' if failure is None and report.get('benchmark_status')=='PASS' and not report['cleanup_pending'] else 'HOLD'
        save()
    if failure is not None:raise failure
    return report
