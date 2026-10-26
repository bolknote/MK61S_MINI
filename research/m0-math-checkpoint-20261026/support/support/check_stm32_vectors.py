#!/usr/bin/env python3
"""Check every production vector against the independent CMSIS device IRQ enum."""
import argparse
import re
import struct
from pathlib import Path


class ElfImage:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        header = struct.unpack_from('<16sHHIIIIIHHHHHH', self.data)
        assert header[0][:7] == b'\x7fELF\x01\x01\x01' and header[2] == 40
        self.sections = [struct.unpack_from('<10I', self.data, header[6] + i * header[11])
                         for i in range(header[12])]
        strings = self.sections[header[13]]
        names = self.data[strings[4]:strings[4] + strings[5]]
        self.named_sections = {self.string(names, section[0]): section for section in self.sections}
        self.segments = [struct.unpack_from('<8I', self.data, header[5] + i * header[9])
                         for i in range(header[10])]
        self.symbols = {}
        self.sizes = {}
        for section in self.sections:
            if section[1] != 2:
                continue
            strings = self.sections[section[6]]
            names = self.data[strings[4]:strings[4] + strings[5]]
            for offset in range(section[4], section[4] + section[5], section[9]):
                name, value, size, _info, _other, _index = struct.unpack_from('<IIIBBH', self.data, offset)
                decoded = self.string(names, name)
                self.symbols[decoded] = value
                self.sizes[decoded] = size

    @staticmethod
    def string(data, begin):
        return data[begin:data.index(b'\0', begin)].decode()

    def bytes_at(self, section):
        return self.data[section[4]:section[4] + section[5]]

    def load(self, machine):
        for section in self.sections:
            if section[2] & 2 and section[5] and section[1] != 8:
                machine.mem_write(section[3], self.bytes_at(section))
        # Include .data's physical Flash initializer, as well as its RAM VMA.
        for kind, offset, _vaddr, paddr, filesz, _memsz, _flags, _align in self.segments:
            if kind == 1 and filesz:
                machine.mem_write(paddr, self.data[offset:offset + filesz])


def check_vectors(image, header):
    irqs = {int(number): name + '_IRQHandler' for name, number in re.findall(
        r'\b(\w+)_IRQn\s*=\s*(\d+)\b', Path(header).read_text())}
    assert len(irqs) > 40 and max(irqs) in (84, 85), 'unsupported device IRQ enum'
    section = image.named_sections['.isr_vector']
    assert section[3] == 0x08000000 and section[3] % 512 == 0
    assert section[5] == (16 + max(irqs) + 1) * 4
    assert image.symbols['g_pfnVectors'] == section[3]
    words = struct.unpack('<' + 'I' * (section[5] // 4), image.bytes_at(section))
    assert words[0] == image.symbols['_estack'] and words[0] % 8 == 0
    core = {1: 'Reset_Handler', 2: 'NMI_Handler', 3: 'HardFault_Handler',
            4: 'MemManage_Handler', 5: 'BusFault_Handler', 6: 'UsageFault_Handler',
            11: 'SVC_Handler', 12: 'DebugMon_Handler', 14: 'PendSV_Handler', 15: 'SysTick_Handler'}
    for index in range(1, 16):
        expected = (image.symbols[core[index]] | 1) if index in core else 0
        assert words[index] == expected, ('core vector', index, hex(words[index]), hex(expected))
    for irq in range(max(irqs) + 1):
        expected = (image.symbols[irqs[irq]] | 1) if irq in irqs else 0
        assert words[16 + irq] == expected, ('peripheral vector', irq, hex(words[16 + irq]), hex(expected))
    return len(words)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--cmsis-header', type=Path, required=True)
    args = parser.parse_args()
    count = check_vectors(ElfImage(args.elf), args.cmsis_header)
    print(args.elf.parent.name, count, 'vectors match independent device IRQ enum, reserved slots and Thumb targets PASS')


if __name__ == '__main__':
    main()
