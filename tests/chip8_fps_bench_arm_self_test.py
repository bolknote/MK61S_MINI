#!/usr/bin/env python3
"""Execute the finite FPS APP as ARM, with modeled C9/display/time only."""
import argparse,re,struct,tempfile
from pathlib import Path
from run_portable_system_arm_tests import Elf,Machine,ROOT,run
from chip8_fps_fixtures import stress_rom

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resident-elf',type=Path,required=True)
    p.add_argument('--app',type=Path,required=True)
    args=p.parse_args()
    packed=args.app.read_bytes();image_size,memory_size,entry=struct.unpack_from('<III',packed,28)
    crc=struct.unpack_from('<I',packed,52)[0]
    with tempfile.TemporaryDirectory(prefix='mk61-chip8-fps-') as directory:
        root=Path(directory);reader=root/'reader';target=root/'image.bin'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        m=Machine(args.resident_elf,True)
        base=(m.pool_begin+31)&~31
        assert base+memory_size<=m.pool_end
        run([reader,args.app,target,hex(base)])
        m.load(('app',[(base,target.read_bytes())],image_size,entry,crc))
        m.files={100:(8,'C8FPS',packed),101:(9,'active.ch8',stress_rom())}
        flow=m.input
        m.uc.mem_write(flow,struct.pack('<4I',48,1,0,0)+struct.pack('<HBBI',100,4,0,300)+bytes(24))
        m.call_timeout_us=50_000_000;m.call_instruction_limit=100_000_000
        assert m.call(3)==0x31574C46 # FLOW magic
        assert m.call(4,flow)==1
        assert m.words(flow+32,4)==(4,0,0,0)
        result=[data for kind,name,data in m.files.values() if kind==4 and name=='result']
        assert len(result)==1
        report=result[0].decode('ascii');fields={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',report)}
        assert fields['V']==1 and fields['RESULT']==0 and fields['US']>=300_000,report
        assert fields['FRAME']>=12 and fields['DRAW']>fields['FRAME'] and fields['CPU']>=180,report
        assert fields['TICK']>=17 and fields['CLAMP_US']==fields['PAUSE_US']==0,report
        assert m.begins==m.ends==1
        print('Finite production CHIP8 runner ARM: auto-exit, same700IPS/60Hz, report, C9/APP ownership and graphics cleanup PASS')
        print(report,end='')
if __name__=='__main__':main()
