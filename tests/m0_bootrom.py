"""Execute only the captured, identified RP2040 B2 factory math in Unicorn."""
import hashlib
import json
from pathlib import Path
import struct

from native_eabi_m0_arm_self_test import Machine

ROM_SHA = 'ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
OFFSETS = dict(dadd=0x00,dsub=0x04,dmul=0x08,ddiv=0x0c,sqrt=0x18,
               cos=0x3c,sin=0x40,tan=0x44,exp=0x4c,ln=0x50,atan2=0x58)


class ROMMachine(Machine):
    def __init__(self, elf, rom, metadata):
        super().__init__(elf, True, stack_bytes=16384, instruction_budget=20000000)
        raw = Path(rom).read_bytes()
        self.rom_metadata = json.loads(Path(metadata).read_text())
        assert len(raw) == 16384 and hashlib.sha256(raw).hexdigest() == ROM_SHA
        assert self.rom_metadata['sha256'] == ROM_SHA
        assert self.rom_metadata['uid'] == 'E6657CD423721C35'
        assert raw[0x13] == self.rom_metadata['rom_version'] == 3
        function_table, data_table, lookup = struct.unpack_from('<3H', raw, 0x14)
        assert (function_table,data_table,lookup) == tuple(self.rom_metadata[k] for k in ('function_table','data_table','lookup'))
        self.uc.mem_map(0,65536)
        self.uc.mem_write(0,raw)
        self.elf.symbols['rom_lookup'] = lookup
        def find(table,code):
            value = self.call('rom_lookup',table,int.from_bytes(code.encode(),'little'),width=32)[0] & 0xffffffff
            assert 0 < value < len(raw), (code,value)
            return value
        sd, sf = find(data_table,'SD'), find(data_table,'SF')
        assert (sd,sf) == (self.rom_metadata['soft_double_table'],self.rom_metadata['soft_float_table'])
        self.rom_entries = {name:struct.unpack_from('<I',raw,sd+offset)[0] for name,offset in OFFSETS.items()}
        assert self.rom_entries == self.rom_metadata['entries']
        for name,address in self.rom_entries.items():
            assert address & 1 and address < len(raw)
            self.elf.symbols['rom_'+name] = address
        if 'aeabi_bits_funcs' in self.elf.symbols:
            table = self.elf.symbols['aeabi_bits_funcs']
            for index in range(4):
                code = struct.unpack('<I',self.uc.mem_read(table+4*index,4))[0]
                key = code.to_bytes(2,'little').decode('ascii')
                assert key in self.rom_metadata['function_codes']
                self.uc.mem_write(table+4*index,struct.pack('<I',find(function_table,key)))
        git = find(data_table,'GR')
        self.rom_revision = struct.unpack_from('<I',raw,git)[0]
        assert self.rom_revision == 0x5b0d9bca

    def rom_intrinsic(self,uc,address,size,operation):
        if operation in ('clz32','clz64'):
            return
        return super().rom_intrinsic(uc,address,size,operation)
