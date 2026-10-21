#!/usr/bin/env python3
"""Execute the actual ARM boot/recheck CRC guard before hardware testing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_LR
from native_eabi_m0_arm_self_test import Machine,SP


class RejectedImage(Exception):
    pass


class FirmwareMachine(Machine):
    def __init__(self,elf):
        super().__init__(elf,True,stack_bytes=16384,instruction_budget=400000000)
        self.boot=self.elf.symbols['_ZN8picocalc8firmware12_GLOBAL__N_14bootE']
        self.failure=self.elf.symbols['_ZN8picocalc8firmware12_GLOBAL__N_17failureE']
        self.uc.mem_map(0x40054000,0x1000)  # time_us_32: fixed timer, no change to CRC code
        self.report_status=[]
        for name in ['snprintf','__wrap_snprintf']:
            if name in self.elf.symbols:
                address=self.elf.symbols[name]&~1
                self.uc.hook_add(UC_HOOK_CODE,self.format,begin=address,end=address)

    def write(self,uc,access,address,size,value,user):
        if getattr(self,'boot',-1)<=address and address+size<=getattr(self,'boot',-1)+24:
            return
        if getattr(self,'failure',-1)<=address and address+size<=getattr(self,'failure',-1)+20:
            if address==self.failure and value==0x50434657:
                raise RejectedImage('ARM guard recorded an invalid image')
            return
        return super().write(uc,access,address,size,value,user)

    def format(self,uc,address,size,user):
        del address,size,user
        pointer=uc.reg_read(UC_ARM_REG_R3)
        value=bytes(uc.mem_read(pointer,32)).split(b'\0',1)[0].decode('ascii')
        self.report_status.append(value)
        uc.reg_write(UC_ARM_REG_R0,0)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))


def qualify(elf_path,manifest_path,output):
    elf_path,manifest_path,output=Path(elf_path),Path(manifest_path),Path(output)
    manifest=json.loads(manifest_path.read_text())
    length=manifest['flash_bytes'];crc=int(manifest['firmware_integrity']['crc32'],16)
    m=FirmwareMachine(elf_path)
    m.call('_ZN8picocalc8firmware7enforceEv',0)
    boot=struct.unpack('<6I',m.uc.mem_read(m.boot,24))
    assert boot[:4]==(0,crc,crc,length),('Valid diagnostic rejected or wrong extent',boot)
    # report(buffer,capacity,recheck=true) exercises its separate size literal.
    m.call('_ZN8picocalc8firmware6reportEPcjb',(512<<32)|(SP-4096),1)
    assert m.report_status==['valid'],m.report_status
    offset=manifest['firmware_integrity']['footer_offset']
    rejects=[]
    for kind,status in [('extent',5),('reference_crc',9)]:
        test=FirmwareMachine(elf_path)
        if kind=='extent':test.uc.mem_write(0x10000000+offset+16,struct.pack('<I',length+256))
        else:
            address=manifest['diagnostic_reference']['reference_flash_address']+8
            old=bytes(test.uc.mem_read(address,1));test.uc.mem_write(address,bytes([old[0]^1]))
        try:test.call('_ZN8picocalc8firmware7enforceEv',0)
        except RejectedImage:pass
        else:raise AssertionError(('Invalid diagnostic accepted',kind))
        got=struct.unpack('<6I',test.uc.mem_read(test.boot,24))
        assert got[0]==status,(kind,got)
        rejects.append(dict(case=kind,status=got[0]))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(elf_path.read_bytes()).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),image_bytes=length,
        valid_boot_crc=hex(crc),explicit_recheck_status=m.report_status[0],rejected=rejects,
        scope='Actual ARM enforce/report CRC code and compiled image bounds; valid full image accepted; excess range and damaged reference rejected. Timer and text formatting mocked.')
    output.write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    report=qualify(args.firmware/'mk61s-picocalc-pico-h.elf',args.firmware/'manifest.json',args.json)
    print('PASS: actual ARM boot/recheck CRC accepts full diagnostic and rejects range/corruption',report['image_bytes'])


if __name__=='__main__':main()
