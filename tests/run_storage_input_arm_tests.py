#!/usr/bin/env python3
"""Real resident storage-input hook: transport only, pinned memory, no UI/FS.

Only clock/CDC peripheral calls are stubbed. Parser, CRC/COBS encoder, bounded RX,
session buffers and the foreground hook execute from the tested ARM ELF.
"""
import argparse
import binascii
from pathlib import Path
import struct

from unicorn.arm_const import UC_ARM_REG_IPSR,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2
from run_usb_screen_stage_arm_tests import StageBuffers
from hil_portable_apps import cobs_encode,cobs_decode


def packet(kind,payload=b''):
    raw=b'MS\x02'+bytes((kind,0))+struct.pack('<HH',0,len(payload))+payload
    return b'\0'+cobs_encode(raw+struct.pack('<H',binascii.crc_hqx(raw,65535)))+b'\0'


class Transport(StageBuffers):
    def __init__(self,path):
        self.rx=bytearray();self.tx=bytearray();self.reads=0;self.critical=False
        super().__init__(path)
        self.handlers={}
        self.forbidden=set()
        for name,address in self.elf.symbols.items():
            address&=~1
            if 'CDC_ReceiveQueue_ReadSize' in name:self.handlers[address]='available'
            elif 'CDC_ReceiveQueue_Dequeue' in name:self.handlers[address]='read'
            elif name=='CDC_resume_receive':self.handlers[address]='resume'
            elif '9UsbSerial5writeEPKhj' in name:self.handlers[address]='write'
            if any(token in name for token in ('MK61Display','program_store','storage_workspace',
                    'idle_main_process','event_hold_key','event_unhold_key','set_external_key_pressed')):
                self.forbidden.add(address)
        assert set(self.handlers.values())=={'available','read','resume','write'}

    def hook(self,uc,address,size,context):
        assert not (self.critical and address in getattr(self,'forbidden',set())),hex(address)
        handler=getattr(self,'handlers',{}).get(address)
        if handler:
            result=0
            if handler=='available':result=len(self.rx)
            elif handler=='read':
                self.reads+=1;result=self.rx.pop(0) if self.rx else 0xffffffff
            elif handler=='write':
                # LTO's constprop variant removes the fixed Serial `this`.
                pointer=uc.reg_read(UC_ARM_REG_R0);count=uc.reg_read(UC_ARM_REG_R1)
                if count>=0x20000000:
                    pointer=count;count=uc.reg_read(UC_ARM_REG_R2)
                assert 0x20000000<=pointer<0x20020000 and count<=1024
                self.tx.extend(uc.mem_read(pointer,count));result=count
            uc.reg_write(UC_ARM_REG_R0,result)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        super().hook(uc,address,size,context)

    def poll(self):
        before=self.reads
        self.critical=True
        try:self.call('_Z18storage_io_processv')
        finally:self.critical=False
        assert self.reads-before<=96,'storage path widened the CDC RX budget'


def check(path):
    m=Transport(path)
    assert m.call('_ZN10usb_screen5startEv')==1
    m.rx.extend(packet(0x14,b'ID'));m.poll()
    assert m.rx and not m.tx,'ordinary non-VM I/O entered the storage input hook'
    m.rx.clear()
    loading=m.elf.symbol('_ZN8m61_textL7loadingE')
    busy=m.elf.symbol('_ZN11language_vm12_GLOBAL__N_14busyE')
    # A NOR read nested in a normal scan's UI hold callback must not scan
    # the matrix recursively or overwrite the outer gesture's hold state.
    scan_state=m.elf.symbol('_ZL10scan_state')
    m.uc.mem_write(scan_state,b'\x02')
    session=m.word(m.elf.symbol('_ZN10usb_screen12_GLOBAL__N_1L7sessionE'))
    assert session and m.session_size>=1536
    # Fixture only: the first member is the uint8 State. An attached session
    # avoids materializing a display just to exercise the storage-only path.
    assert bytes(m.uc.mem_read(session,1))==b'\x01'
    m.uc.mem_write(session,b'\x02')
    m.uc.mem_write(loading,b'\x01')
    m.rx.extend(packet(0x14,b'M6'));m.poll()
    raw=cobs_decode(bytes(m.tx).strip(b'\0'))
    assert raw[:5]==b'MS\x02\x15\0' and raw[9:-2]==b'M6'
    m.uc.mem_write(loading,b'\x00');m.tx.clear()
    m.uc.mem_write(busy,b'\x01')
    stage=m.acquire(0,3,'VFAT_STAGE',2560)
    workspace=m.acquire(1,0,'LANGUAGE_VM',8192)
    assert stage and workspace
    m.uc.mem_write(stage,b'\x5a'*2560);m.uc.mem_write(workspace,b'\xa5'*8192)
    heap=m.heap()
    for nonce in range(32):
        payload=struct.pack('<H',nonce)
        m.rx.extend(packet(0x14,payload));m.tx.clear();m.poll()
        assert not m.rx
        raw=cobs_decode(bytes(m.tx).strip(b'\0'))
        assert raw[:5]==b'MS\x02\x15\0' and raw[9:-2]==payload
        assert binascii.crc_hqx(raw[:-2],65535)==struct.unpack('<H',raw[-2:])[0]
    damaged=bytearray(packet(0x14,b'bad'));damaged[-3]^=1
    m.rx.extend(damaged);m.tx.clear();m.poll();assert not m.tx
    # A virtual release must not dispatch a UI hold handler from NOR wait.
    for kind,payload in ((0x30,b'\x27\x01'),(0x30,b'\x27\x00'),(0x13,b''),
                         (0x11,b''),(0x11,b'invalid')):
        m.rx.extend(packet(kind,payload));m.tx.clear();m.poll();assert not m.tx
    assert bytes(m.uc.mem_read(session,1))==b'\x02','surface changed during storage'
    m.rx.extend(b'x'*192+packet(0x14,b'RX'));m.tx.clear()
    m.poll();assert m.rx and not m.tx
    m.poll();assert m.rx and not m.tx
    m.poll();assert not m.rx and m.tx
    m.rx.extend(packet(0x14,b'IQ'));m.tx.clear()
    m.uc.reg_write(UC_ARM_REG_IPSR,16);m.poll()
    assert m.rx and not m.tx
    m.uc.reg_write(UC_ARM_REG_IPSR,0);m.poll();assert not m.rx and m.tx
    assert m.heap()==heap
    assert bytes(m.uc.mem_read(scan_state,1))==b'\x02'
    assert bytes(m.uc.mem_read(stage,2560))==b'\x5a'*2560
    assert bytes(m.uc.mem_read(workspace,8192))==b'\xa5'*8192
    m.invariant()
    print('Storage input ARM: 32 CRC/nonce PONGs, invalid CRC, deferred UI/key delivery, 96-byte RX, IRQ refusal, pinned memory PASS')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',required=True,type=Path)
    check(parser.parse_args().resident_elf)
