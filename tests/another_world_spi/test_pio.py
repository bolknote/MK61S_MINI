"""Exercise wire.pio's assembled instructions against known physical pin levels."""

from pathlib import Path
import re
import sys

header = Path(sys.argv[1]).read_text()
words = [int(v, 16) for v in re.findall(r"^\s*(0x[0-9a-fA-F]+),", header, re.M)]
labels = ("edge", "selected", "gap", "raw", "sample")
entry = [int(re.search(rf"wire_offset_{label} (\d+)u", header)[1]) for label in labels]
MASK32 = (1 << 32) - 1


class Machine:
    """The PIO instructions and FIFO modes used by these four state machines."""

    def __init__(self, number, sample_bits):
        self.number = number
        self.pc = entry[number]
        self.x = MASK32
        self.y = self.isr = self.shift = 0
        self.fifo = []
        self.bits = sample_bits

    def jump(self, condition, pins):
        if condition == 0:
            return True
        if condition == 2:
            old = self.x
            self.x = (old - 1) & MASK32
            return old != 0
        if condition == 4:
            old = self.y
            self.y = (old - 1) & MASK32
            return old != 0
        if condition == 3:
            return self.y == 0
        if condition == 6:
            pin = 10 if self.number == 2 else 13
            return bool(pins & (1 << pin))
        raise ValueError(f"unknown jump condition {condition}")

    def tick(self, pins):
        instruction = words[self.pc]
        opcode = instruction >> 13
        arg = (instruction >> 5) & 7
        operand = instruction & 31
        if opcode == 0:  # JMP
            if self.jump(arg, pins):
                self.pc = operand
                return
        elif opcode == 1:  # WAIT GPIO
            assert arg & 3 == 0
            if (pins >> operand) & 1 != arg >> 2:
                return
        elif opcode == 7:  # SET
            if arg == 1:
                self.x = operand
            else:
                assert arg == 2
                self.y = operand
        elif opcode == 5:  # MOV
            if (arg, operand) == (6, 3):  # ISR, NULL
                self.isr = self.shift = 0
            else:
                assert (arg, operand) == (2, 6)  # Y, ISR
                self.y = self.isr
        elif opcode == 2:  # IN PINS
            assert arg == 0
            width = self.bits if self.number == 3 else operand
            if self.number == 3 and self.shift + width == 32 and len(self.fifo) == 8:
                return
            base = 13 if self.number == 2 else 10
            field = (pins >> base) & ((1 << width) - 1)
            self.isr = ((self.isr << width) | field) & MASK32
            self.shift += width
            if self.number == 3 and self.shift == 32:
                self.fifo.append(self.isr)
                self.isr = self.shift = 0
        else:
            raise ValueError(f"unexpected PIO instruction {instruction:04x}")
        if self.number == 3 and self.pc == entry[4]:
            self.pc = entry[4]  # SM3 wraps on the single sampling instruction.
        elif self.number < 3 and self.pc + 1 == entry[self.number + 1]:
            self.pc = entry[self.number]
        else:
            self.pc += 1


def check(sys_mhz, spi_mhz, phase, bits):
    period = sys_mhz / spi_mhz
    samples = [1 << 13] * (9 + phase)
    for i in range(512):
        length = round((i + 1) * period) - round(i * period)
        high = round((i + 0.5) * period) - round(i * period)
        samples.extend([1 << 10] * high + [0] * (length - high))
        if i in (267, 407):
            samples.extend([0] * 255)  # CS stays asserted across both stalls.
    active_ticks = len(samples) - (9 + phase)
    samples.extend([1 << 13] * 210)
    edges, selected, gaps, burst = machines = [Machine(n, bits) for n in range(4)]
    for pins in samples:
        for sm in machines:
            sm.tick(pins)
    assert MASK32 - edges.x == 512
    assert abs(2 * (MASK32 - selected.x) - active_ticks) <= 1
    assert MASK32 - gaps.x == 2
    assert len(burst.fifo) == 8
    capture = [(word >> k) & ((1 << bits) - 1) for word in burst.fifo for k in range(32 - bits, -1, -bits)]
    if bits == 4:
        assert not any(sample & 8 for sample in capture)
    rising = [i for i in range(1, len(capture)) if capture[i] & 1 and not capture[i - 1] & 1]
    measured = (rising[-1] - rising[0]) / (len(rising) - 1)
    assert abs(measured - period) < (0.26 if bits == 1 else 1.01)


for cpu in (125, 200, 270):
    for spi in (12, 24):
        for phase in range(3):
            for width in (1, 4):
                check(cpu, spi, phase, width)
print("36 PIO waveforms passed")
