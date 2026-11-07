#!/usr/bin/env python3
"""One bounded, single-use kernel APP measurement; no import-time device I/O."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import stat
import subprocess
import sys
import termios
import time

import native_transport as n

HERE = Path(__file__).resolve().parent
FIELDS = ('BUILD', 'ACTUAL', 'EXPECTED', 'IMAGE', 'FIRMWARE_CRC', 'BOOTS', 'CRASH',
          'SERVICE', 'RUNTIME', 'UI', 'RUN', 'BUSY', 'USB_DISK', 'SYS_HZ', 'PERI_HZ',
          'PHYSICAL_KEYS', 'SETTINGS_WRITES', 'RTC_SET')
COUNTERS = ('ERRORS', 'QPI_FALLBACKS', 'TAIL_TIMEOUTS', 'CRC_ERRORS', 'DMA_TIMEOUTS',
            'LCD_ERRORS', 'SD_SPEED_FALLBACKS', 'SD_PROBE_FAILURES', 'I2C_TIMEOUTS',
            'I2C_ABORTS', 'SCREEN_ERRORS')
RECORD = re.compile(rb'AI_QKERNEL mode=(\d+) cols=(\d+) rows=(\d+) loops=(\d+) repeat=(\d+) us=(\d+) checksum=([0-9A-F]{8}) correct=(\d+)')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def field(s, name):
    m = re.search(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'=([^ \r\n]+)', s)
    need(m is not None, 'Missing native field ' + name)
    return m[1]


def filtered(s):
    # No RTC, registers, calculator contents, settings snapshots or raw C5 files.
    result = {k: field(s, k) for k in FIELDS}
    result['error_counters'] = {k: int(field(s, k)) for k in COUNTERS}
    fs = re.findall(r'FS_ERROR=\[([^\r\n\]]*)\]', s)
    need(len(fs) == 1, 'Missing/ambiguous FS diagnostic')
    result['fs_error'] = fs[0]
    lcd = re.findall(r'(?m)^LCD=ST7365P [^\r\n]*', s)
    need(len(lcd) == 1, 'Missing LCD diagnostic')
    result['lcd_spi_hz'] = int(field(lcd[0], 'SPI_HZ'))
    return result


def health(s, phase, closed=True):
    f = filtered(s)
    for k, v in dict(BUILD='CDB70C8F', ACTUAL='7ED9C260', EXPECTED='7ED9C260',
                     IMAGE='1538304', FIRMWARE_CRC='valid', BOOTS='4', CRASH='NONE',
                     RUN='0', BUSY='0', USB_DISK='0', SYS_HZ='125000000',
                     PERI_HZ='48000000', SETTINGS_WRITES='0', RTC_SET='0').items():
        need(f[k] == v, 'Unexpected native ' + k)
    need(not any(f['error_counters'].values()), 'Hardware error counter')
    need(f['fs_error'] == '', 'New FS error')
    need(f['lcd_spi_hz'] == 12000000, 'Unexpected LCD clock')
    if closed:
        keys = int(f['PHYSICAL_KEYS'])
        n.readiness(s, 'CDB70C8F', '7ED9C260', physical_keys=keys)
    else:
        need(f['RUNTIME'] == 'NONE', 'APP did not finish')
        need('PATH=[' + phase['destination'] + ']' in s, 'Foreign foreground')
        need(f['SERVICE'] in ('VIEWER', 'CONSOLE'), 'Unexpected result foreground')
        need('APP finished;' in s, 'APP return not normal')
    return f


def binding():
    raw = subprocess.run(['/usr/sbin/ioreg', '-a', '-r', '-c', 'IOUSBHostDevice', '-l', '-w', '0'],
                         capture_output=True, check=True, timeout=5).stdout
    found = []

    def walk(nodes, ancestors=()):
        for node in nodes:
            chain = ancestors + (node,)
            if node.get('IOCalloutDevice') == n.PORT:
                found.append(chain)
            walk(node.get('IORegistryEntryChildren', []), chain)

    walk(plistlib.loads(raw))
    need(len(found) == 1, 'Ambiguous or absent CDC')
    chain = found[0]
    leaf = chain[-1]
    device = [x for x in chain if x.get('IOObjectClass') == 'IOUSBHostDevice'][-1]
    need(device.get('USB Serial Number') == n.UID, 'Wrong native USB UID')
    tty = n.PORT.replace('/cu.', '/tty.')
    need(leaf.get('IODialinDevice') == tty, 'Wrong tty sibling')
    for path in (n.PORT, tty):
        need(stat.S_ISCHR(os.stat(path).st_mode), 'Not a character device')
    return dict(uid=n.UID, cu=n.PORT, tty=tty, usb_entry=device['IORegistryEntryID'],
                location=device['locationID'], session=device['sessionID'],
                cdc_entry=leaf['IORegistryEntryID'], cu_rdev=os.stat(n.PORT).st_rdev,
                tty_rdev=os.stat(tty).st_rdev)


def noholders(b):
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    q = lib.proc_listpidspath
    q.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p,
                  ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    q.restype = ctypes.c_int
    owners = []
    for path in (b['cu'], b['tty']):
        size = q(1, 0, os.fsencode(path), 0, None, 0)
        need(0 < size <= 1048576, 'Holder query failed')
        buf = (ctypes.c_int * (size // 4 + 32))()
        count = q(1, 0, os.fsencode(path), 0, buf, ctypes.sizeof(buf))
        need(0 <= count < ctypes.sizeof(buf) and count % 4 == 0, 'Holder query truncated')
        owners.extend((path, pid) for pid in list(buf)[:count // 4])
    need(not owners, 'Named CDC holders ' + repr(owners))
    return []


def records(raw):
    found = []
    for m in RECORD.finditer(raw):
        mode, cols, rows, loops, repeat, us = map(int, m.groups()[:6])
        found.append(dict(mode=mode, cols=cols, rows=rows, loops=loops, repeat=repeat,
                          us=us, checksum=m[7].decode(), correct=int(m[8])))
    return found


def compare(raw, host):
    got, reference = records(raw), records(host)
    need(len(got) == len(reference) == 18, 'Expected exactly 18 complete records')
    need(b'AI_QKERNEL DONE correct=1' in raw, 'Missing DONE')
    for a, b in zip(got, reference):
        need(a['us'] > 0, 'Zero duration')
        need({k: v for k, v in a.items() if k != 'us'} ==
             {k: v for k, v in b.items() if k != 'us'}, 'Host/device oracle mismatch')
    return got


def validate(path):
    p = json.loads(path.read_text())
    need(p['controller_sha256'] == n.sha(__file__), 'Controller changed')
    need(p['helper_sha256'] == n.sha(n.__file__), 'Transport changed')
    for item in p['pins']:
        need(n.sha(item['path']) == item['sha256'], 'Pinned input changed')
    need(p['authority'] == 'direct human user' and p['user_quote'] == 'вот ещё советы, попробуем?', 'Missing task authority')
    need(p['root_technical_review_claimed'] is False, 'Unwarranted review claim')
    need(p['deadline_seconds'] == 150, 'Unbounded deadline')
    need(time.time() <= p['start_before'], 'Stale phase')
    need(re.fullmatch(r'/Apps/QK-[A-F0-9]{12}/QKERNEL.APP', p['destination']), 'Wrong owned path')
    return p


def worker(phasepath):
    phase = validate(phasepath)
    out = Path(phase['output'])
    out.mkdir(exist_ok=False)
    (out / 'attempt.json').write_text(json.dumps(dict(pid=os.getpid(), phase_sha256=n.sha(phasepath))))
    receipt = dict(status='HOLD', phase_sha256=n.sha(phasepath), save_or_restore=False,
                   flash_writes=0, model_writes=0, clock_writes=0, rtc_writes=0,
                   settings_writes=0, root_technical_review_claimed=False)
    p = None
    try:
        expected = json.loads(Path(phase['release_path']).read_text())['native_binding']
        now = binding()
        need(now == expected, 'Stale USB/native binding')
        noholders(now)
        receipt['native_binding'] = now
        # Snapshot only host tty flags for reversible fd cleanup, never device state.
        p = n.Serial(time.monotonic() + phase['deadline_seconds'])
        need(os.fstat(p.fd).st_rdev == now['cu_rdev'] and binding() == now, 'Binding changed at open')
        receipt['before'] = health(p.status(), phase)
        p.commands()
        n.identity(p)
        owned = []
        n.create_owned(p, phase['destination'].rsplit('/', 1)[0], owned, out)
        receipt['installed'] = n.upload(p, phase['destination'], Path(phase['payload']).read_bytes(), out / 'upload-fault.bin')
        receipt['ready_before_launch'] = health(p.status(), phase)
        p.commands()
        p.data.clear()
        p.send(('run "' + phase['destination'] + '"\r').encode())
        try:
            raw = p.wait(lambda b: n.PROMPT.search(b), 75)
        finally:
            # Preserve measured records before any UI return or fault response.
            (out / 'benchmark-raw.bin').write_bytes(bytes(p.data))
        receipt['records'] = compare(raw, Path(phase['host_log']).read_bytes())
        need(re.search(rb'APP_RESULT=0\b', raw), 'Nonzero or missing APP result')
        (out / 'records.json').write_text(json.dumps(receipt['records'], indent=2) + '\n')
        s = p.status()
        if field(s, 'SERVICE') != 'CLOSED':
            receipt['owned_return'] = health(s, phase, closed=False)
            # Proven finished owned result page only. No input to an unknown APP.
            p.send(b'\x1e\x1b')
            p.pump(.3)
            s = p.status()
            if field(s, 'SERVICE') == 'BROWSER' and field(s, 'RUNTIME') == 'NONE':
                need('PATH=[' + phase['destination'].rsplit('/', 1)[0] + ']' in s or
                     'PATH=[' + phase['destination'] + ']' in s, 'Foreign browser')
                p.send(b'\x1b')
                p.pump(.3)
                s = p.status()
        receipt['after'] = health(s, phase)
        receipt['status'] = 'PASS'
        receipt['app_retained'] = phase['destination']
    except BaseException as error:
        # First fault stops. No retry, reset, cleanup action, replay or recovery.
        receipt['error'] = str(error)
    finally:
        if p is not None:
            p.close()
        receipt['cdc_closed'] = p is None or p.fd < 0
        try:
            now = binding()
            need(now == receipt.get('native_binding', now), 'Binding changed at release')
            receipt['holders'] = noholders(now)
        except BaseException as error:
            receipt['status'] = 'HOLD'
            receipt['release_error'] = str(error)
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(status=receipt['status'], error=receipt.get('error'), output=str(out))), flush=True)
    return 0 if receipt['status'] == 'PASS' else 1


def supervise(phasepath):
    phase = validate(phasepath)
    with phasepath.with_suffix('.USED').open('x') as f:
        f.write(str(os.getpid()))
    start = time.time()
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(phasepath)],
                             start_new_session=True)
    killed = False
    try:
        code = child.wait(timeout=phase['deadline_seconds'] + 10)
    except subprocess.TimeoutExpired:
        killed = True
        os.killpg(child.pid, signal.SIGTERM)
        try:
            code = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait(timeout=3)
    result = dict(pid=child.pid, exit_code=code, worker_reaped=True, timed_out=killed,
                  elapsed_seconds=time.time() - start, phase_sha256=n.sha(phasepath))
    phasepath.with_suffix('.supervisor.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return code


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--worker', action='store_true')
    ap.add_argument('phase', type=Path)
    args = ap.parse_args()
    raise SystemExit(worker(args.phase) if args.worker else supervise(args.phase))
