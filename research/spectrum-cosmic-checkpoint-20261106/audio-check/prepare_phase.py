"""HOST-only packet creation. No device I/O and no grant creation."""
import argparse
import json
from pathlib import Path
import run_audio_check as controller

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--supervisor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ready', action='store_true', help='Only after current supplier release has been verified')
    args = parser.parse_args()
    receipt, supervisor = args.receipt.resolve(), args.supervisor.resolve()
    source = json.loads(receipt.read_text())
    output = args.output.resolve()
    handoff = output.with_name(output.stem + '-handoff.json')
    controller.need(not output.exists() and not handoff.exists(), 'Never overwrite a previous packet')
    normalized = dict(uid=controller.b.UID, expected=controller.EXPECTED, lease=source['lease'],
        source_receipt=str(receipt), source_receipt_sha256=controller.sha(receipt),
        supervisor=str(supervisor), supervisor_sha256=controller.sha(supervisor), native_binding=source['native_binding'])
    handoff.write_text(json.dumps(normalized, indent=2) + '\n')
    native = ROOT / '.build/m0-exp-decision-20261106-001/sdk-source-next-717base'
    sdk = Path('/private/tmp/mk61-spectrum-20261105/pico-sdk/src/rp2040/hardware_regs/include/hardware/regs')
    files = [HERE / name for name in ('main.c', 'self_test.c', 'self-test.log', 'pcm_levels.c', 'pcm-levels.log',
        'frame_dump_driver.c', 'controller_tests.py', 'controller-tests.log', 'prepare_phase.py', 'REVIEW.md')]
    files += [HERE / 'build' / name for name in ('SPAUDCHK.APP', 'SPAUDCHK.elf', 'SPAUDCHK.bin', 'SPAUDCHK.json', 'compile_commands.json')]
    files += [native / name for name in ('ports/picocalc/audio_stream.cpp', 'ports/picocalc/native_app.cpp',
        'ports/picocalc/io_worker.cpp', 'ports/picocalc/script.hpp', 'ports/picocalc/settings.hpp')]
    files += [sdk / name for name in ('pwm.h', 'io_bank0.h', 'addressmap.h')]
    files += [sdk.parents[3] / 'hardware_structs/include/hardware/structs/io_bank0.h']
    files += [receipt, supervisor, handoff, ROOT / 'sdk/portable/include/mk61_app.h', ROOT / 'code/loadable_app_services.h']
    pins = {**controller.source_pins(), **{str(path): controller.sha(path) for path in files}}
    item = lambda path: dict(local=str(path), sha256=controller.sha(path))
    packet = dict(role='spectrum-audio-check', action='timing', uid=controller.b.UID, folder=controller.FOLDER,
        indexes=[0], expected=controller.EXPECTED, sequence=controller.SEQUENCE,
        readiness='fresh_handoff_verified' if args.ready else 'draft_no_GO',
        files={controller.NAME: item(HERE / 'build' / controller.NAME)}, handoff=item(handoff), pins=pins,
        scope='One8.5s stereo synth diagnostic;settings volume getter andPWM/pinmux reads only;one temporary APP;'
              'no ordinary APP/firmware/PSRAM/RTC/oldstate operations;90sphase+45scleanup,150sexternal supervisor;'
              'firstfaultHOLD/no retry. Physical audibility is a separate human observation.')
    check = {**packet, 'readiness': 'fresh_handoff_verified'}
    controller.validate_plan(check)
    output.write_text(json.dumps(packet, indent=2) + '\n')
    print(json.dumps(dict(phase=str(output), sha256=controller.sha(output), pins=len(pins), readiness=packet['readiness'])))


if __name__ == '__main__':
    main()
