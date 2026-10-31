#!/usr/bin/env python3
"""Pure draft quiet-boot predicates. Never a real provider or hardware GO."""
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

SCOPE = 'INTERP_QUIET_BOOT_V3'
READS = {'identity', 'crash show', 'date', 'alarm', 'reg', 'stk', 'hout', 'dump', 'pwd', 'ring', 'ls /'}
OWNED = ('/INTRP01/', '/MK61S-V138-BACKUP/')


def assess(data, policy, phase='post'):
    if phase not in ('context', 'pre', 'post'):
        raise ValueError('Unknown draft guard phase')
    failures = []
    def check(value, name):
        if not value:
            failures.append(name)
    def zero(values):
        try:
            return bool(values) and all(Decimal(str(value)).is_finite() and Decimal(str(value)) == 0 for value in values)
        except (InvalidOperation, ValueError, TypeError):
            return False
    base = policy.get('accepted_base')
    check(isinstance(base, dict) and all(base.get(key) for key in ('build', 'source_sha256', 'elf_sha256')),
          'accepted_repaired_base_unbound')
    pre, post = data.get('pre', {}), data.get('post', {})
    states = (('pre', pre), ('post', post)) if phase == 'post' else (('pre', pre),)
    for label, state in states:
        check(state.get('base') == base and base is not None, label + ':base_mismatch')
        check(state.get('uid') == policy['uid'], label + ':UID')
        check(state.get('ip') == 0 and state.get('steps') == 105, label + ':IP_or_program_size')
        check(len(state.get('register_values', [])) == 15 and zero(state.get('register_values')), label + ':registers_not_zero')
        check(len(state.get('stack_values', [])) == 5 and zero(state.get('stack_values')) and zero([state.get('last_x')]), label + ':stack_LASTX_not_zero')
        try:
            program = bytes.fromhex(state.get('program_hex', ''))
            check(len(program) == 105 and not any(program), label + ':program_not_zero')
        except (ValueError, TypeError):
            failures.append(label + ':program_encoding')
        check(all(state.get(key) == value for key, value in dict(run=0, busy=0, dirty=0, physical_keys=0,
              service='CLOSED', runtime='NONE', ui='CALCULATOR', terminal='COMMAND', usb_disk=0,
              usb_screen='OFF', m61_active=0, m61_suspended=0, cwd='/').items()), label + ':foreign_owner_or_mode')
        check(state.get('rtc_set') == 0, label + ':RTC_SET')
        check(state.get('settings_sequence') == policy['required_settings_sequence'], label + ':settings_sequence')
        check(state.get('alarms') == ['OFF ONCE', 'OFF ONCE'], label + ':alarms')
        check(state.get('retained_fault') is False and state.get('health_ok') is True, label + ':fault_or_health')
    check(pre.get('boot_id'), 'boot_unknown')
    if phase == 'post':
        check(pre.get('boot_id') == post.get('boot_id'), 'boot_changed_or_unknown')
        check(pre.get('settings_fingerprint') and pre.get('settings_fingerprint') == post.get('settings_fingerprint'), 'settings_changed')
    check(data.get('fresh_power_and_no_user_input') is True and data.get('source_domain_proof_matches_base') is True,
          'quiet_boot_history_or_source_proof_missing')
    check(data.get('scope') == SCOPE, 'scope_mismatch')
    for operation in data.get('operations', []):
        if operation.get('kind') == 'read_command':
            check(operation.get('command') in READS, 'unreviewed_command_or_setter')
        elif operation.get('kind') in ('owned_upload', 'owned_remove', 'owned_app'):
            path = operation.get('path', '')
            check(any(path.startswith(prefix) for prefix in OWNED) and '..' not in path.split('/'), 'foreign_path_mutation')
            if operation.get('kind') == 'owned_app':
                check(operation.get('sha256') in policy['allowed_app_sha256'], 'unreviewed_APP')
        else:
            failures.append('unreviewed_activity')
    sd = data.get('sd', {})
    if phase != 'context':
        check(sd.get('complete_current_bytes') is True and sd.get('independent_actual_review') is True and
              sd.get('postcold_lineage_covered') is True, 'ALL_SD_incomplete_stale_or_unverified')
        if phase == 'post':
            check(sd.get('every_original_byte_reverified') is True, 'ALL_SD_incomplete_stale_or_unverified')
    check(data.get('fresh_exclusive_scope_handoff') is True, 'new_INTERP_handoff_missing')
    # Same A748 reference formula as the reviewed SD compare-only path. Its
    # applicability must be source-proven again for the actual repaired base.
    try:
        ppm = pre['rtc_ppm']
        check(type(ppm) is int and -500 <= ppm <= 500, 'RTC_calibration_invalid')
        if phase != 'post':
            datetime.fromisoformat(pre['clock']['rtc'])
            check(pre['clock']['wall_after'] >= pre['clock']['wall_before'] and pre['clock']['host_boot_id'], 'clock_capture_invalid')
            return result(failures)
        check(post['rtc_ppm'] == ppm, 'RTC_calibration_changed')
        before, after = pre['clock'], post['clock']
        low = after['wall_before'] - before['wall_after']
        high = after['wall_after'] - before['wall_before']
        check(low >= 0 and high >= low and before['host_boot_id'] == after['host_boot_id'], 'clock_origin_or_host_discontinuity')
        elapsed = (datetime.fromisoformat(after['rtc']) - datetime.fromisoformat(before['rtc'])).total_seconds()
        hz = policy['reference_rtc_hz']
        divider = (hz * (1000000 - ppm) + 500000) // 1000000
        tolerance = 3 + high / (2 * hz)
        check(low * hz / divider - tolerance <= elapsed <= high * hz / divider + tolerance,
              'RTC_trajectory_changed_no_setter_fallback')
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        failures.append('RTC_capture_missing_or_invalid')
    return result(failures)


def result(failures):
    return dict(status='DRAFT_GUARDS_MATCH_MODEL_ONLY' if not failures else 'DRAFT_GUARDS_REJECT_MODEL_ONLY',
                model_matches=not failures, failures=failures, hardware_GO=False, execution_enabled=False,
                real_provider_bound=False,
                limitation='Normalized fixture predicates only. Real parsers, source/authority/lease provenance, post-Cold byte receipts and the new compare-only carrier still require integration and independent review. This is not FULL_FIELDS/CALCAP snapshot restoration.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=Path(__file__).with_name('policy.UNBOUND.json'))
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    if args.evidence:
        result = assess(json.loads(args.evidence.read_text()), json.loads(args.policy.read_text()))
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['model_matches'] else 2)
    print(json.dumps(dict(status='HELD_DRAFT_INTEGRATION_ONLY', hardware_GO=False, device_opened=False,
                         policy=json.loads(args.policy.read_text()), plan=str(Path(__file__).with_name('integration-plan.json'))), indent=2))
    raise SystemExit(2)


if __name__ == '__main__':
    main()
