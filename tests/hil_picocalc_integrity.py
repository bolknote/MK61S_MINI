#!/usr/bin/env python3
"""Explicitly qualify firmware CRC rejection and ROM recovery on one Pico UID.

--flash-test installs a copy whose two checksum words disagree with its code,
observes automatic ROM UF2 fallback, then restores the supplied valid firmware
and calculator state. No card writes or STM32 operations are performed.
"""
import argparse,hashlib,json,re,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from hil_picocalc_software import connect,calculator,restore
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'ports/picocalc'))
from seal_picocalc import verify
from uf2 import encode,validate

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--uid',required=True)
    parser.add_argument('--firmware-directory',type=Path,required=True)
    parser.add_argument('--picotool',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--flash-test',action='store_true',required=True)
    args=parser.parse_args();assert re.fullmatch('[0-9A-F]{16}',args.uid)
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.firmware_directory/'manifest.json').read_text())
    good=args.firmware_directory/'mk61s-picocalc-pico-h.uf2';image=(args.firmware_directory/'mk61s-picocalc-pico-h.bin').read_bytes()
    assert hashlib.sha256(good.read_bytes()).hexdigest()==manifest['uf2_sha256']
    validate(good.read_bytes(),image)
    offset=manifest['firmware_integrity']['footer_offset'];verify(image,offset)
    corrupt=bytearray(image);corrupt[offset+20]^=1;corrupt[offset+24]^=1
    try:verify(corrupt,offset)
    except ValueError:pass
    else:raise AssertionError('negative fixture must have a CRC mismatch')
    fixture=args.output/'negative-checksum.uf2';fixture.write_bytes(encode(corrupt))
    transcript=[];cases=[];before=None;p=None
    def run(*command):
        result=subprocess.run([str(x) for x in command],capture_output=True,text=True,timeout=45)
        transcript.append(result.stdout+result.stderr)
        assert result.returncode==0,(command,result.stdout,result.stderr)
        return result.stdout
    def bootloader():
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            result=subprocess.run([str(args.picotool),'info','-a','--ser',args.uid],capture_output=True,text=True,timeout=4)
            if result.returncode==0:
                assert '0x'+args.uid in result.stdout,result.stdout
                transcript.append(result.stdout);return
            time.sleep(.3)
        raise TimeoutError('exact Pico UID did not enter its ROM bootloader')
    try:
        p=connect(args.port,args.uid);calculator(p)
        before={cmd:p.command(cmd) for cmd in ('reg','stk','hout','pwd')}
        (args.output/'calculator-before.json').write_text(json.dumps(before,indent=2)+'\n')
        p.write_line('dfu');p.pump(.2);p.__exit__(None,None,None);p=None
        bootloader()
        try:
            run(args.picotool,'load','-v','-x',fixture,'--ser',args.uid)
            time.sleep(1);bootloader()
            cases.append('checksum-modified image automatically enters RP2040 ROM UF2 before application startup')
        finally:
            # Recovery is attempted even if the negative observation failed.
            run(args.picotool,'load','-v','-x',good,'--ser',args.uid)
        p=connect(args.port,args.uid)
        final=p.expect('FIRMWARE_CRC=valid','BUILD='+manifest['build_id'].upper(),'SERVICE=CLOSED')
        assert 'FIRMWARE_CRC=valid' in p.command('dfu status')
        cases.append('sealed UF2 boots and independently recomputes its entire Flash CRC')
        restore(p,before);final=p.status();transcript.append(p.text.decode('utf-8',errors='replace'))
        cases.append('calculator program, registers, all five stack values and working directory restored')
        report={'passed':True,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'uid':args.uid,
            'uf2_sha256':manifest['uf2_sha256'],'negative_uf2_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'firmware_integrity':manifest['firmware_integrity'],'cases':cases,'final':final}
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print('ALL PicoCalc firmware integrity/recovery HIL PASS',flush=True)
    finally:
        if p is not None:p.__exit__(None,None,None)
        (args.output/'transcript.txt').write_text('\n'.join(transcript))

if __name__=='__main__':main()
