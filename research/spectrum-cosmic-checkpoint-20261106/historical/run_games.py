"""One bounded two-game Spectrum phase; import performs no device I/O."""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.build/spectrum-hardware-tests/run-20261105'))
import xip_named_run_v3 as base
from hil_c5_stack import read_file

need, Hold, sha = base.need, base.Hold, base.sha
FOLDER = base.FOLDER
FIXTURES = ('SPMN', 'SPCP')
NAMES = {'SPTIME.APP', *(name + suffix for name in FIXTURES for suffix in ('.Z80', '.ULP'))}

def source_pins():
    return {**base.source_pins(), str(Path(__file__).resolve()): sha(__file__)}

def validate_plan(plan):
    need(plan.get('role') == 'spectrum-games' and plan['folder'] == FOLDER, 'Changed phase namespace')
    need(plan['uid'] == base.UID and plan['indexes'] == [0, 1], 'Changed device or game count')
    need(set(plan['files']) == NAMES, 'Changed writable file set')
    need([e['id'] for e in plan['games']] == list(FIXTURES), 'Changed game fixtures')
    expected = plan['expected']
    need(set(expected) == {'build', 'crc', 'bytes'} and
         all(re.fullmatch('[0-9A-F]{8}', expected[k]) for k in ('build', 'crc')) and
         1000000 < expected['bytes'] < 1800000, 'Invalid exact firmware identity')
    for name, item in plan['files'].items():
        path = item['local']
        need(sha(path) == item['sha256'] == plan['pins'][path], 'Changed fixture: ' + name)
        need(0 < Path(path).stat().st_size <= 65535, 'Fixture exceeds fsput limit')
    for game in plan['games']:
        need(game['ulaplus'] in (0, 1), 'Invalid palette mode')
        x0, x1, y0, y1 = game['hud_roi_bytes']
        need(0 <= x0 < x1 <= 32 and 0 <= y0 < y1 <= 192, 'Invalid game HUD ROI')
        need(re.fullmatch('[0-9A-F]{8}', game['hud_signature']), 'Invalid HUD signature')
    for key in ('supplier_receipt', 'supplier_release', 'prior_probe', 'production_app'):
        item = plan[key]
        need(sha(item['local']) == item['sha256'] == plan['pins'][item['local']], 'Changed supplier/application input')
    supplier = json.loads(Path(plan['supplier_receipt']['local']).read_text())
    release = json.loads(Path(plan['supplier_release']['local']).read_text())
    need(supplier['status'] == 'PASS' and supplier['uid'] == base.UID and
         supplier['cdc_descriptor_closed'] and not supplier['port_close_errors'] and
         supplier['program_ip_cwd_alarm_preserved'] and supplier['rtc_trajectory_verified'], 'Supplier native proof incomplete')
    need(release['lease'] == 'released' and release['all_ports_closed'] and release['named_port_holders'] == 0 and
         release['firmware'] == expected and release['CLOCK_receipt_sha256'] == plan['supplier_receipt']['sha256'], 'Supplier release differs')
    base.guard_status(supplier['status_after'], expected)

def listing_records(report):
    return tuple(line.rstrip('\r') for line in report.splitlines() if re.match(r'^[df]\t', line))

def listing_names(records):
    return {line.split('\t')[-1].rstrip('/') for line in records}

def restore_files(p, g, created, original_probe, probe_changed):
    need(created <= NAMES - {'SPTIME.APP'}, 'Cleanup includes an unowned filename')
    remaining = listing_names(listing_records(p.command(f'ls "{FOLDER}"')))
    backup = g.out / 'verified-backup'
    backup.mkdir(exist_ok=True)
    g.final['fixture_backups'] = {}
    g.final['removed_created_files'] = []
    for name in sorted(created & remaining):
        data = read_file(p, FOLDER + '/' + name)
        target = backup / name
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        need(sha(target) == digest and target.read_bytes() == data, 'Host backup differs before cleanup')
        g.final['fixture_backups'][name] = {'sha256': digest, 'bytes': len(data)}
        p.command(f'rm "{FOLDER}/{name}"')
        g.final['removed_created_files'].append(name)
    if probe_changed:
        need(original_probe is not None, 'No verified original probe for restore')
        base.write_file(p, FOLDER + '/SPTIME.APP', original_probe)
        g.final['restored_probe_sha256'] = hashlib.sha256(original_probe).hexdigest()
    final = listing_records(p.command(f'ls "{FOLDER}"'))
    need(not (created & listing_names(final)), 'Created fixtures remain after cleanup')
    return final

def framebuffer(record):
    begin = re.findall(rb'SPBEGIN GAME\r?\n(.*?)SPEND\r?\n', record, re.S)
    need(len(begin) == 1, 'Missing or duplicate game framebuffer')
    rows = re.findall(rb'(?m)^SPDATA ([0-9A-F]{4}) ([0-9A-F]{64})\r?\n', begin[0])
    need(len(rows) == 244, 'Incomplete framebuffer')
    data = bytearray()
    for at, encoded in rows:
        need(int(at, 16) == len(data), 'Out-of-order framebuffer block')
        data.extend(bytes.fromhex(encoded.decode()))
    need(len(data) == 7808, 'Wrong framebuffer length')
    need(all(c < 64 for c in data[6144:7680]), 'Invalid palette index')
    return bytes(data)

def scene_signature(data, game):
    x0, x1, y0, y1 = game['hud_roi_bytes']
    value = 2166136261
    for y in range(y0, y1):
        for x in range(x0, x1):
            value = ((value ^ data[y * 32 + x]) * 16777619) & 0xffffffff
    signature = f'{value:08X}'
    need(signature == game['hud_signature'], 'Game HUD differs: ' + game['id'])
    return signature

class GamesPort(base.SpectrumPort):
    def native_return(self, physical):
        own_browser = False
        for _ in range(5):
            status = self.status()
            service, path, result = base.foreground(status)
            if service == 'CLOSED':
                base.guard_status(status, base.EXPECTED, physical)
                self.commands()
                return status
            if service == 'BROWSER' and own_browser:
                need(base.field(status, 'RUNTIME') == 'NONE', 'Unexpected browser runtime')
                self.wire(27)
                self.pump(.2)
                continue
            owned = {FOLDER + '/SPTIME.APP'}
            if getattr(self, 'ordinary_opened', False):
                owned.add(FOLDER + '/SPECTRUM.APP')
            need(path in owned, 'Foreign foreground; no escape sent')
            if base.field(status, 'RUNTIME') == 'APP':
                self.wire(27)
                self.pump(.3)
                continue
            need(base.field(status, 'RUNTIME') == 'NONE' and service in ('VIEWER', 'BROWSER'), 'Unexpected owned foreground')
            if service == 'VIEWER':
                need(result.startswith('APP finished;'), 'Owned APP did not finish normally')
            self.send(b'\x1e')
            self.wire(27)
            self.pump(.2)
            own_browser = True
        raise Hold('Native return exceeds five bounded escapes')

    def open_fixture(self, game):
        start = len(self.text)
        self.ui(ord('o'))
        target = (game['id'] + '.Z80').encode()
        for _ in range(64):
            rows = base.menu_rows(self.text[start:])
            need(rows and rows[-1][0] == b'Snapshot', 'Snapshot chooser missing')
            label = rows[-1][4]
            if label == target:
                start = len(self.text)
                self.wire(13)
                self.match(rb'SPPAL mode=' + str(game['ulaplus']).encode() + rb'\r?\n', start)
                self.match(rb'SPRUN\r?\n', start)
                return
            start = len(self.text)
            self.ui(0xb6)
            following = base.menu_rows(self.text[start:])
            need(following and following[-1][4] != label, 'Owned snapshot absent')
        raise Hold('Snapshot chooser exceeds finite entry cap')

def run_port(g):
    validate_plan(g.j)
    base.EXPECTED = g.j['expected']
    before = None
    changed = {}
    created = set()
    original_probe = None
    probe_changed = False
    initial_rows = None
    clean = False
    with GamesPort(g) as p:
        status = p.status()
        physical = base.guard_status(status, base.EXPECTED)
        supplier = json.loads(Path(g.j['supplier_receipt']['local']).read_text())
        need(p.binding == supplier['native_binding'], 'USB binding changed since supplier handoff')
        rtc_before = {key: base.field(status, key) for key in ('RTC', 'RTC_SET', 'RTC_PPM')}
        rtc_started = base.continuous()
        p.commands()
        need(base.field(p.command('identity'), 'UID') == base.UID, 'Wrong PicoCalc identity')
        before = base.calc(p)
        try:
            listing = p.command(f'ls "{FOLDER}"')
            initial_rows = listing_records(listing)
            existing = listing_names(initial_rows)
            need({'SPTIME.APP', 'SPECTRUM.APP'} <= existing, 'Owned application namespace absent')
            original_probe = read_file(p, FOLDER + '/SPTIME.APP')
            need(hashlib.sha256(original_probe).hexdigest() == g.j['prior_probe']['sha256'], 'Prior probe differs from supplier expectation')
            (g.out / 'prior-SPTIME.APP').write_bytes(original_probe)
            need(sha(g.out / 'prior-SPTIME.APP') == g.j['prior_probe']['sha256'], 'Original probe backup differs')
            item = g.j['files']['SPTIME.APP']
            probe_changed = True
            base.write_file(p, FOLDER + '/SPTIME.APP', Path(item['local']).read_bytes())
            changed['SPTIME.APP'] = item['sha256']
            # Check actual free SRAM before spending time transferring fixtures.
            start = len(p.text)
            p.open_app('SPTIME.APP')
            p.menu(start)
            base.validate_root(p.text[start:], initial=True)
            initialized = p.status()
            need(base.field(initialized, 'RUNTIME') == 'APP' and
                 base.field(initialized, 'APP_EXTERNAL_BYTES') == '1892352', 'Preflight RAM did not initialize')
            p.save('games-preflight')
            p.native_return(physical)
            for name in sorted(NAMES - {'SPTIME.APP'}):
                item = g.j['files'][name]
                data = Path(item['local']).read_bytes()
                if name in existing:
                    need(read_file(p, FOLDER + '/' + name) == data, 'Existing fixture differs: ' + name)
                else:
                    created.add(name)
                    base.write_file(p, FOLDER + '/' + name, data)
                    changed[name] = item['sha256']
            start = len(p.text)
            p.open_app('SPTIME.APP')
            p.menu(start)
            base.validate_root(p.text[start:], initial=True)
            initialized = p.status()
            need(base.field(initialized, 'RUNTIME') == 'APP' and
                 base.field(initialized, 'APP_EXTERNAL_BYTES') == '1892352', 'Probe did not initialize')
            p.save('games-initial')
            g.final['games'] = []
            for game in g.j['games']:
                p.open_fixture(game)
                p.pump(2)
                for _ in range(10):
                    p.wire(ord('p'))
                    p.pump(.2)
                p.pump(2.4)
                p.pause()
                record = bytes(p.text)
                data = framebuffer(record)
                signature = scene_signature(data, game)
                whole, steady = base.measured_timing(record)
                p.save('game-' + game['id'])
                (g.out / (game['id'] + '-frame.bin')).write_bytes(data)
                g.final['games'].append({'title': game['title'], 'fixture': game['id'],
                    'whole': whole, 'steady': steady, 'hud_signature': signature,
                    'frame_sha256': hashlib.sha256(data).hexdigest()})
            p.native_return(physical)
            production = read_file(p, FOLDER + '/SPECTRUM.APP')
            need(hashlib.sha256(production).hexdigest() == g.j['production_app']['sha256'], 'Ordinary APP changed')
            p.ordinary_opened = True
            p.open_app('SPECTRUM.APP')
            p.pump(2)
            need(base.field(p.status(), 'RUNTIME') == 'APP', 'Ordinary APP initialization failed')
            p.wire(ord('r'))
            p.pump(2)
            need(base.field(p.status(), 'RUNTIME') == 'APP', 'Ordinary APP run failed')
            g.final['ordinary_app_smoke'] = True
            g.final['ordinary_app_sha256'] = g.j['production_app']['sha256']
        finally:
            g.cleanup()
            try:
                p.native_return(physical)
                p.command('fsput cancel')
                if initial_rows is not None:
                    final_rows = restore_files(p, g, created, original_probe, probe_changed)
                    need(set(final_rows) == set(initial_rows), 'Owned namespace listing changed after cleanup')
                    g.final['namespace_preserved'] = True
                status = p.status()
                base.guard_status(status, base.EXPECTED, physical)
                after = base.calc(p)
                base.equal_calc(before, after)
                rtc_after = {key: base.field(status, key) for key in ('RTC', 'RTC_SET', 'RTC_PPM')}
                need(all(rtc_before[key] == rtc_after[key] for key in ('RTC_SET', 'RTC_PPM')), 'RTC setter count or rate changed')
                actual = (datetime.datetime.fromisoformat(rtc_after['RTC']) - datetime.datetime.fromisoformat(rtc_before['RTC'])).total_seconds()
                expected = base.elapsed(rtc_started, base.continuous())
                need(abs(actual - expected) <= 3, 'RTC trajectory differs from elapsed continuous time')
                g.final.update(rtc_preserved=True, rtc_before=rtc_before, rtc_after=rtc_after,
                               continuous_seconds=expected, rtc_elapsed_seconds=actual)
                g.final.update(status_after=status, calculator_before=before, calculator_after=after,
                               calculator_preserved=True)
                clean = True
            finally:
                g.final.update(changed_sd_files=changed, cleanup_native_verified=clean)

def run(g):
    failure = None
    try:
        run_port(g)
    except BaseException as error:
        failure = error
    try:
        need(g.final.get('cdc_descriptor_closed') and not g.final.get('port_close_errors'), 'CDC close unproven')
        g.noholders(g.final['native_binding'])
        need(g.final.get('cleanup_native_verified') and g.final.get('calculator_preserved'), 'Native handoff unproven')
        g.final['lease'] = 'released'
    except BaseException as error:
        g.final['handoff_error'] = repr(error)
        if failure is None:
            failure = error
    if failure is not None:
        raise failure

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pins', action='store_true')
    parser.add_argument('--phase', type=Path)
    parser.add_argument('--grant', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.pins:
        print(json.dumps(source_pins(), indent=2))
        return
    need(args.phase and args.grant and args.out, 'Explicit phase, grant and output required')
    validate_plan(json.loads(args.phase.read_text()))
    g = base.SpectrumGate(args.phase, args.grant, args.out)
    g.final['lease'] = 'closed_port_needs_attention'
    try:
        run(g)
    except BaseException as error:
        g.finish(False, repr(error))
        raise
    else:
        g.finish(True)

if __name__ == '__main__':
    main()
