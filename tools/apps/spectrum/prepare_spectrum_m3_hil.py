#!/usr/bin/env python3
"""Build and pin a finite M0/M3 sound test kit without opening any device."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
PYTHON = sys.executable
TARGET = 'mk61s-picocalc-pico-h'
SOURCE_SUFFIXES = ('.c', '.cpp', '.h', '.hpp', '.S', '.inc', '.ld', '.pio')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def firmware_inputs():
    return sorted({ROOT / 'tools/firmware/picocalc/build_picocalc.py', ROOT / 'dev/lib/seal_picocalc.py',
                   *(p for folder in ('code', 'ports/picocalc', 'sdk/coproc', 'third_party/fatfs', 'third_party/core_math')
                     for p in (ROOT / folder).rglob('*')
                     if p.is_file() and (p.suffix in SOURCE_SUFFIXES or p.name == 'CMakeLists.txt'))})


def all_inputs():
    folders = ('examples/portable-apps/SPECTRUM', 'third_party/emu2149', 'third_party/z80',
               'tools/apps/spectrum', 'tools/apps/portable', 'sdk/portable')
    paths = set(firmware_inputs())
    paths.update(ROOT/'firmware/picocalc-southbridge'/name for name in ('manifest.json','source.zip','firmware.bin'))
    paths.update(p for folder in folders for p in (ROOT / folder).rglob('*')
                 if p.is_file() and (p.suffix in (*SOURCE_SUFFIXES, '.py', '.md', '.sh') or p.name == 'CMakeLists.txt'))
    paths.update(p for pattern in ('spectrum*', '*emu2149*', 'picocalc_audio*', 'run_spectrum*')
                 for p in (ROOT / 'tests').glob(pattern) if p.is_file())
    return sorted(paths)


def pins(paths):
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def verify_sources(expected):
    current = pins(all_inputs())
    changed = sorted(k for k in set(expected) | set(current) if expected.get(k) != current.get(k))
    if changed:
        raise ValueError('Sources changed while preparing the kit: ' + ', '.join(changed))


def run(out, name, command, env=None):
    print(name + '...', flush=True)
    with (out / (name + '.log')).open('x') as log:
        subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    print(name + ': PASS', flush=True)


def prepare(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = pins(all_inputs())
    save(out / 'source-pins.json', inputs)
    for source in inputs:
        target = out / 'source' / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
        if sha(target) != inputs[source]:
            raise ValueError('Source changed during snapshot: ' + source)
    checks = {}
    env = dict(os.environ, MK61_TEST_SANITIZERS='1', SPECTRUM_M3_FAST_INIT='96')
    for name, command in (
        ('host-audio', [PYTHON, 'tests/picocalc_audio_self_test.py']),
        ('host-m3', ['bash', 'tests/run_spectrum_m3_audio_tests.sh']),
        ('host-spectrum', ['bash', 'tests/run_spectrum_tests.sh']),
        ('host-qualifier', [PYTHON, 'tests/spectrum_m3_qualification_self_test.py']),
    ):
        run(out, name, command, env)
        checks[name] = {'status': 'PASS', 'log_sha256': sha(out / (name + '.log'))}
    verify_sources(inputs)
    fw = out / 'firmware'
    if args.firmware_from:
        # Reuse only a sealed build whose entire source/flag digest matches
        # this kit. Updating a log parser need not rebuild identical firmware.
        shutil.copytree(args.firmware_from.resolve(), fw)
    else:
        run(out, 'build-firmware', [PYTHON, 'tools/firmware/picocalc/build_picocalc.py',
                                  '--build-path', out / 'firmware-build', '--output-dir', fw, '--jobs', args.jobs])
    metadata = json.loads((fw / 'manifest.json').read_text())
    # Match exactly the builder's source digest and its default build flags.
    digest = hashlib.sha256()
    for source in firmware_inputs():
        digest.update(str(source.relative_to(ROOT)).encode() + b'\0')
        digest.update((out / 'source' / source.relative_to(ROOT)).read_bytes())
    digest.update(b'audio-clock=200\0lcd-color-chain=1\0lcd-spi-request=12500000\0')
    if digest.hexdigest() != metadata['source_sha256']:
        raise ValueError('Firmware build ID does not describe the frozen source inputs')
    if sha(fw / (TARGET + '.bin')) != metadata['bin_sha256'] or sha(fw / (TARGET + '.uf2')) != metadata['uf2_sha256']:
        raise ValueError('Sealed firmware artifact hashes differ')
    verify_sources(inputs)
    run(out, 'build-app', [PYTHON, 'tools/apps/spectrum/build_spectrum_app.py',
                          '--build-dir', out / 'app', '--output-dir', out / 'SPECTRUM'])
    run(out, 'build-dsp-probe', [PYTHON, 'tools/apps/spectrum/build_spectrum_m3_probe.py',
                                '--build-dir', out, '--frames', '96', '--pwm8'])
    run(out, 'build-game-probes', [PYTHON, 'tools/apps/spectrum/build_spectrum_m3_game_probe.py',
                                  '--build-dir', out, '--frames', '600', '--fixture-dir', args.fixture_dir])
    verify_sources(inputs)
    module = json.loads((out / 'module/manifest.json').read_text())
    if sha(out / 'SPECTRUM/AY.S3M') != module['sha256']:
        raise ValueError('APP and DSP probe contain different M3 modules')
    apps = {key: json.loads((out / path).read_text()) for key, path in (
        ('ordinary', 'app/SPECTRUM.json'), ('remote', 'remote/app/S3GAME.json'),
        ('local', 'local/app/S3GAME.json'), ('dsp', 'probe/app/S3SOUND.json'))}
    budget = metadata['foreground_memory_budget']
    if budget['heap_capacity_bytes'] < 108544 or module['memory_bytes'] > 6144:
        raise ValueError('Real-time memory budget failed')
    if any(app['memory_bytes'] > 49152 for app in apps.values()):
        raise ValueError('APP exceeds the 48KiB lease')
    erase_end = (metadata['flash_bytes'] + 4095) // 4096 * 4096
    if erase_end > 0x180000:
        raise ValueError('Pico firmware overlaps protected fixtures')
    southbridge = ROOT / 'firmware/picocalc-southbridge'
    stm = json.loads((southbridge / 'manifest.json').read_text())
    if sha(southbridge / stm['image']) != stm['image_sha256'] or stm['clock_hz'] != 72000000:
        raise ValueError('Unified STM32 firmware pin/clock differs')
    if sha(southbridge/'source.zip') != stm['source_archive_sha256']:
        raise ValueError('Unified firmware source archive differs')
    with zipfile.ZipFile(southbridge/'source.zip') as archive:
        for path in ('source/Core/Src/stm3_runtime.c','source/Core/Inc/stm3_runtime.h','source/Core/Src/coproc_hal.c'):
            if hashlib.sha256(archive.read(path)).hexdigest() != stm['source_archive_files'][path]:
                raise ValueError('Changed resident source in firmware archive: '+path)
    artifacts = [fw / (TARGET + suffix) for suffix in ('.bin', '.uf2', '.elf')]
    artifacts += [out / p for p in ('SPECTRUM/SPECTRUM.APP', 'SPECTRUM/AY.S3M', 'probe/app/S3SOUND.APP',
                                   'remote/app/S3GAME.APP', 'local/app/S3GAME.APP')]
    manifest = {
        'status': 'HOST_READY', 'hardware_verified': False, 'physical_io': 0,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'pico_uid': 'E6657CD423721C35', 'firmware': metadata,
        'firmware_build': {'method': 'reused matching sealed build' if args.firmware_from else 'compiled',
                           'origin': str(args.firmware_from.resolve()) if args.firmware_from else None},
        'clocks_hz': {'pico_remote': 125000000, 'stm32': 72000000, 'pico_local_control': 200000000,
                      'peripheral_usb': 48000000},
        'module': module, 'app_memory_bytes': {key: value['memory_bytes'] for key, value in apps.items()},
        'host_checks': checks, 'source_pins': 'source-pins.json', 'source_pins_sha256': sha(out / 'source-pins.json'),
        'artifacts': {str(p.relative_to(out)): sha(p) for p in artifacts},
        'protected_flash_start': '0x10180000', 'firmware_erase_end_exclusive': hex(0x10000000 + erase_end),
        'southbridge_prerequisite': {'image': str(southbridge / stm['image']), 'sha256': stm['image_sha256'],
                                    'installed_verified': False, 'owner': 'Harness / ROOT'},
        'pmu_scheduling_prerequisite': {
            'status': 'REQUIRES_OWNER_VERIFICATION',
            'audio_block_us': 3840, 'observed_legacy_telemetry_timeout_ms': 4,
            'observed_other_legacy_timeouts_ms': 60,
            'requirement': 'PMU telemetry must not block coprocessor service; legacy AXP waits must also service it',
            'preserve': ['battery protection', 'power button', 'charging', 'I2C1 slave', 'I2C2 ownership'],
            'evidence': 'HOST PMU foreground gap tests; no physical timing claim',
        },
        'fixture_directory': args.fixture_dir, 'game_frames': 600,
        'remote_policy': 'PSG_ONLY_OPEN6; fail closed, no local synthesis or clock boost',
        'qualification': 'tools/apps/spectrum/qualify_spectrum_m3_run.py',
        'execution_order': ['Fresh coordinator handoff; no earlier receipt is admission',
                            'Verify installed unified STM32 image and stable I2C/keyboard',
                            'Verify PMU scheduling fix with its owner; I2C1 health alone does not qualify I2C2 stalls',
                            'Admit exact Pico UID/build and save native C5 baseline',
                            'Install pinned Pico firmware below protected fixtures; verify readback',
                            'Run finite push-only S3SOUND; verify PCM CRC and native render/transport timing',
                            'Run remote-only Cosmic Payback at 125/72MHz, save raw wire and before/after C5',
                            'Remove owned byte-verified test files and close CDC/shared lock',
                            'Qualify captured logs independently of successful app return',
                            'If healthy, run local 200MHz control with same fixtures and collect logs'],
    }
    save(out / 'manifest.json', manifest)
    (out / 'PLAN.md').write_text(
        '# M0/M3 sound test kit\n\n'
        'HOST_READY. Device access: 0. Physical real-time qualification is pending.\n\n'
        'The remote probe requires PSG_ONLY_OPEN6 and cannot fall back to local sound. '
        'Missing or failed M3 closes the finite probe. The local probe is an explicit 200MHz control. '
        'Neither probe changes the STM32 clock.\n\n'
        'Start only after the coordinator releases the Pico and confirms the unified STM32 image. '
        'Use the exact artifacts and hashes in manifest.json; source/ contains their input snapshot. '
        'Keep old HOLD and failure receipts.\n\n'
        'PMU scheduling is a separate prerequisite: the old resident performs a blocking I2C2 status read '
        'with a 4ms timeout before coproc_poll(), versus 3840us per 96 audio samples. '
        'Other legacy AXP calls use up to 60ms timeouts. Verify nonblocking telemetry and continued '
        'coprocessor service during legacy waits with the PMU owner, preserving charging/power controls. '
        'Reordering one poll or clean I2C1 keyboard counters does not prove this requirement. '
        'HOST_READY is not physical M3-audio qualification.\n\n'
        'Capture SP3 POLICY/RESULT/FRAME and native C5 before/after each run. Then run:\n\n'
        '```sh\npython3 tools/apps/spectrum/qualify_spectrum_m3_run.py '
        '--wire RUN/game-wire.txt --before RUN/before.txt --after RUN/after.txt '
        '--mode remote --output RUN/qualification.json\n```\n\n'
        'Qualification checks the 3.5MHz floor with only 1us timestamp uncertainty, frame delays, '
        '25kHz sample coverage, no fallback/underrun/late block, pushed completion without readiness polls, '
        'bounded native slices, keyboard/I2C counters and clean native resource return. '
        'Clean app return alone is not a real-time PASS.\n')
    print(json.dumps({'status': manifest['status'], 'kit': str(out), 'pico_build': metadata['build_id'],
                      'heap': budget['heap_capacity_bytes'], 'module_bytes': module['memory_bytes'],
                      'physical_io': 0}, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True, help='New directory; existing results are never replaced')
    ap.add_argument('--fixture-dir', default='/MK61S-SPECTRUM-HIL-20261105/SPECTRUM')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--firmware-from', type=Path, help='Reuse a sealed build only if all source/flag and artifact hashes match')
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error('--jobs must be positive')
    prepare(args)


if __name__ == '__main__':
    main()
