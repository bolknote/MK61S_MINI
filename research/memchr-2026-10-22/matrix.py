"""Pinned old-host Classic matrix admission and decoding, without device I/O."""
import json
import os
from pathlib import Path
import statistics
import struct
import sys
import run as bench
from relocation import geometry
from session import Hold,sha

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
THREAD='01a15d77-6fe3-74d3-a025-dbf484687484'
UID='AEB505B6E0067623';SERIAL='2068336B4731';BUILD='3AB3DD45'
ALLOWED=(('/MCHR-M03','38690534c676cf8ee964e331aacabc22ae5e4484a6c00c668e816d64cea12d9b',False),
         ('/MCHR-S03','c6053649da91a4d144dd7e689e265aff0adf4a6ac3fee5199c68330065019d89',True))

def dependencies(entry):
    paths={Path(__file__).resolve(),Path(entry).resolve(),Path(bench.old.__file__).resolve()}
    for name,module in list(sys.modules.items()):
        if name=='__main__':continue
        value=getattr(module,'__file__',None)
        if value:
            path=Path(value).resolve()
            if path.suffix=='.py' and ROOT in path.parents:paths.add(path)
    return {str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in sorted(paths)}

def grant(plan,digest,entry):
    return dict(scope='APP-only',cpu='m4',uid=UID,usb_serial=SERIAL,build=BUILD,
        plan_sha256=digest,runner_sha256=sha(Path(entry).read_bytes()),
        apps=[dict(directory=row['directory'],app_sha256=row['app_sha256']) for row in plan['apps']])

def validate(path,digest,port,entry,lease_path=None):
    raw=path.read_bytes()
    if sha(raw)!=digest:raise Hold('Matrix plan changed')
    plan=json.loads(raw)
    pins=dict(scope='APP-only',cpu='m4',uid=UID,usb_serial=SERIAL,build=BUILD)
    if any(plan.get(k)!=v for k,v in pins.items()) or os.path.realpath(port)!=os.path.realpath(plan['port']):raise Hold('Matrix identity/scope differs')
    if plan['dependencies']!=dependencies(entry):raise Hold('Matrix runner dependencies changed')
    if tuple((row['directory'],row['app_sha256'],row['shared']) for row in plan['apps'])!=ALLOWED:raise Hold('Unapproved matrix APP set')
    for name,item in plan['artifacts'].items():
        data=Path(name).read_bytes()
        if len(data)!=item['bytes'] or sha(data)!=item['sha256']:raise Hold('Matrix artifact changed: '+name)
    for row in plan['apps']:
        if any(row[key] not in plan['artifacts'] for key in ('app','elf','raw_image','kernels','kernel_layout','manifest')):raise Hold('Unpinned matrix proof input')
        manifest=json.loads(Path(row['manifest']).read_text())
        if manifest['app_sha256']!=row['app_sha256'] or sha(Path(row['app']).read_bytes())!=row['app_sha256']:raise Hold('Matrix APP bytes differ')
        if (manifest['directory'],manifest['shared'],manifest['expected_runtime_count'],manifest['expected_services_size'])!=(row['directory'],row['shared'],26,28):raise Hold('Matrix provider contract differs')
        if manifest['cpu']!='m4' or manifest['placement']!='sram' or manifest['flash_header']:raise Hold('Matrix scope expansion')
        if manifest['symbols']!=['baseline','libc_search','dsp16','pair64','fast64','dsp32','memchr','byte_search']:raise Hold('Matrix function set differs')
        if row['corpus']['sources']!=[0]:raise Hold('This packet only reads SRAM inputs')
    lease_path=lease_path or ROOT/'.build/classic-device-handoff.json'
    lease_raw=lease_path.read_bytes();lease=json.loads(lease_raw)
    if (lease.get('owner'),lease.get('owner_thread'),lease.get('state'),lease.get('build'))!=('memchr',THREAD,'reserved_app_only',BUILD):raise Hold('No exclusive old-host matrix lease')
    if lease.get('memchr_approval')!=grant(plan,digest,entry):raise Hold('Matrix lease binding differs')
    return plan,lease_path,sha(lease_raw)

def proof(row):
    manifest=json.loads(Path(row['manifest']).read_text())
    args=(row['app'],row['elf'],row['raw_image'],row['kernels'],row['kernel_layout'],0x20005438,0x2001bf00)
    result=geometry(*args,names=manifest['symbols'])
    cached=geometry(*args,names=('mk61_memchr_fallback' if row['shared'] else 'memchr',))
    result['sdk_cached_target']=cached['pointers'][0];result['sdk_cached_body']=cached['bodies']
    return result

def validator(inputs,bounded,full):
    row_words=69;length=256+276*len(inputs);expected=tuple(map(tuple,inputs))
    def recognized(raw):
        if len(raw)!=length:return False
        h=struct.unpack_from('<64I',raw)
        if h[:5]!=(0x4d435250,3,8,len(inputs),7) or h[26:28]!=(3,26) or h[34]!=28:return False
        if h[15]!=96000000 or h[24]!=0x9f8f7ded or h[25]!=0 or h[13]!=0:return False
        if h[16:24]!=tuple(bounded['pointers']) or h[33]!=bounded['sdk_cached_target']:return False
        if h[6] and h[14]==0 and not any(raw[256:]):return h[7]<8 and h[8]<=4096 and h[9]<=7
        if h[6] or h[5]!=8*(len(inputs)+1)+(96800 if full else 0) or h[14]<19200000:return False
        return all(struct.unpack_from('<6I',raw,256+i*row_words*4)==values for i,values in enumerate(expected))
    return recognized

def decode(raw,inputs,bounded,full,shared):
    if not validator(inputs,bounded,full)(raw):raise Hold('Report differs from pinned old-host matrix')
    h=struct.unpack_from('<64I',raw)
    if h[6]:raise Hold('Hardware correctness failed: '+repr(h[:35]))
    names=['baseline','libc','dsp16','pair64','fast64','dsp32','sdk','byte']
    rows=[]
    for index,values in enumerate(inputs):
        words=struct.unpack_from('<69I',raw,256+index*276);control=words[6:13];timings={}
        for f,name in enumerate(names):
            samples=words[13+f*7:20+f*7];cycles=[(sample-empty)/values[3] for sample,empty in zip(samples,control)]
            timings[name]=dict(raw=list(samples),paired_cycles=cycles,median_cycles=statistics.median(cycles))
        rows.append(dict(size=values[0],offset=values[1],value=values[2],loops=values[3],source=values[4],mode=values[5],
            prefix_bytes=bench.prefix(values[0],values[1],values[2],values[4],values[5]),control=list(control),timings=timings))
    return dict(checks=h[5],clock=h[15],rows=rows,public_runtime_present=False,runtime_count=26,services_size=28,
        sdk_mode='shared cached local fallback' if shared else 'standalone local',sdk_first_call_raw_cycles=h[32],
        sdk_cached_target=hex(h[33]),addresses={n:hex(a) for n,a in zip(names,h[16:24])})
