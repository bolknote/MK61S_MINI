#!/usr/bin/env python3
"""Execute the real packed startup, key decoder, streaming IO and runtime.

The timer and external file/MMIO API are synthetic. Function semantics were
already tested for every body; this test does not repeat that campaign or
claim hardware time. It exercises real bodies at representative long inputs,
and accelerates other rows at the measurement boundary to test full pages.
"""
import argparse,collections,hashlib,json,struct,subprocess,sys,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=ROOT/'research/m0-libc-batch-2026-11-07'
sys.path[:0]=[str(ROOT/'tests'),str(HERE)]
from unicorn_runtime import Uc
from check_stm32_vectors import ElfImage
from prepare import pin,save,request,FUNCTIONS,ROWS
import wire
CTX=[0x410cc601,0,0,0,1,0x1000]
ROM=Path('/Users/bolk/Projects/MK61S_MINI/.build/strchr-m0-hil-20261107-v1/runs-002/000-fixture-install/factory-rom.bin')
ROM_SHA='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'

class Machine:
    def __init__(self,t,app,decoded,base,ops):
        from unicorn import UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
        import unicorn.arm_const as arm
        self.arm,self.t,self.app,self.base,self.ops=arm,t,app,base,ops
        self.e=ElfImage(Path(app['ELF']['path']));self.delta=base-app['report']['load_address']
        self.packed=Path(app['APP']['path']).read_bytes();self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);self.u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M0)
        for a,n in [(0,0x4000),(0x10000000,0x200000),(0x20000000,0x42000),(0x40054000,4096),(0x40058000,4096),(0x40008000,4096),(0xe000e000,4096),(0x14000000,4096)]:self.u.mem_map(a,n)
        rom=ROM.read_bytes();assert hashlib.sha256(rom).hexdigest()==ROM_SHA;self.u.mem_write(0,rom)
        resident=ElfImage(Path(t['candidate_ELF']['path']));resident.load(self.u)
        self.fixture=Path(t['fixture']['path']).read_bytes();self.u.mem_write(t['fixture_base'],self.fixture);self.u.mem_write(base,decoded)
        self.stop,self.api,self.services=0x101bfff0,0x101be000,0x101be200
        self.stubs={n:0x101be400+16*i for i,n in enumerate(['query','call','millis','service','file_size','file_read','unexpected','prefill_return'])}
        for a in self.stubs.values():self.u.mem_write(a,b'\x70\x47')
        calls=[self.stubs['unexpected']|1]*24
        for i,n in [(0,'millis'),(1,'service'),(13,'file_size'),(14,'file_read'),(23,'query')]:calls[i]=self.stubs[n]|1
        self.u.mem_write(self.api,struct.pack('<IHHI24I',0x31505041,1,108,33,*calls))
        self.u.mem_write(self.services,struct.pack('<IHH5I',0x31535953,2,28,0,self.stubs['call']|1,0,0,t['runtime_address']))
        for a,v in [(0xe000ed00,CTX[0]),(0x14000000,CTX[4]),(0xe000e100,CTX[5]),(0x40008030,2),(0x40008034,0x100),(0x40008038,4),(0x4005802c,0x60c)]:self.u.mem_write(a,struct.pack('<I',v))
        self.counter,self.ms=0xffffffe0,0
        self.stop_tick=self.stop_wall=False;self.input=b'';self.output=None;self.real_index=None
        self.measure_calls=collections.Counter();self.real_calls=collections.Counter();self.writes=[];self.prefill_probes=0
        self.wrong_return=False;self.change_context=False;self.failed_write=None;self.file_write_count=0
        self.protected=[(lo,bytes(self.u.mem_read(lo,hi-lo))) for lo,hi in t['protected_ranges']]
        regs=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(13)]+[arm.UC_ARM_REG_SP,arm.UC_ARM_REG_LR,arm.UC_ARM_REG_XPSR]
        self.prefill_state=None
        def prefill_next():
            s=self.prefill_state
            for r,v in s['registers'].items():self.u.reg_write(r,v)
            if s['queue']:
                offset,n=s['queue'].pop(0);s['current']=(offset,n)
                for i,v in enumerate([s['context'],offset,0x2003f000,n]):self.u.reg_write(getattr(arm,'UC_ARM_REG_R'+str(i)),v)
                self.u.reg_write(arm.UC_ARM_REG_LR,self.stubs['prefill_return']|1);self.u.reg_write(arm.UC_ARM_REG_PC,s['read']|1)
            else:
                self.u.mem_write(s['payload']+16,struct.pack('<I',10));self.u.reg_write(arm.UC_ARM_REG_R0,1)
                self.u.reg_write(arm.UC_ARM_REG_PC,s['registers'][arm.UC_ARM_REG_LR]);self.prefill_state=None
        def callback(uc,address,size,user):
            name=next(k for k,v in self.stubs.items() if v==address)
            vals=[uc.reg_read(getattr(arm,'UC_ARM_REG_R'+str(i))) for i in range(4)]
            if name=='prefill_return':
                s=self.prefill_state;assert vals[0]==1
                assert all(uc.reg_read(r)==s['registers'][r] for r in [getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(4,12)]+[arm.UC_ARM_REG_SP])
                off,n=s['current'];data=bytes(uc.mem_read(0x2003f000,n));assert data==b'\xa5'*n
                self.output[off:off+n]=data;self.prefill_probes+=1;prefill_next();return
            if name=='query':assert vals[:2]==[1,2];result=self.services
            elif name=='call':
                operation,a,b,c=vals;payload=struct.unpack('<I',uc.mem_read(uc.reg_read(arm.UC_ARM_REG_SP),4))[0]
                if operation==ops['caps']:result=2|256|(1<<24)|(1<<26)
                elif operation==ops['resolve']:
                    assert a==0xffff and b==11 and self.cstring(c)==t['namespace']+'/INPUT.bin'
                    uc.mem_write(payload,struct.pack('<5I32s',7,9,len(self.input),11,0,b'INPUT'));result=0
                elif operation==ops['source']:
                    assert a==9 and b==0xffff and c==11 and self.output is None
                    np,context,reader,n,inode=struct.unpack('<5I',uc.mem_read(payload,20));assert self.cstring(np)=='RESULT' and n==wire.REPORT_BYTES and inode==0xffff
                    self.output=bytearray(b'\xcc'*n)
                    queue=[(n-29,29),(53,117),(53,117),(0,256)]+[(i,min(256,n-i)) for i in range(0,n,256)]
                    self.prefill_state=dict(registers={r:uc.reg_read(r) for r in regs},queue=queue,context=context,read=reader,payload=payload)
                    prefill_next();return
                elif operation==ops['bytes']:
                    assert a==ops['write'] and b==0 and c==16
                    path,data,off,n=struct.unpack('<4I',uc.mem_read(payload,16));assert self.cstring(path)==t['namespace']+'/RESULT.bin' and 0<n<=4096 and off+n<=wire.REPORT_BYTES
                    self.file_write_count+=1
                    if self.file_write_count==self.failed_write:result=0
                    else:self.output[off:off+n]=uc.mem_read(data,n);self.writes.append((off,n));result=1
                else:raise AssertionError(('unexpected service',vals))
            elif name=='millis':
                if not self.stop_wall:
                    self.ms=(self.ms+1)&0xffffffff
                    if not self.stop_tick:self.counter=(self.counter+1000)&0xffffffff
                result=self.ms
            elif name=='service':result=0
            elif name=='file_size':assert vals[0]==7;result=len(self.input)
            elif name=='file_read':
                inode,off,out,n=vals;assert inode==7 and off+n<=len(self.input)
                uc.mem_write(out,self.input[off:off+n]);result=n
            else:raise AssertionError(('unexpected API',name,vals))
            uc.reg_write(arm.UC_ARM_REG_R0,result)
        for a in self.stubs.values():self.u.hook_add(UC_HOOK_CODE,callback,begin=a,end=a)
        def ticks(uc,access,address,size,value,user):
            assert address==0x40054028 and size==4
            if not self.stop_tick:self.counter=(self.counter+17)&0xffffffff
            uc.mem_write(address,struct.pack('<I',self.counter))
        self.u.hook_add(UC_HOOK_MEM_READ,ticks,begin=0x40054028,end=0x4005402b)
        def measurement(uc,address,size,user):
            row=uc.reg_read(arm.UC_ARM_REG_R0);f=uc.reg_read(arm.UC_ARM_REG_R1)
            index=struct.unpack('<I',uc.mem_read(row,4))[0];case=t['cases'][index];self.measure_calls[case['function']]+=1
            observed=bytes(uc.mem_read(self.e.symbols['key']+self.delta,32));assert observed.hex()==case['key_hex'],'actual decoder read wrong key'
            if index==self.real_index:
                self.real_calls[case['function']]+=1
                if self.change_context:uc.mem_write(0x14000000,struct.pack('<I',0));self.change_context=False
                if self.wrong_return:
                    target_ptr=self.e.symbols['targets']+self.delta+4*f;ptr=struct.unpack('<I',uc.mem_read(target_ptr,4))[0]
                    # Replace just this call's entry with a known wrong leaf.
                    uc.mem_write(0x101bd000,b'\x00\x20\x70\x47');uc.mem_write(target_ptr,struct.pack('<I',0x101bd001));self.wrong_return=False
                return
            uc.mem_write(row+12+f*28,struct.pack('<7I',*([17]*7)))
            uc.reg_write(arm.UC_ARM_REG_R0,1);uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
        ma=(self.e.symbols['measure']&~1)+self.delta;self.u.hook_add(UC_HOOK_CODE,measurement,begin=ma,end=ma)
        def write(uc,access,address,size,value,user):
            assert not (0x10000000<=address<0x10200000 or address>=0x40000000 or 0x14000000<=address<0x14001000),('CPU wrote Flash/MMIO',hex(address))
        self.u.hook_add(UC_HOOK_MEM_WRITE,write)
        self.u.reg_write(arm.UC_ARM_REG_XPSR,0x01000000);self.u.reg_write(arm.UC_ARM_REG_SP,0x20041ff0);self.u.reg_write(arm.UC_ARM_REG_LR,self.stop|1)
        self.u.emu_start(resident.symbols['__aeabi_mem_init']|1,self.stop,count=100000);assert self.u.reg_read(arm.UC_ARM_REG_PC)==self.stop
    def cstring(self,at):
        result=bytearray()
        for i in range(256):
            c=self.u.mem_read(at+i,1)[0]
            if not c:return result.decode()
            result.append(c)
        raise AssertionError('unbounded path')
    def invoke(self,command,input=None):
        if input is not None:self.input=input
        self.output=None;self.writes=[];self.file_write_count=0
        a=self.arm;u=self.u;sp=0x20041ff0
        saved={getattr(a,'UC_ARM_REG_R'+str(i)):0xa1740000+i*0x1111 for i in range(4,12)}
        for r,v in saved.items():u.reg_write(r,v)
        for r,v in [(a.UC_ARM_REG_R0,command),(a.UC_ARM_REG_R1,self.api),(a.UC_ARM_REG_R2,struct.unpack_from('<I',self.packed,52)[0]),(a.UC_ARM_REG_R3,self.packed[12]),(a.UC_ARM_REG_SP,sp),(a.UC_ARM_REG_LR,self.stop|1),(a.UC_ARM_REG_XPSR,0x01000000),(a.UC_ARM_REG_PRIMASK,0),(a.UC_ARM_REG_CONTROL,0)]:u.reg_write(r,v)
        u.mem_write(sp,bytes(4));entry=self.base+struct.unpack_from('<I',self.packed,36)[0]
        u.emu_start(entry|1,self.stop,count=500000000)
        assert u.reg_read(a.UC_ARM_REG_PC)==self.stop and u.reg_read(a.UC_ARM_REG_SP)==sp
        assert all(u.reg_read(r)==v for r,v in saved.items()),'AAPCS'
        assert u.reg_read(a.UC_ARM_REG_PRIMASK)==u.reg_read(a.UC_ARM_REG_CONTROL)==0
        assert all(bytes(u.mem_read(lo,len(data)))==data for lo,data in self.protected)
        return u.reg_read(a.UC_ARM_REG_R0)

def validate_keys(t):
    fixture=Path(t['fixture']['path']).read_bytes()
    for c in t['cases']:
        flags,n,ao,bo,lens,ac,bc,want=struct.unpack('<8I',bytes.fromhex(c['key_hex']))
        a=fixture[ao:ao+(lens&65535)];b=fixture[bo:bo+(lens>>16)]
        assert a.hex()==c['left_hex'] and b.hex()==c['right_hex']
        assert ac==zlib.crc32(a+b'\0') and bc==zlib.crc32(b+b'\0')
        op=FUNCTIONS[flags&7];assert op==c['function'] and flags>>16==c['repeats']
        if op in ('strlen','strnlen'):expected=len(a) if op=='strlen' else min(len(a),n)
        elif op in ('strcmp','strncmp','memcmp'):
            x=a if op=='strcmp' else a[:n];y=b if op=='strcmp' else b[:n]
            if op!='memcmp':x=x.split(b'\0',1)[0];y=y.split(b'\0',1)[0]
            expected=(x>y)-(x<y)
        else:
            seed=bytes.fromhex(c['seed_hex']);expected=0
            output=a+b'\0' if op=='strcpy' else a[:n]+bytes(max(0,n-len(a))) if op=='strncpy' else seed+a[:n]+b'\0'
            assert output.hex()==c['output_hex']
        assert want==expected&0xffffffff
    assert {v['logical_index'] for v in t['logical_map']}=={i for c in t['cases'] for i in c['logical_indexes']}
    return len(t['cases'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--apps',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--quick',action='store_true');a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    t=json.loads((a.template/'PLAN.json').read_text());apps=json.loads((a.apps/'BUILD.json').read_text())
    # Obtain API numeric values from the real public header, not copied enums.
    src=a.output/'enums.c';src.write_text('#include <stdio.h>\n#include "loadable_app_services.h"\nint main(void){printf("{\\"caps\\":%u,\\"resolve\\":%u,\\"source\\":%u,\\"bytes\\":%u,\\"write\\":%u}",MK61_SERVICE_CAPABILITIES,MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_FILE_WRITE_SOURCE,MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_WRITE);}\n')
    subprocess.run(['cc','-I'+str(ROOT/'code'),str(src),'-o',str(a.output/'enums')],check=True,capture_output=True);ops=json.loads(subprocess.check_output([str(a.output/'enums')]))
    checked=validate_keys(t);print('all',checked,'frozen key descriptors/oracles PASS',flush=True)
    decoder=a.output/'decode-app';argv=['c++','-std=c++17','-O2','-DMK61_CORE_STANDALONE=1','-I'+str(ROOT/'code'),str(ROOT/'tests/portable_app_format_self_test.cpp'),str(ROOT/'code/loadable_module_format.cpp'),str(ROOT/'code/zx0.cpp'),'-o',str(decoder)]
    r=subprocess.run(argv,capture_output=True,text=True);save(a.output/'DECODER-BUILD.json',dict(argv=argv,EXIT=r.returncode,stdout=r.stdout,stderr=r.stderr));assert r.returncode==0
    passed=[];machines=[]
    for route,app in enumerate(apps['products']):
        base=(0x20022008,0x20028000)[route%2];decoded_path=a.output/(app['route']+'.decoded')
        subprocess.run([str(decoder),app['APP']['path'],str(decoded_path),hex(base)],check=True,capture_output=True);decoded=decoded_path.read_bytes()
        m=Machine(t,app,decoded,base,ops);assert m.invoke(0)==0
        req=request(t,route,None);assert m.invoke(1,req)==0
        q=wire.parse_report(bytes(m.output),req,t,app,decoded);assert q['header'][24:30]==CTX
        (a.output/(app['route']+'-qual.bin')).write_bytes(m.output)
        byop={n:next(c for c in reversed(t['cases']) if c['function']==n and c['work']>=min(700,max(v['work'] for v in t['cases'] if v['function']==n))) for n in FUNCTIONS}
        selected=list(byop.values())[:1] if a.quick else list(byop.values())
        selected.sort(key=lambda c:c['index'])
        for c in selected:
            m.real_index=c['index'];req=request(t,route,c['index']//ROWS,CTX)
            result=m.invoke(1,req)
            if result!=0:
                (a.output/(app['route']+'-FIRST-FAULT.bin')).write_bytes(m.output)
                raise AssertionError((app['route'],c['function'],result,struct.unpack_from('<48I',m.output)))
            parsed=wire.parse_report(bytes(m.output),req,t,app,decoded);assert len(parsed['rows'])==min(ROWS,len(t['cases'])-(c['index']//ROWS)*ROWS)
            stem=app['route']+'-'+c['function'];(a.output/(stem+'.bin')).write_bytes(m.output)
            save(a.output/(stem+'.json'),dict(function=c['function'],case=c['index'],header=parsed['header'],rows=len(parsed['rows']),real_calls=m.real_calls[c['function']],stream_pages=parsed['header'][47]))
            assert m.real_calls[c['function']]==(9 if c['function'] in t['runtime_slots'] else 8)
            print(app['route'],c['function'],'packed body+full streaming pages PASS (synthetic17us)',flush=True)
        before=sum(m.measure_calls.values());assert m.invoke(1,req)==5 and sum(m.measure_calls.values())==before
        assert struct.unpack_from('<I',m.output,8)[0]==8
        passed.append(dict(route=app['route'],checked_rows=sum(m.measure_calls.values()),real_body_calls=dict(m.real_calls),immutable_source_probes=m.prefill_probes,stream_IO_bounds=True,cache_replay_rejected=True,protected_ranges_unchanged=True))
        machines.append((app,decoded,base,req))
    if not a.quick:
        app,decoded,base,last=machines[0];c=next(c for c in t['cases'] if c['function']=='strlen' and c['expected']>0)
        negatives=[]
        for kind in ('nonce','context','wrong-return','stopped-timer','both-clocks-stopped','wrong-ref','failed-page-write'):
            m=Machine(t,app,decoded,base,ops);assert m.invoke(0)==0;m.real_index=c['index'];req=request(t,0,c['index']//ROWS,CTX)
            if kind=='nonce':
                data=bytearray(req);struct.pack_into('<I',data,24,1);struct.pack_into('<I',data,60,zlib.crc32(data[:60]));req=bytes(data)
            if kind=='context':m.change_context=True
            if kind=='wrong-return':m.wrong_return=True
            if kind in ('stopped-timer','both-clocks-stopped'):m.stop_tick=True
            if kind=='both-clocks-stopped':m.stop_wall=True
            if kind=='wrong-ref':m.u.mem_write(0x40008034,struct.pack('<I',0x200))
            if kind=='failed-page-write':m.failed_write=2
            result=m.invoke(1,req);assert result in (4,5),kind
            raw=bytes(m.output);(a.output/('negative-'+kind+'.bin')).write_bytes(raw)
            h=struct.unpack_from('<256I',raw)
            if kind=='failed-page-write':assert result==4 and h[2]==0xffffffff and len(m.writes)==1
            else:assert h[2] in (1,2,5,6) and h[8]<=c['index'] and wire.checked_crc(raw[:1024],1020),(kind,h[:48])
            negatives.append(dict(kind=kind,result=result,header=list(h[:48]),no_later_measurement=True))
            print(kind,'first fault retained/no later group PASS',flush=True)
    else:negatives=[]
    save(a.output/'RESULT.json',dict(status='PASS_PACKED_QUICK' if a.quick else 'PASS_ALL_EIGHT_PACKED_ROUTES_STREAMING_AND_FIRST_FAULT',physical_IO=0,physical_timing=False,synthetic_interval=17,full_body_semantic_campaign_not_repeated=True,checked_key_descriptors=checked,routes=passed,negative_controls=negatives,decoder=pin(decoder),bootrom=pin(ROM),source_pins=[pin(Path(__file__)),pin(HERE/'wire.py'),pin(HERE/'carrier.c')],apps=pin(a.apps/'BUILD.json')))
if __name__=='__main__':main()
