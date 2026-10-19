#!/usr/bin/env python3
"""Time the installed Turochamp search on an exact PicoCalc UID/build.

No firmware or card writes. Verify the complete game, read native 320x320
CRC-checked USB frames, and restore the calculator data and terminal directory.
The first run is a session-first run, not a claim of empty caches after reset.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
import zlib

from hil_c5_stack import read_file
from hil_picocalc_apps import AppsPort
from hil_picocalc_software import calculator, restore
from hil_portable_system_apps import png
from hil_turochamp_performance import Font, ROOT, board_pixels as compact_board_pixels, completed_board
from m8_codec import encode


def canonical_frame(native):
    """Translate the unscaled FMK cells to the existing Classic pixel oracle.

    PicoCalc cell (0,0) is at (8,36); Classic cell (0,0) is at (2,0).
    This is a pixel-for-pixel crop/translation, with no glyph resampling.
    """
    assert len(native) == 12800
    frame = bytearray(1536)
    for y in range(64):
        for x in range(192):
            if native[(y + 36) // 8 * 320 + x + 6] & (1 << ((y + 36) % 8)):
                frame[y // 8 * 192 + x] |= 1 << (y % 8)
    return bytes(frame)


def board_pixels(frame):
    if len(frame)==1536:return compact_board_pixels(frame)
    assert len(frame)==12800
    pixels=bytearray(frame)
    for page in range(2):pixels[page*320+304:(page+1)*320]=bytes(16)
    return bytes(pixels)


class ChessPort(AppsPort):
    def __init__(self, path, large_font=False):
        super().__init__(path, keyboard_layout=0)
        self.native_display = True
        self.frame_times = []
        self.boards = []
        self.large_font = large_font

    def receive_packet(self, encoded):
        count = len(self.frames)
        super().receive_packet(encoded)
        if len(self.frames) > count:
            self.frame_times.append(time.monotonic())
            self.boards.append(self.frames[-1] if self.large_font else canonical_frame(self.frames[-1]))


def healthy(status, build):
    for token in ('BUILD=' + build, 'CRASH=NONE', 'FIRMWARE_CRC=valid',
                  'SD=OK', 'USB_DISK=0', 'SCREEN_ERRORS=0'):
        assert token in status, (token, status)


def wait_screen(p, font, label, start=0, timeout=45, additional=()):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        p.pump(.04)
        if len(p.boards) > start and all(font.has(p.boards[-1], text) for text in (label, *additional)):
            return
        assert b'Open failed!' not in p.text[p.open_text_start:], p.text[-600:]
    raise TimeoutError('Missing Turochamp screen: ' + label)


def stop(p):
    for _ in range(4):
        if p.attached:
            p.key(39)  # PicoCalc's MINI wire layout: Escape.
        else:
            os.write(p.fd, b'\x1e\x1b')
        p.pump(.15)
        status = p.status()
        if 'M61_ACTIVE=0 ' in status and 'RUNTIME=NONE ' in status:
            calculator(p)
            return
    raise AssertionError(('Turochamp did not stop', status))


def search(p, font, args, index, destination):
    destination.mkdir()
    cursor = len(p.frames)
    opened = time.monotonic()
    p.open(args.game_dir.rstrip('/') + '/autoexec.m61')
    # Loading the FMK font can repaint the previous run's retained text before
    # init.tbi finishes. Require fresh output from this menu invocation before
    # sending keys; a matching old bitmap alone is not a readiness barrier.
    p.wait_text(encode('ОК - НАЧАТЬ'), p.open_text_start, timeout=60)
    wait_screen(p, font, 'ВЫБЕРИТЕ СТОРОНУ', cursor, additional=('ОК - НАЧАТЬ',))
    menu_seconds = time.monotonic() - opened
    for label in ('ЧЁРНЫЕ', 'ДВА ИГРОКА', 'ИНСТРУКЦИЯ', 'ДЕБЮТНАЯ КНИГА'):
        cursor = len(p.frames)
        text_cursor = len(p.text)
        p.key(24)  # MINI right: next menu item (logical INPUT 16).
        p.wait_text(encode(label), text_cursor)
        ending = 'ОК - ВКЛ/ВЫКЛ' if label == 'ДЕБЮТНАЯ КНИГА' else 'ОК - НАЧАТЬ'
        p.wait_text(encode(ending), text_cursor)
        wait_screen(p, font, label, cursor, additional=(ending,))
    if font.has(p.boards[-1], 'КНИГА: ВКЛ'):
        cursor = len(p.frames)
        text_cursor = len(p.text)
        p.key(29)  # MINI OK.
        p.wait_text(encode('КНИГА: ВЫКЛ'), text_cursor)
        wait_screen(p, font, 'КНИГА: ВЫКЛ', cursor, additional=('ОК - ВКЛ/ВЫКЛ',))
    assert font.has(p.boards[-1], 'КНИГА: ВЫКЛ')
    png(p.frames[-1], destination / 'book-off-native.png')
    for label in ('БЕЛЫЕ', 'ЧЁРНЫЕ'):
        cursor = len(p.frames)
        text_cursor = len(p.text)
        p.key(24)
        p.wait_text(encode(label), text_cursor)
        p.wait_text(encode('ОК - НАЧАТЬ'), text_cursor)
        wait_screen(p, font, label, cursor, additional=('ОК - НАЧАТЬ', 'КНИГА: ВЫКЛ'))

    cursor = len(p.frames)
    if args.screen_mode == 'completion':
        p.send(0x13)
        p.attached = False
        p.pump(.2)
        os.write(p.fd, b'\x1e')
        p.pump(.05)
    serial_start = len(p.text)
    started = time.monotonic()
    if args.screen_mode == 'completion':
        os.write(p.fd, b'\r')
    else:
        p.key(29)
    progress, seen = [], set()
    last_notice = started
    serial_finished = None
    while time.monotonic() - started < args.timeout:
        p.pump(.04)
        serial = bytes(p.text[serial_start:])
        failures = re.findall(rb'VM_RESULT=(?!OK\b)[^\r\n]+', serial)
        assert not failures, failures
        if args.screen_mode == 'continuous':
            assert p.attached, 'USB Screen detached during search'
        elif not p.attached:
            for value in re.findall(encode('ПОЗ ') + rb'(\d+)', serial):
                nodes = int(value)
                if nodes not in seen:
                    seen.add(nodes)
                    progress.append(dict(nodes=nodes, seconds=time.monotonic() - started))
            heading = b'  h g f e d c b a' if p.large_font else b' hgfedcba'
            board = serial[serial.rfind(heading):]
            if (encode('ВАШ ХОД') in board and b'e2-e3' in board and
                all(re.search(rb'(?m)^' + str(rank).encode() + rb'[^\r\n]*\r?\n', board)
                    for rank in range(1, 9)) and
                re.search(rb'(?m)^8[^\r\n]*' + encode('ОК ВЫБОР') + rb'\r?\n', board)):
                serial_finished = time.monotonic() - started
                cursor = len(p.frames)
                p.attach_waiting()
                (destination / 'complete-board.m8').write_bytes(board)
        if args.screen_mode == 'completion' and not p.attached:
            cursor = len(p.frames)
        for i in range(cursor, len(p.frames)):
            frame, stamp = p.boards[i], p.frame_times[i]
            if args.screen_mode == 'continuous' and font.has(frame, 'ПОИСК...' if p.large_font else 'ДУМАЕТ...'):
                nodes = font.number_after(frame, 'ПОЗ ')
                if nodes is not None and nodes not in seen:
                    seen.add(nodes)
                    progress.append({'nodes': nodes, 'seconds': stamp - started})
                    if nodes in (0, 21, 210, 420):
                        png(p.frames[i], destination / f'nodes-{nodes:04d}-native.png')
            elif completed_board(font, frame):
                assert progress and progress[-1]['nodes'] == 420, progress
                elapsed = stamp - started
                png(p.frames[i], destination / 'move-e2-e3-native.png')
                png(frame, destination / 'move-e2-e3-canonical.png')
                (destination / 'move-native.frame').write_bytes(p.frames[i])
                (destination / 'move-canonical.frame').write_bytes(frame)
                result = dict(repeat=index, temperature='session-first' if index == 0 else 'repeat',
                              menu_seconds=menu_seconds, seconds=elapsed, nodes=420,
                              nodes_per_second=420 / elapsed, move='e2e3',
                              complete_eight_rank_board=True, progress=progress,
                              screen_mode=args.screen_mode,
                              terminal_complete_seconds=serial_finished,
                              board_frame_sha256=hashlib.sha256(board_pixels(frame)).hexdigest(),
                              native_frame_sha256=hashlib.sha256(p.frames[i]).hexdigest())
                if p.large_font:
                    rows=bytearray(12800)
                    for y in range(320):
                        for x in range(320):
                            if frame[y//8*320+x]&(1<<(y&7)):rows[y*40+x//8]|=0x80>>(x&7)
                    wanted=f'{zlib.crc32(rows):08X}'
                    deadline=time.monotonic()+8
                    while time.monotonic()<deadline:
                        status=p.status()
                        if 'LCD_PENDING=0 ' in status and 'LCD_FRAME_CRC='+wanted in status:break
                        p.pump(.05)
                    else:raise AssertionError(('LCD transfer differs from native chess frame',wanted,status))
                    result['lcd_transfer_crc']=wanted
                (destination / 'run.json').write_text(json.dumps(result, indent=2) + '\n')
                print(f'Run {index + 1}: e2-e3, 420 nodes, {elapsed:.3f}s PASS', flush=True)
                stop(p)
                # Include the complete result stream through the final stop,
                # so asynchronous output cannot silently lose module reports.
                trace=re.findall(rb'(?m)^VM_RESULT=[^\r\n]*',bytes(p.text[serial_start:]))
                result['module_result_count']=len(trace)
                result['module_result_trace_sha256']=hashlib.sha256(b'\n'.join(trace)).hexdigest()
                (destination / 'run.json').write_text(json.dumps(result, indent=2) + '\n')
                return result
        cursor = len(p.frames)
        if time.monotonic() - last_notice >= 25:
            nodes = progress[-1]['nodes'] if progress else '?'
            modules = len(re.findall(rb'VM_RESULT=OK\b', serial))
            live = dict(nodes=nodes, seconds=time.monotonic() - started, completed_module_calls=modules)
            (destination / 'live.json').write_text(json.dumps(live, indent=2) + '\n')
            (destination / 'terminal-live.m8').write_bytes(serial)
            print(f'Run {index + 1}: {nodes} nodes, {live["seconds"]:.1f}s, {modules} completed modules', flush=True)
            last_notice = time.monotonic()
        assert b'Open failed!' not in p.text[p.open_text_start:], p.text[-600:]
    raise TimeoutError(('Turochamp search', progress, bytes(p.text[-1200:])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--game-dir', required=True)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--runs', default=3, type=int)
    parser.add_argument('--large-font', action='store_true', help='Validate native 12x24 text and paired 24x24 chess tiles')
    parser.add_argument('--timeout', default=900, type=float)
    parser.add_argument('--screen-mode', choices=('continuous', 'completion'), default='continuous',
                        help='Mirror throughout, or attach only after the complete terminal board')
    args = parser.parse_args()
    assert 1 <= args.runs <= 10
    assert re.fullmatch(r'[0-9A-Fa-f]{16}', args.uid)
    assert re.fullmatch(r'[0-9A-Fa-f]{8}', args.build_id)
    args.uid, args.build_id = args.uid.upper(), args.build_id.upper()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    font = (Font((ROOT/'programs/games/Turochamp/Turochamp320.FMK').read_bytes(),
                 width=12,height=24,left=4,top=40,columns=26,rows=10,frame_width=320) if args.large_font
            else Font((ROOT/'programs/games/Turochamp/Turochamp.FMK').read_bytes()))
    report = dict(result='RUNNING', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                  uid=args.uid, build=args.build_id, game_directory=args.game_dir,
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  opening_book=False, level=2, maximum_depth=8, profiling=False,
                  reset_before=False, native_geometry=[320, 320],
                  screen_mode=args.screen_mode,
                  text_cell=[12,24] if args.large_font else [7,7],
                  timing_start='OK on Black selection',
                  timing_end='CRC-checked complete eight-rank e2-e3 board',
                  filesystem_writes=0, firmware_writes=0, runs=[])
    before = None
    with ChessPort(args.port,args.large_font) as p:
        p.drain()
        p.commands()
        identity = p.command('identity')
        assert 'UID=' + args.uid in identity, identity
        initial = p.status()
        healthy(initial, args.build_id)
        for token in ('UI=CALCULATOR', 'SERVICE=CLOSED', 'DIRTY=0', 'RUN=0', 'M61_ACTIVE=0'):
            assert token in initial, initial
        report.update(identity=identity, initial=initial)
        before = {command: p.command(command) for command in ('reg', 'stk', 'hout', 'pwd')}
        (args.output_dir / 'snapshot.json').write_text(json.dumps(before, indent=2) + '\n')
        try:
            package = {}
            for source in sorted((ROOT / 'programs/games/Turochamp').iterdir()):
                if not source.is_file():
                    continue
                binary = source.suffix.lower() == '.fmk'
                expected = source.read_bytes() if binary else encode(source.read_text())
                actual = read_file(p, args.game_dir.rstrip('/') + '/' + source.name, m8=not binary)
                assert actual == expected, ('Installed game differs', source.name)
                package[source.name] = dict(bytes=len(actual), sha256=hashlib.sha256(actual).hexdigest())
            report['game_package'] = package
            print(f'Verified all {len(package)} game files; firmware {args.build_id}; native 320x320', flush=True)
            p.command('uscreen on')
            p.attach_waiting()
            for index in range(args.runs):
                report['runs'].append(search(p, font, args, index, args.output_dir / f'run-{index + 1}'))
                report['health_run_' + str(index + 1)] = p.status()
                healthy(report['health_run_' + str(index + 1)], args.build_id)
                (args.output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            assert len({run['board_frame_sha256'] for run in report['runs']}) == 1
            report['median_seconds'] = statistics.median(run['seconds'] for run in report['runs'])
            report['repeat_median_seconds'] = statistics.median(run['seconds'] for run in report['runs'][1:]) if args.runs > 1 else None
            for source in (ROOT / 'programs/games/Turochamp').iterdir():
                if source.is_file():
                    binary = source.suffix.lower() == '.fmk'
                    expected = source.read_bytes() if binary else encode(source.read_text())
                    assert read_file(p, args.game_dir.rstrip('/') + '/' + source.name, m8=not binary) == expected
            report['game_files_unchanged'] = True
            report['result'] = 'PASS'
        except BaseException as error:
            report.update(result='FAIL', error=repr(error))
            if p.frames:
                png(p.frames[-1], args.output_dir / 'failure-native.png')
            raise
        finally:
            try:
                stop(p)
                p.command('cd "' + re.search(r'(?m)^(/[^\r\n]*)', before['pwd'])[1] + '"')
                restore(p, before)
                report['calculator_state_restored'] = True
                p.send(0x13)
                p.attached = False
                p.pump(.2)
                p.command('uscreen off' if 'USB_SCREEN=OFF ' in initial else 'uscreen on')
                report['final'] = p.status()
                healthy(report['final'], args.build_id)
                assert 'SERVICE=CLOSED' in report['final'] and 'M61_ACTIVE=0' in report['final']
            except BaseException as error:
                report.update(result='FAIL', cleanup_error=repr(error))
            report['frames_crc_verified'] = len(p.frames)
            (args.output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            (args.output_dir / 'terminal.bin').write_bytes(p.text)
    assert report['result'] == 'PASS', report
    print(json.dumps({key: report[key] for key in ('result', 'median_seconds', 'repeat_median_seconds', 'frames_crc_verified')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
