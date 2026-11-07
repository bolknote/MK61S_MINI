#!/usr/bin/env python3
"""One C5 completion observation, no terminal commands or foreground input."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import run_kernel as k


def diagnostic_raw(raw):
    # Preserve diagnostic wire evidence before interpreting health. Human asked
    # for no old calculator/RTC/settings backups, so redact those unrelated values.
    raw = re.sub(rb'(?m)^UI=([A-Z]+)[^\r\n]*', rb'UI=\1 [settings redacted]', raw)
    raw = re.sub(rb'\b(?:X_RAW|X)=\[[^\r\n\]]*\]', b'X=[redacted]', raw)
    raw = re.sub(rb'\bIP=[^ \r\n]+', b'IP=[redacted]', raw)
    raw = re.sub(rb'\bRTC=[^ \r\n]+', b'RTC=[redacted]', raw)
    raw = re.sub(rb'\bRTC_PPM=[^ \r\n]+', b'RTC_PPM=[redacted]', raw)
    return raw


def validate(path):
    p = json.loads(path.read_text())
    k.need(time.time() <= p['start_before'], 'Stale completion')
    k.need(p['controller_sha256'] == k.n.sha(__file__), 'Changed completion')
    for item in p['pins']:
        k.need(k.n.sha(item['path']) == item['sha256'], 'Changed pinned completion input')
    k.need(p['deadline_seconds'] == 30 and p['operation'] == 'one_C5_only', 'Unexpected scope')
    return p


def worker(path):
    phase = validate(path)
    out = Path(phase['output']);out.mkdir(exist_ok=False)
    r = dict(status='HOLD', operation='one_C5_only', phase_sha256=k.n.sha(path),
             root_technical_review_claimed=False, serial_commands=0,
             foreground_input=0, app_runs=0, device_state_restored=False,
             diagnostic_raw_redactions=['calculator X/IP', 'RTC/time correction', 'UI settings'])
    p = None
    try:
        expected = json.loads(Path(phase['release']).read_text())['native_binding']
        now = k.binding();k.need(now == expected, 'Stale binding');k.noholders(now)
        r['native_binding'] = now
        p = k.n.Serial(time.monotonic() + 30)
        k.need(os.fstat(p.fd).st_rdev == now['cu_rdev'] and k.binding() == now, 'Changed binding at open')
        try:
            status = p.status()
        finally:
            # Also preserve partial evidence on timeout/malformed response.
            (out / 'native-diagnostic-raw.bin').write_bytes(diagnostic_raw(bytes(p.data)))
        r['observed'] = k.filtered(status)
        f = r['observed']
        for name, value in dict(BUILD='CDB70C8F', ACTUAL='7ED9C260', EXPECTED='7ED9C260',
                                IMAGE='1538304', FIRMWARE_CRC='valid', BOOTS='4', CRASH='NONE',
                                SYS_HZ='125000000', PERI_HZ='48000000', RUN='0', BUSY='0',
                                USB_DISK='0', RUNTIME='NONE').items():
            k.need(f[name] == value, 'Unexpected native ' + name)
        k.need(not any(f['error_counters'].values()) and f['lcd_spi_hz'] == 12000000, 'New hardware diagnostic')
        foreground = re.findall(r'PATH=\[([^\r\n\]]*)\]', status)
        k.need(len(foreground) == 1, 'Ambiguous foreground');r['foreground'] = foreground[0]
        if f['SERVICE'] == 'CLOSED' and f['fs_error'] == '':
            r['status'] = 'PASS_CLOSED'
        elif f['fs_error'] == 'File or directory not found (4)' and f['SERVICE'] == 'BROWSER' and foreground[0] in phase['owned_foregrounds']:
            r['status'] = 'RELEASED_WITH_KNOWN_FS4_BROWSER'
        else:
            r['status'] = 'OBSERVED_STOP'
    except BaseException as error:
        r['error'] = str(error)
    finally:
        if p is not None:p.close()
        r['cdc_closed'] = p is None or p.fd < 0
        try:
            k.need(k.binding() == r.get('native_binding'), 'Binding changed at release')
            r['holders'] = k.noholders(r['native_binding'])
        except BaseException as error:r['status'] = 'HOLD';r['release_error'] = str(error)
        (out / 'receipt.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(r), flush=True)
    return 0 if r['status'] in ('PASS_CLOSED', 'RELEASED_WITH_KNOWN_FS4_BROWSER') else 1


def main(path):
    phase = validate(path)
    with path.with_suffix('.USED').open('x') as f:f.write(str(os.getpid()))
    child = subprocess.Popen([sys.executable, __file__, '--worker', str(path)], start_new_session=True)
    killed = False
    try:code = child.wait(timeout=40)
    except subprocess.TimeoutExpired:
        killed = True;os.killpg(child.pid, signal.SIGTERM)
        try:code = child.wait(timeout=2)
        except subprocess.TimeoutExpired:os.killpg(child.pid, signal.SIGKILL);code = child.wait(timeout=2)
    r = dict(pid=child.pid, exit_code=code, worker_reaped=True, timed_out=killed)
    path.with_suffix('.supervisor.json').write_text(json.dumps(r, indent=2) + '\n')
    return code


if __name__ == '__main__':
    ap = argparse.ArgumentParser();ap.add_argument('--worker', action='store_true');ap.add_argument('phase', type=Path);a = ap.parse_args()
    raise SystemExit(worker(a.phase) if a.worker else main(a.phase))
