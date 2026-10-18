#!/usr/bin/env python3
"""Measure separate SRAM ALU APPs on an identified RP2040; never flash/reset."""
import argparse
import json
import os
from pathlib import Path
import re
import statistics
import struct
from hil_picocalc_parity import PicoShell
from hil_c5_stack import read_file,write_file

class BenchmarkShell(PicoShell):
    def command(self,command,timeout=5):
        # fsget hex-encodes the complete APP. A 15 KiB qualification image
        # takes longer than the small-file helper's default 15 seconds.
        if command.startswith('fsget '):timeout=max(timeout,60)
        return super().command(command,timeout)

def decode(raw):
    assert len(raw)>=24
    magic,version,cases,samples,rounds=struct.unpack_from('<5I',raw)
    if version==2:return decode_addition_streams(raw)
    assert (magic,version,cases,samples,rounds)==(0x30414C55,1,12,1024,9)
    assert len(raw)==24+4*cases*96
    result={}
    for op,name in enumerate(('dadd','dsub','dmul','ddiv')):
        rows=[]
        for case in range(cases):
            offset=24+(op*cases+case)*96
            a,b,value=struct.unpack_from('<3Q',raw,offset)
            x,y=struct.unpack('<2d',struct.pack('<2Q',a,b))
            expected=(x+y,x-y,x*y,x/y)[op]
            assert value==struct.unpack('<Q',struct.pack('<d',expected))[0],(name,case,hex(a),hex(b),hex(value))
            elapsed=struct.unpack_from('<9I',raw,offset+24)
            control=struct.unpack_from('<9I',raw,offset+60)
            rows.append({'a':f'{a:016X}','b':f'{b:016X}','result':f'{value:016X}',
                'us_per_call':statistics.median(x-y for x,y in zip(elapsed,control))/samples,
                'raw_us':list(elapsed),'control_us':list(control)})
        result[name]=rows
    return result

def decode_addition_streams(raw):
    assert struct.unpack_from('<6I',raw)==(0x30414C55,2,32,1024,9,6)
    assert len(raw)==24+6*(32*24+72)
    names=('same_sign_positive','same_sign_negative','mixed_sign_close',
           'wide_gap','same_exponent','full_exponent_range')
    rows=[]
    for group,name in enumerate(names):
        offset=24+group*(32*24+72);pairs=[]
        for case in range(32):
            a,b,value=struct.unpack_from('<3Q',raw,offset+case*24)
            x,y=struct.unpack('<2d',struct.pack('<2Q',a,b))
            assert value==struct.unpack('<Q',struct.pack('<d',x+y))[0],(name,case,hex(a),hex(b),hex(value))
            pairs.append({'a':f'{a:016X}','b':f'{b:016X}','result':f'{value:016X}'})
        elapsed=struct.unpack_from('<9I',raw,offset+32*24)
        control=struct.unpack_from('<9I',raw,offset+32*24+36)
        rows.append({'name':name,'pairs':pairs,
            'us_per_call':statistics.median(x-y for x,y in zip(elapsed,control))/1024,
            'raw_us':list(elapsed),'control_us':list(control)})
    return {'dadd_streams':rows}

def operands(result):
    return {name:[[(pair['a'],pair['b']) for pair in row.get('pairs',[row])] for row in rows]
            for name,rows in result.items()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--uid',required=True)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--math-only',action='store_true',help='Run only the local 1897-vector qualification APP')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    config=json.loads((args.build/'benchmark.json').read_text());directory=config['directory']
    assert re.fullmatch(r'/MK61S-M0-ALU-[A-Za-z0-9-]+',directory)
    results={};created=False;math_result=None
    with BenchmarkShell(args.port,keyboard_layout=0) as p:
        def status():
            start=len(p.text);os.write(p.fd,b'\x05');p.pump(.5)
            return bytes(p.text[start:]).decode('cp1251','replace')
        identity=p.command('identity')
        assert 'UID='+args.uid.upper() in identity,identity
        initial=status()
        assert all(s in initial for s in ('RP2040 125 MHz','SERVICE=CLOSED','RUNTIME=NONE','RUN=0 BUSY=0','USB_DISK=0','DIRTY=0','TERMINAL=COMMAND')),initial
        if not args.math_only and 'GCC' in config['apps']:
            assert 'MATH=compact-binary64/GCC-IEEE-softfloat' in initial,'GCC control requires compiler-runtime resident firmware'
        before={cmd:p.command(cmd) for cmd in ('reg','stk','dump','pwd')}
        assert directory[1:]+'/' not in p.command('ls /')
        answer=p.command('mkdir '+directory);assert 'ERROR' not in answer,answer;created=True
        try:
            write_file(p,directory+'/marker.bin',b'\0')
            for name,app in config['apps'].items():
                if args.math_only:continue
                write_file(p,f'{directory}/{name}.APP',Path(app['file']).read_bytes())
                answer=p.command(f'open "{directory}/{name}.APP"',timeout=45)
                assert 'APP_FLOW_RESULT=0' in answer,answer
                raw=read_file(p,f'{directory}/{name}.bin')
                (args.output/(name+'.bin')).write_bytes(raw);results[name]=decode(raw)
                print(name,{op:round(statistics.mean(r['us_per_call'] for r in rows),4) for op,rows in results[name].items()},flush=True)
            if results:
                reference=operands(next(iter(results.values())))
                assert all(operands(result)==reference for result in results.values()),'benchmark operands differ between implementations'
            if 'math_probe' in config:
                names=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt','pow')
                records=[]
                fixture=Path(__file__).parent/'fixtures/compact_math_binary64.tsv'
                for line in fixture.read_text().splitlines():
                    if not line or line.startswith('#'):continue
                    op,a,b,value=line.split()
                    records.append(struct.pack('<IIQQQ',names.index(op),0,int(a,16),int(b,16),int(value,16)))
                for offset in range(0,len(records),127):
                    block=records[offset:offset+127]
                    write_file(p,f'{directory}/MATH{offset//127:02d}.bin',
                        struct.pack('<4I',0x5641544D,len(block),offset,len(records))+b''.join(block))
                    if offset//127%5==0:print('Math blocks uploaded',offset//127+1,flush=True)
                print('Uploading and verifying local math APP',flush=True)
                write_file(p,directory+'/MATHLOCAL.APP',Path(config['math_probe']['file']).read_bytes())
                print('Executing local math vectors',flush=True)
                answer=p.command(f'open "{directory}/MATHLOCAL.APP"',timeout=60)
                assert 'APP_FLOW_RESULT=0' in answer,answer
                raw=read_file(p,directory+'/MATHOUT.bin');assert len(raw)==544
                (args.output/'MATHLOCAL.bin').write_bytes(raw)
                magic,version,samples,rounds,count,failures=struct.unpack_from('<6I',raw)
                assert (magic,version,samples,rounds)==(0x54414D51,1,1024,9)
                worst=struct.unpack_from('<11Q',raw,24)
                assert count==len(records) and not failures,(count,failures)
                assert all(v<=(0 if name=='sqrt' else 4) for name,v in zip(names,worst)),worst
                math_result={'cases':count,'failures':failures,'worst_ulp':dict(zip(names,worst)),
                    'location':'Local compact_math and owned arithmetic execute in SRAM; no resident math imports.'}
                print('Local owned arithmetic:',math_result,flush=True)
            after={cmd:p.command(cmd) for cmd in before}
            assert before==after,('calculator or cwd changed',before,after)
        finally:
            p.command('fsput cancel')
            os.write(p.fd,b'\x1e\x1b\x1b\x1f');p.pump(.3)
            if created:
                answer=p.command('rm -r '+directory,timeout=30);assert 'ERROR' not in answer,answer
            final=status();(args.output/'transcript.bin').write_bytes(p.text)
        report={'status':'PASS','identity':identity,'initial':initial,'final':final,'results':results,
            'local_math':math_result,
            'temporary_directory_removed':True,'calculator_and_cwd_preserved':True,
            'method':'RP2040 TIMERAWL, 125 MHz, median of nine paired 1024-call batches minus identity; interrupts enabled.',
            'build':config}
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
