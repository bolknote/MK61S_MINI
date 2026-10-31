#!/usr/bin/env python3
"""Offline APP, relocation, caller and failure-phase proof. No physical timing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'tools/.mk61-app')]
from check_stm32_vectors import ElfImage
from app_relocations import extract
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


wire = module('strlen_wire', HERE/'decode.py')
pack = module('strlen_pack', ROOT/'tools/.mk61-app/mk61_module_pack.py')
sha = lambda data: hashlib.sha256(data).hexdigest()


def proof(experiment, output):
    exp = json.loads(experiment.read_text())
    anchor = json.loads(wire.pinned(exp['anchors']))
    corpus = json.loads(wire.pinned(exp['corpus']))
    firmware = ElfImage(anchor['firmware']['ELF']['path'])
    m0 = exp['cpu']=='m0'
    rom_path=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
    rom=rom_path.read_bytes() if m0 else b''
    if m0:
        assert len(rom)==16384 and sha(rom)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
    checks = []
    outputs = []
    output.mkdir(parents=True, exist_ok=False)
    for app in exp['apps']:
        raw = wire.pinned(app['BIN'])
        container = wire.pinned(app['APP'])
        elf = ElfImage(app['ELF']['path'])
        assert container[:8] == b'MK61APP\0' and struct.unpack_from('<3H',container,8)==(1,64,6)
        flags, linked_base, stored, image_size, memory_size = struct.unpack_from('<5I',container,16)
        code_size, count, stored_crc, image_crc = struct.unpack_from('<4I',container,40)
        assert linked_base==0x20000000 and len(container)==64+stored and flags & 5 == 5
        assert zlib.crc32(container[:60])==struct.unpack_from('<I',container,60)[0]
        assert zlib.crc32(container[64:])==stored_crc
        decoded = pack.zx0_decode(container[64:64+code_size],image_size)
        if flags&2:
            decoded = pack.bcj_transform(decoded,False)
        assert decoded==raw==elf.bytes_at(elf.named_sections['.module_image'])
        assert zlib.crc32(raw)==image_crc and len(raw)==app['image_bytes']
        assert memory_size==app['memory_bytes']
        offsets, table = extract(Path(app['ELF']['path']),linked_base,image_size,memory_size)
        assert len(offsets)==count and table==container[64+code_size:]
        control_offset = app['control_offset']
        assert raw[control_offset:control_offset+4]==bytes.fromhex('00207047')
        for leaf in anchor['leaves']:
            if leaf['name'] in elf.symbols:
                address = (elf.symbols[leaf['name']]&~1)-linked_base
                assert sha(raw[address:address+leaf['bytes']])==leaf['sha256']
                assert not any(address<=at<address+leaf['bytes'] for at in offsets)
        bases = [0x20020000,0x20028000,0x20035000] if m0 else [0x20008000,0x20010000,0x20018000]
        for base in bases:
            machine = Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
            machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if m0 else UC_CPU_ARM_CORTEX_M4)
            for address,size in [(0x20000000,0x100000),(0x08000000,0x100000),(0x10000000,0x200000),
                                 (0x30000000,4096),(0x40054000,4096),(0xe0001000,4096),
                                 (0xe000e000,4096),(0xd0000000,4096),(0x12000000,65536)]:
                machine.mem_map(address,size)
            firmware.load(machine)
            if m0:
                machine.mem_map(0,16384)
                machine.mem_write(0,rom)
            relocated = bytearray(raw)+bytearray(memory_size-image_size)
            for at in offsets:
                struct.pack_into('<I',relocated,at,struct.unpack_from('<I',relocated,at)[0]+base-linked_base)
            machine.mem_write(base,bytes(relocated))
            assert all(relocated[at:at+4]==raw[at:at+4] for at in range(0,len(raw)-3,4)
                       if struct.unpack_from('<I',raw,at)[0] in [anchor['runtime_address'],anchor['native']['entry']])
            for symbol in ['bench_strlen_runtime','mk61_app_runtime']:
                if symbol in elf.symbols:
                    machine.mem_write(base+elf.symbols[symbol]-linked_base,struct.pack('<I',anchor['runtime_address']))
            targets = [p+base-linked_base if relocate else p for p,relocate in
                       zip(app['functions'],app['function_relocatable'])]
            timer = 0x40054028 if m0 else 0xe0001004
            active = dict(clock=0, step=17)
            def tick(uc,*_):
                active['clock']=(active['clock']+active['step'])&0xffffffff
                uc.mem_write(timer,struct.pack('<I',active['clock']))
            machine.hook_add(UC_HOOK_MEM_READ,tick,begin=timer,end=timer)
            stack, stop = 0x200fe000, 0x30000000
            saved = {reg:0x72816201+reg*314 for reg in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
            def call(entry,args,limit=3000000):
                for reg,value in saved.items():
                    machine.reg_write(reg,value)
                for reg,value in [(UC_ARM_REG_R0,args[0]),(UC_ARM_REG_R1,args[1]),(UC_ARM_REG_R2,args[2]),
                                  (UC_ARM_REG_R3,args[3]),(UC_ARM_REG_SP,stack),(UC_ARM_REG_LR,stop|1),
                                  (UC_ARM_REG_XPSR,0x01000000),(UC_ARM_REG_PRIMASK,0),(UC_ARM_REG_CONTROL,0)]:
                    machine.reg_write(reg,value)
                machine.mem_write(stack,bytes(16))
                try:
                    machine.emu_start(entry|1,stop,count=limit)
                except Exception:
                    print('EMU_FAIL',app['name'],hex(base),hex(entry),'PC',hex(machine.reg_read(UC_ARM_REG_PC)),
                          'LR',hex(machine.reg_read(UC_ARM_REG_LR)),flush=True)
                    raise
                assert machine.reg_read(UC_ARM_REG_PC)==stop, hex(machine.reg_read(UC_ARM_REG_PC))
                assert machine.reg_read(UC_ARM_REG_SP)==stack
                assert all(machine.reg_read(reg)==value for reg,value in saved.items())
                return machine.reg_read(UC_ARM_REG_R0)
            # Execute the actual indirect caller and actual selected bodies.
            measure = base+(elf.symbols['measure']&~1)-linked_base
            sink = base+elf.symbols['sink']-linked_base
            buffer = base+app['buffer_offset']
            current = {}
            def observed(uc,address,_size,_user):
                current['calls']+=1
                assert uc.reg_read(UC_ARM_REG_R0)==current['text']
            def writes(uc,_kind,address,size,_value,_user):
                assert stack-128<=address and address+size<=stack or address==sink and size==4
            wh = machine.hook_add(UC_HOOK_MEM_WRITE,writes)
            cases = [(0,7,0),(3,1,1),(128,3,0),(2048,7,1),(2048,0,0)]
            for length,align,source in cases:
                copy = (length+align)&7
                start = 2048+copy-length
                pattern = bytearray(b'\x01'*2112)
                for i in range(length):
                    at = start+i
                    pattern[32+align+i]=((at*31+(at>>3)*7)%255)+1
                pattern[32+align+length]=0
                machine.mem_write(buffer,bytes(pattern))
                text = anchor['flash_data']['address']+copy*2064+start if source else buffer+32+align
                assert bytes(machine.mem_read(text,length+1))==bytes(pattern[32+align:32+align+length+1])
                for f,target in enumerate(targets):
                    current.update(calls=0,text=text)
                    hook = machine.hook_add(UC_HOOK_CODE,observed,begin=target&~1,end=target&~1)
                    actual = call(measure,[target,text,3,0])
                    machine.hook_del(hook)
                    assert actual==17 and current['calls']==3
                    assert struct.unpack('<I',machine.mem_read(sink,4))[0]==length
                    assert bytes(machine.mem_read(buffer,len(pattern)))==pattern
                    checks.append(dict(app=app['name'],base=base,kind='real-caller',function=f,case=[length,align,source],calls=3))
            machine.hook_del(wh)
            # The moved Flash leaves must still obey containing-group bounds.
            if app['leaf_code_bank']=='flash':
                for f,leaf in enumerate(anchor['leaves']):
                    if leaf['offset'] is None:
                        continue
                    target = targets[f]
                    granule = 8 if not m0 and leaf['name'] in ['libc_strlen','dsp8','dsp32'] else 1 if leaf['name'] in ['baseline','byte1','byte4'] else 4
                    for length in [0,1,2,3,4,7,8,15,16,63,64,127,128,2047,2048]:
                        pointer = 0x12010000-length-1
                        machine.mem_write(pointer,b'\x81'*length+b'\0')
                        low = pointer&~7 if not m0 and leaf['name']=='libc_strlen' else pointer
                        high = (pointer+length+granule)&~(granule-1)
                        def guarded(uc,_kind,address,size,_value,_user):
                            assert low<=address and address+size<=high or stack-64<=address and address+size<=stack or \
                                target&~1<=address and address+size<=(target&~1)+leaf['bytes'], (leaf['name'],hex(address),size)
                        hook = machine.hook_add(UC_HOOK_MEM_READ,guarded)
                        assert call(target,[pointer,0,0,0])==length
                        machine.hook_del(hook)
                        checks.append(dict(app=app['name'],base=base,kind='moved-flash-guard',function=f,length=length))
            # Full SDK initialize/run and real correctness loops; only the
            # timer and measurement duration are synthetic in this phase.
            api, query, millis, service, delay, read = [0x200e0000,0x30000100,0x30000110,0x30000120,0x30000130,0x30000140]
            api_bytes = bytearray(108)
            struct.pack_into('<IHHI',api_bytes,0,0x31505041,1,108,0xffffffff)
            for at,pointer in [(12,millis),(16,service),(20,delay),(68,read),(104,query)]:
                struct.pack_into('<I',api_bytes,at,pointer|1)
            machine.mem_write(api,bytes(api_bytes))
            machine.mem_write(0xe000ed00,struct.pack('<I',0x410cc601 if m0 else 0x410fc241))
            machine.mem_write(0xe000edfc,struct.pack('<I',0x200))
            machine.mem_write(0xe0001000,struct.pack('<I',0x40000000))
            common = bytes(machine.mem_read(anchor['services_address'],28))
            host_call = struct.unpack_from('<I',common,12)[0]&~1
            flow = {}
            def returned(uc,value):
                uc.reg_write(UC_ARM_REG_R0,value)
                uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
            def shim(uc,address,_size,_user):
                a=[uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
                if address==query:
                    returned(uc,anchor['services_address'])
                elif address==millis:
                    returned(uc,1000)
                elif address in (service,delay):
                    returned(uc,0)
                elif address==read:
                    assert a==[17,0,a[2],184]
                    uc.mem_write(a[2],flow['input'])
                    returned(uc,184)
                elif address==host_call:
                    payload=struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4))[0]
                    if a[0]==26:
                        returned(uc,0xffffffff)
                    elif a[0]==8:
                        assert bytes(uc.mem_read(a[3],len(app['directory'])+11))==app['directory'].encode()+b'/INPUT.bin\0'
                        uc.mem_write(payload,struct.pack('<5I',17,18,184,11,0)+bytes(32))
                        returned(uc,0)
                    elif a[0]==9:
                        name,data,size,_id=struct.unpack('<4I',uc.mem_read(payload,16))
                        assert bytes(uc.mem_read(name,7))==b'RESULT\0' and size==app['report_bytes']
                        flow['report']=bytes(uc.mem_read(data,size))
                        returned(uc,17)
                    else:
                        raise AssertionError(('unexpected service',a))
                elif address==measure:
                    index=len(flow['calls'])
                    flow['calls'].append(a[:3])
                    returned(uc,1000+index%37)
                    if flow.get('post-corrupt') and index+1==flow['expected_calls']:
                        location=anchor['flash_code']['address']
                        uc.mem_write(location,bytes([uc.mem_read(location,1)[0]^1]))
                else:
                    raise AssertionError(address)
            hooks=[machine.hook_add(UC_HOOK_CODE,shim,begin=pointer,end=pointer) for pointer in
                   [query,millis,service,delay,read,host_call,measure]]
            samples = [0,32,52] if base==bases[0] else [52]
            scenarios = ['success'] if base!=bases[0] else ['success','leaf-crc','footer','timer','wrong-return','input-write','post-crc']
            for scenario in scenarios:
                for batch_index in samples if scenario=='success' else [52]:
                    machine.mem_write(base,bytes(relocated))
                    firmware.load(machine)
                    if m0:
                        # Real Pico SDK startup resolves MS/MC/S4/C4 in the
                        # existing captured ROM before shared SDK memset is used.
                        call(firmware.symbols['__aeabi_mem_init'],[0,0,0,0])
                    active.update(clock=0,step=0 if scenario=='timer' else 200011 if m0 else 19200011)
                    row=corpus['batches'][batch_index]
                    input_bytes=wire.pinned(row['input'])
                    flow.clear();flow.update(input=input_bytes,calls=[],expected_calls=len(row['rows'])*7*(len(targets)+4),
                                             **{'post-corrupt':scenario=='post-crc'})
                    entry=base+(elf.symbols['mk61_module_entry']&~1)-linked_base
                    assert call(entry,[0,api,0,4])==0
                    bad_hook=None
                    if scenario=='leaf-crc':
                        # Pick an SRAM fallback if available; otherwise a blob
                        # mutation is correctly caught by the earlier blob CRC.
                        f=next((i for i,r in enumerate(app['function_relocatable'][:len(anchor['leaves'])]) if r),0)
                        location=targets[f]&~1
                        machine.mem_write(location,bytes([machine.mem_read(location,1)[0]^1]))
                    elif scenario=='footer':
                        location=anchor['footer_address']
                        machine.mem_write(location,b'X')
                    elif scenario in ['wrong-return','input-write']:
                        def bad(uc,_address,_size,_user):
                            flow['fault_injected']=True
                            length=row['rows'][0][0]
                            if scenario=='input-write':
                                uc.mem_write(buffer,b'X')
                            returned(uc,length+1 if scenario=='wrong-return' else length)
                        bad_hook=machine.hook_add(UC_HOOK_CODE,bad,begin=targets[0]&~1,end=targets[0]&~1)
                        machine.ctl_remove_cache(targets[0]&~1,(targets[0]&~1)+32)
                    actual=call(entry,[1,0,0,0],limit=12000000)
                    if bad_hook:
                        machine.hook_del(bad_hook)
                    assert 'report' in flow, (scenario,app['name'])
                    report=flow['report']
                    parsed=wire.decode(report,exp,anchor,app,row,input_bytes)
                    expect={'success':0,'leaf-crc':1,'footer':1,'timer':4,'wrong-return':2,'input-write':3,'post-crc':5}[scenario]
                    assert parsed['failure_code']==expect and actual==(0 if not expect else 5), (scenario,parsed['failure_code'],actual,flow.get('fault_injected'))
                    assert bytes(machine.mem_read(0xe000edfc,4))==struct.pack('<I',0x200)
                    assert bytes(machine.mem_read(0xe0001000,4))==struct.pack('<I',0x40000000)
                    if scenario in ['success','post-crc']:
                        order=[]
                        for c,descriptor in enumerate(row['rows']):
                            length,align,source,loops,copy,_=descriptor
                            text=anchor['flash_data']['address']+copy*2064+2048+copy-length if source else buffer+32+align
                            for r in range(7):
                                indices=[(r+c+(len(targets)-1-j if r&1 else j))%len(targets) for j in range(len(targets))]
                                expected_targets=[base+control_offset+1,targets[0]]+[targets[i] for i in indices]+[targets[0],base+control_offset+1]
                                order += [[target,text,loops] for target in expected_targets]
                        assert flow['calls']==order
                    else:
                        assert not flow['calls']
                    name=f'{app["name"]}-{base:08x}-{batch_index:02}-{scenario}'
                    (output/(name+'.bin')).write_bytes(report)
                    checks.append(dict(app=app['name'],base=base,kind='full-SDK-flow',batch=batch_index,scenario=scenario,
                                       result=actual,failure_code=expect,measurement_calls=len(flow['calls'])))
                    outputs.append(dict(file=name+'.bin',sha256=sha(report),synthetic=True,physical=False))
            for hook in hooks:
                machine.hook_del(hook)
        print('PASS',exp['cpu'],anchor['phase'],app['name'],'checks',len(checks),flush=True)
    result=dict(status='PASS_HOST_ONLY_NOT_HARDWARE',
        experiment=dict(path=str(experiment),sha256=sha(experiment.read_bytes())),cpu=exp['cpu'],phase=anchor['phase'],
        real_caller_and_moved_Flash_bounds=True,full_SDK_flow=True,three_APP_allocations=True,
        failure_phases=[1,2,3,4,5],control_order_validated=True,checks=len(checks),details=checks,outputs=outputs,
        timer_and_measured_duration_synthetic=True,hardware_access=False,physical_timings=0)
    if m0:
        result['existing_captured_ROM']=dict(path=str(rom_path),bytes=len(rom),sha256=sha(rom),
            uid='E6657CD423721C35',startup_helper='__aeabi_mem_init',new_device_access=False)
    (output/'proof.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    proof(args.experiment.resolve(),args.output.resolve())
