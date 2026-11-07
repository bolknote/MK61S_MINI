"""Install only the accepted complete libc fixture, retaining the current resident.

No hardware I/O at import. Requires a fresh Root current-image acceptance,
exact discardable sector bounds, explicit reset permission and one-use Go.
Reads back only the new fixture and public factory ROM. No previous firmware,
settings, files, calculator state or RTC is inventoried, copied or restored.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import termios
import fcntl
import controller as c
from device_guard import Gate, Port, UID, need, sha, dump, stable_termios, TIOCNXCL

HERE = Path(__file__).resolve().parent
ROM_SHA = 'ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'


def stable_crash(body):
    # The retained record updates this field after the explicitly planned
    # reboot. Registers, sequence, origin build, fault reason and flags remain
    # byte-exact; a new crash is never accepted as the known CLOCK280 record.
    raw = re.sub(rb'RESET_AFTER_REBOOT=[0-9A-F]{8}', b'RESET_AFTER_REBOOT=PLANNED', body)
    need(raw != body and body.count(b'RESET_AFTER_REBOOT=') == 1, 'Malformed retained reset field')
    return raw


def fixture_bounds(t, resident_bytes):
    base = t['fixture_base']; end = base + t['fixture']['bytes']; erase_end = (end + 4095) & ~4095
    need(base % 4096 == 0 and 0x10000000 + resident_bytes <= base < end <= erase_end <= 0x101c0000,
         'Fixture outside disposable application range')
    need(all(erase_end <= lo or base >= hi for lo, hi in t['protected_ranges']), 'Protected erase range')
    need(erase_end <= 0x10180000 or base >= 0x10182000, 'Historical MathQFP reserve')
    return base, end, erase_end


def precheck(phase, grant, output):
    j = json.loads(phase.read_text()); gr = json.loads(grant.read_text())
    need(j['schema'] == 1 and j['scope'] == 'm0-libc-batch-fixture-install' and j['action'] == 'flash' and
         j['uid'] == UID and j['owner'] == c.OWNER, 'Wrong fixture install scope')
    need(j['Flash_writes'] == 1 and j['reset_commands'] == 2 and j['RTC_setters'] == 0 and
         j['previous_state_capture'] is False and j['previous_state_restore'] is False, 'Changed install bounds')
    need(gr['status'] == 'ROOT_EXPLICIT_PHASE_GO' and gr['executor'] == c.OWNER and gr['uid'] == UID and
         gr['phase_sha256'] == sha(phase) and gr['reset_and_old_state_discard_authorized'] is True,
         'No exact Root install/reset/discard authorization')
    need(j['argv'] == [str(Path(sys.executable).resolve()), str(Path(__file__).resolve()),
         '--phase', str(phase), '--grant', str(grant), '--output', str(output)] and
         j['cwd'] == str(Path.cwd().resolve()) == str(c.ROOT), 'Unbound executable/argv/cwd')
    need(c.source_closure() <= set(gr['source_pins']), 'Unpinned imported installer source')
    for path, digest in gr['source_pins'].items(): need(sha(path) == digest, 'Changed reviewed source ' + path)
    for path, digest in j['pins'].items(): need(sha(path) == digest, 'Changed installer artifact ' + path)
    for key in ('current_image_acceptance', 'previous_receipt', 'previous_supervisor', 'template', 'layout', 'picotool'):
        need(sha(j[key]) == j['pins'][j[key]], 'Unbound install input ' + key)
    need(j['pins'][str(Path(sys.executable).resolve())] == sha(sys.executable), 'Python executable unpinned')
    current = json.loads(Path(j['current_image_acceptance']).read_text())
    need(current['status'] == 'ROOT_ACCEPTED_M0_LIBC_CURRENT_IMAGE' and current['uid'] == UID and
         current['expected'] == j['expected'] and current['usb_binding'] == j['usb_binding'] and
         current['boot_fields'] == j['boot_fields'] and current['context_fields'] == j['context_fields'] and current['template_sha256'] == sha(j['template']) and
         gr['current_image_acceptance_sha256'] == sha(j['current_image_acceptance']), 'Stale current-image handoff')
    c.predecessor(j, gr)
    t = json.loads(Path(j['template']).read_text()); layout = json.loads(Path(j['layout']).read_text())
    need(current['layout_sha256'] == sha(j['layout']) == gr['accepted_layout_sha256'] and
         gr['erase_contents_discard_authorized'] is True, 'Fixture sectors not explicitly accepted for overwrite')
    need(current['resident_BIN_sha256'] == t['candidate_firmware']['sha256'] and
         current['resident_ELF_sha256'] == t['candidate_ELF']['sha256'], 'Actual resident/source differs')
    need(t['candidate_build'].upper() == j['expected']['build'].upper() and
         t['candidate_crc'].upper() == j['expected']['crc'].upper() and
         t['candidate_firmware']['bytes'] == j['expected']['bytes'], 'Resident status/image mismatch')
    for ref in (t['fixture'], t['candidate_firmware'], t['candidate_ELF']):
        need(c.pin(ref['path']) == ref and j['pins'][ref['path']] == ref['sha256'], 'Unpinned fixture/image')
    base, end, erase_end = fixture_bounds(t, j['expected']['bytes'])
    need(gr['accepted_erase'] == j['accepted_erase'] == dict(begin=base, end_exclusive=erase_end) and
         layout['fixture_begin'] == hex(base) and layout['fixture_erase_end'] == hex(erase_end) and layout['no_overlap'],
         'Changed complete erase-sector bounds')
    need(set(j['boot_fields']) == set(j['after_boot_fields']) == {'BOOTS', 'RESET_REASON', 'BOOT_WATCHDOG'},
         'Incomplete planned boot context')
    need(j['after_boot_fields']['BOOTS'] == str(int(j['boot_fields']['BOOTS']) + 1), 'Only one planned native boot allowed')
    need(j['expected']['crash'] == 'NONE', 'This new batch does not admit an unknown retained crash')
    need(gr['accepted_extension'] == t['extension_requires_independent_root_disposable_acceptance'], 'New fixture extension not independently accepted')
    if j['expected']['crash'] == 'AVAILABLE':
        need(current['known_crash_report_sha256'] == j['known_crash_report_sha256'], 'Known crash unbound')
    return j, t


def execute(g, t):
    j = g.j; before_crash = None
    with Port(g) as p:
        physical = c.admit(p, g)
        if j['expected']['crash'] == 'AVAILABLE':
            before_crash = c.crash_report_body(p.command('crash show'))
            need(hashlib.sha256(before_crash).hexdigest() == j['known_crash_report_sha256'], 'Crash changed before reset')
            (g.out / 'known-crash-before.bin').write_bytes(before_crash)
        location = p.binding['location']; old_binding = p.binding.copy()
        # The qualified exp-physical delivery/termios sequence, with the
        # fresh known-crash guard replacing its historical CRASH=NONE guard.
        c.status_guard(p.status(), j, physical)
        termios.tcsetattr(p.fd, termios.TCSANOW, p.saved)
        need(stable_termios(termios.tcgetattr(p.fd)) == stable_termios(p.saved), 'Pre-DFU termios differs')
        fcntl.ioctl(p.fd, TIOCNXCL); p.exclusive = False; p.restored_for_dfu = True
        g.final['reset_commands'] = 1
        p.send(b'dfu\r'); p.wait_owned_dfu_delivery()
    g.wait_rom(location); rom_binding = g.rom_identity(location); g.native_absent(old_binding)
    g.save_range(0, 0x4000, g.out / 'factory-rom.bin')
    need(sha(g.out / 'factory-rom.bin') == ROM_SHA, 'Factory ROM differs from qualified v3/B2')
    base = t['fixture_base']; end = base + t['fixture']['bytes']
    g.final.update(Flash_writes=1, Flash_readback_verified=False)
    g.picotool(['load', '-v', t['fixture']['path'], '-t', 'bin', '-o', hex(base)])
    g.save_range(base, end, g.out / 'new-fixture-readback.bin')
    need((g.out / 'new-fixture-readback.bin').read_bytes() == Path(t['fixture']['path']).read_bytes(),
         'New fixture readback differs; do not retry')
    g.final.update(Flash_writes=1, reset_commands=1, factory_ROM_sha256=ROM_SHA, owned_ROM_binding=rom_binding,
                   fixture_readback=c.pin(g.out / 'new-fixture-readback.bin'), firmware_written=False, Flash_readback_verified=True)
    g.final['reset_commands'] = 2; g.picotool(['reboot']); g.wait_native(location)
    after = dict(j, boot_fields=j['after_boot_fields'])
    with Port(g) as p:
        need(p.binding['location'] == location, 'Native returned at another physical slot')
        c.status_guard(p.status(), after)
        p.commands(); need('UID=' + UID in p.command('identity'), 'Returned UID changed')
        if before_crash is not None:
            body = c.crash_report_body(p.command('crash show')); (g.out / 'known-crash-after.bin').write_bytes(body)
            need(stable_crash(body) == stable_crash(before_crash), 'Known retained crash changed')
            g.final['known_crash_report_sha256_after'] = hashlib.sha256(body).hexdigest()
        final = p.status(); c.status_guard(final, after)
        g.final.update(status_after=final, usb_binding_after=p.binding, boot_fields_after=j['after_boot_fields'],
                       physical_keys_after=c.field(final, 'PHYSICAL_KEYS'), final_mode='NATIVE',
                       retained_crash_preserved=before_crash is not None)
    g.noholders(g.final['native_binding'])


def main():
    parser = argparse.ArgumentParser()
    for name in ('phase', 'grant', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    a = parser.parse_args(); g = None
    try:
        j, t = precheck(a.phase, a.grant, a.output)
        g = Gate(a.phase, a.grant, a.output)
        g.final.update(child_pid=os.getpid(), Flash_writes=0, reset_commands=0, RTC_setters=0,
                       previous_state_capture=False, previous_state_restore=False, full_flash_backup=False)
        execute(g, t); g.finish(True)
    except BaseException as error:
        if g: g.finish(False, repr(error))
        raise


if __name__ == '__main__': main()
