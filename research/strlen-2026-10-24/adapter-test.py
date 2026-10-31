#!/usr/bin/env python3
"""Exercise the frozen adapter's whole batch transaction with mock parent I/O."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import zlib


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    adapter=load('frozen_strlen_adapter',a.packet/'adapter.py')
    wire=load('frozen_strlen_wire',a.packet/'decode.py')
    plan=json.loads((a.packet/'plan.json').read_text());checks=[]
    for phase in plan['phases']:
        exp_path=Path(phase['experiment']['path'])
        exp=json.loads(wire.pinned(phase['experiment']))
        corpus=json.loads(wire.pinned(exp['corpus']))
        proof_path=Path(phase['proof']['path']).parent
        proof=json.loads(wire.pinned(phase['proof']))
        templates={}
        for app in exp['apps']:
            template=next(out['file'] for out in proof['outputs'] if out['file'].startswith(app['name']+'-') and
                          out['file'].endswith('-00-success.bin'))
            templates[app['name']]=(proof_path/template).read_bytes()
        class Parent:
            def __init__(self,fault=None):
                self.files={};self.predicates=[];self.opens=0;self.guards=0;self.idle=0;self.fault=fault
            def guard(self):self.guards+=1
            def check_idle(self):
                self.idle+=1
                return dict(mock=True,physical=False,typed_idle=True)
            def put(self,name,data):
                assert name in ['STLNBEN.APP','INPUT.bin'];self.files[name]=data
            def read(self,name):return self.files[name]
            def expect_result(self,predicate,metadata):self.predicates.append((predicate,metadata))
            def admit_result(self,data):assert self.predicates[-1][0](data)
            def open(self,name,timeout):
                assert name=='STLNBEN.APP' and timeout==180 and len(self.predicates)==self.opens+1
                self.opens+=1
                _predicate,meta=self.predicates[-1]
                app=next(item for item in exp['apps'] if item['name']==meta['app'])
                assert self.files['STLNBEN.APP']==wire.pinned(app['APP'])
                batch=corpus['batches'][meta['batch']]
                assert self.files['INPUT.bin']==wire.pinned(batch['input'])
                raw=bytearray(templates[app['name']]);f=len(app['functions']);stride=24+7*4*(f+4)
                struct.pack_into('<I',raw,3*4,len(batch['rows']))
                struct.pack_into('<I',raw,5*4,len(batch['rows'])*f)
                struct.pack_into('<I',raw,8*4,batch['first'])
                struct.pack_into('<I',raw,27*4,zlib.crc32(self.files['INPUT.bin']))
                for i in range(7):
                    at=256+i*stride
                    raw[at:at+stride]=bytes(stride)
                    if i<len(batch['rows']):
                        struct.pack_into('<6I',raw,at,*batch['rows'][i])
                        for r in range(7):
                            struct.pack_into('<'+'I'*(f+4),raw,at+24+r*4*(f+4),*[1000+q for q in range(f+4)])
                if self.fault=='known':
                    for i in range(len(batch['rows'])):
                        raw[256+i*stride+24:256+(i+1)*stride]=bytes(stride-24)
                    for field,value in [(5,1),(6,1),(7,2),(14,0),(63,batch['rows'][0][0]+1)]:
                        struct.pack_into('<I',raw,field*4,value)
                elif self.fault=='unknown':struct.pack_into('<I',raw,0,0)
                elif self.fault=='stale':struct.pack_into('<I',raw,27*4,batch['crc32']^1)
                self.files['RESULT.bin']=bytes(raw)
                return dict(mock=True,physical=False,completed=True)
        for fault in [None,'known','unknown','stale']:
            parent=Parent(fault);target=a.output/(phase['cpu']+'-'+phase['phase']+'-'+(fault or 'success'))
            try:
                result=adapter.run_phase(parent,exp_path,target)
            except (adapter.Hold,wire.Invalid,ValueError) as error:
                assert fault is not None,(fault,error)
                assert parent.opens==1
                checks.append(dict(cpu=phase['cpu'],phase=phase['phase'],fault=fault,status='STOPPED',opens=parent.opens))
            else:
                assert fault is None
                assert parent.opens==212 and result['batches']==212 and parent.idle==214
                checks.append(dict(cpu=phase['cpu'],phase=phase['phase'],fault=None,status='PASS',opens=parent.opens))
    result=dict(status='PASS_HOST_MOCK_ONLY',checks=checks,physical_IO=0,hardware_timings=0,
        positive_batches=sum(c['opens'] for c in checks if c['fault'] is None),faults_stopped=sum(c['fault'] is not None for c in checks))
    (a.output/'adapter-test.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
