#!/usr/bin/env python3
"""Verify clock-gated sleep, clock sync and USB Screen on the actual Pico H.

No SD writes. Calculator X is set to 42. --leave-asleep permits a subsequent
physical unplug/replug check; BATTERY_SLEEPS then proves the battery path ran.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import time
from zoneinfo import ZoneInfo
from hil_picocalc_runtime import Pico
from hil_portable_apps import cobs_decode


class ClockPico(Pico):
    def __init__(self, path):
        self.clock_replies = []
        super().__init__(path)

    def receive_packet(self, encoded):
        super().receive_packet(encoded)
        raw = cobs_decode(encoded)
        if raw[3] == 0x41: self.clock_replies.append(raw[9:-2])

    def clock(self, mode, date):
        before = len(self.clock_replies)
        self.send(0x40, struct.pack('<BH5B', mode, date.year, date.month, date.day,
                                  date.hour, date.minute, date.second))
        deadline = time.monotonic() + 4
        while len(self.clock_replies) == before and time.monotonic() < deadline: self.pump(.05)
        assert len(self.clock_replies) > before, 'No framed RTC reply'
        reply = self.clock_replies[-1]
        assert len(reply) == 9 and reply[:2] == b'\0\1', reply
        return datetime(struct.unpack_from('<H', reply, 2)[0], *reply[4:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--leave-asleep', action='store_true')
    args = parser.parse_args();args.output.mkdir(parents=True, exist_ok=True)
    cases = [];cycles = []
    with ClockPico(args.port) as p:
        p.log_output = args.output
        initial = p.expect('PICO-H 0.4.1', 'SERVICE=CLOSED', 'USB_DISK=0')
        if 'SLEEP=1' in initial: p.step(b' ', 'SLEEP=0')
        if 'UI=CALCULATOR' not in p.status(): p.step(b'\t', 'UI=CALCULATOR')
        p.step(b'\x0842', 'X_RAW=[ 4.2000000  01]')
        before_clock = p.status()
        start = p.clock(2, datetime.now(ZoneInfo('Europe/Moscow')))
        start_wall = time.monotonic()
        unchanged = p.clock(1, datetime(2037, 3, 4, 5, 6, 7))
        assert abs((unchanged - start).total_seconds()) <= 1
        p.expect('X_RAW=[ 4.2000000  01]', 'RTC_SET=1')
        cases.append('CRC-framed RTC read/set; automatic sync preserves an already configured RTC and X=42')
        p.send(0x17);p.pump(.6);p.expect('USB_SCREEN=OFFER', 'X_RAW=[ 4.2000000  01]')
        p.attach_waiting();p.pump(.6)
        assert struct.unpack_from('<H', p.caps, 4)[0] & 128
        assert p.frames and any(p.frames[-1])
        p.send(0x13);p.attached = False;p.pump(.2);p.expect('USB_SCREEN=OFFER')
        cases.append('framed PicoCalc USB Screen activation, advertised clock capability and atomic keyframe')
        for _ in range(3):
            p.system(7, 'SLEEP=1')
            p.pump(.3)
            asleep = p.expect('SLEEP=1', 'LCD_BKL=0 KBD_BKL=0', 'POWER_MODE=SLEEP_USB',
                              'SYS_HZ=48000000 PERI_HZ=48000000 PLL_MASK=2')
            p.pump(1.2)
            awake = p.step(b' ', 'SLEEP=0', 'LCD_BKL=240 KBD_BKL=40', 'POWER_MODE=RUN',
                           'SYS_HZ=125000000 PERI_HZ=125000000 PLL_MASK=3', 'X_RAW=[ 4.2000000  01]')
            assert 'KBD=OK errors=0' in awake and 'SCREEN_ERRORS=0' in awake
            cycles.append({'asleep': asleep, 'awake': awake})
        cases.append('three real sleep/wake cycles: PLL_SYS off, USB alive at 48 MHz, full 125 MHz restoration, RAM/backlight/keypad preserved')
        final_clock = p.clock(0, start)
        elapsed = time.monotonic() - start_wall
        assert abs((final_clock - start).total_seconds() - elapsed) < 2
        cases.append('RTC continuity from XOSC through repeated PLL changes')
        if args.leave_asleep: p.system(7, 'SLEEP=1')
        final = p.status()
        root = Path(__file__).resolve().parents[1]
        report = {'uf2_sha256': hashlib.sha256((root/'binary/picocalc-pico-h/mk61s-picocalc-pico-h.uf2').read_bytes()).hexdigest(),
                  'passed': True, 'cases': cases, 'initial': initial, 'cycles': cycles, 'final': final,
                  'rtc_elapsed_seconds': (final_clock-start).total_seconds(), 'wall_elapsed_seconds': elapsed}
        (args.output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('PASS PicoCalc clock-gated sleep, USB/PLL restoration, framed clock sync', flush=True)


if __name__ == '__main__': main()
