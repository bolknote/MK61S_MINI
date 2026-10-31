#!/usr/bin/env python3
"""Compare-only orchestration draft. No device factory or hardware entry point."""
import copy
import json
from pathlib import Path

from quiet_guards import assess


class ScopedCompareCarrier:
    """Use reviewed RX-only Wire and V3 decoder via the verified bound object.

    observer.capture must persist raw first-status before any follow-up and
    parse normalized public state. storage must bind verified current ALL
    lineage, own only named paths and source-prove owned UI return. Neither
    real implementation nor authority/lease binding is supplied by this draft.
    """
    def __init__(self, bound, wire, observer, storage, context, policy, output):
        self.bound, self.w, self.observer, self.storage = bound, wire, observer, storage
        self.context, self.policy = copy.deepcopy(context), copy.deepcopy(policy)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.state = dict(status='RUNNING_DRAFT', primary_failure=None, finalizer_failures=[],
                          pending=[], completed=[], hardware_GO=False, real_preservation_PASS=False,
                          snapshot_kind='quiet-source-inferred-semantic-domain; no FULL_FIELDS capsule')

    def record(self, name, value):
        data = value if isinstance(value, bytes) else (json.dumps(value, indent=2)+'\n').encode()
        (self.output / name).write_bytes(data)

    def guard(self, state, phase, original=None, sd=None):
        data = dict(self.context, pre=original or state, post=state, sd=sd or {})
        report = assess(data, self.policy, phase)
        self.record('guard-'+phase+'-'+str(len(self.state['completed']))+'.json', report)
        if not report['model_matches']:
            raise RuntimeError('Quiet admission rejected: '+','.join(report['failures']))

    def execute(self):
        opened = delivery_started = admitted = False
        before = sd = None
        try:
            # Reject even the draft's unbound static context before calling a
            # port factory. Actual authority verification is a missing real
            # entry-point responsibility, not established by these booleans.
            if (self.policy.get('accepted_base') is None or
                self.context.get('scope') != 'INTERP_QUIET_BOOT_V3' or
                self.context.get('fresh_exclusive_scope_handoff') is not True or
                self.context.get('source_domain_proof_matches_base') is not True or
                self.context.get('fresh_power_and_no_user_input') is not True):
                raise RuntimeError('Unbound static scope/base/history/authority; do not open a device')
            self.w.open(); opened = True
            before = self.observer.capture(self.w, 'pre', self.record)
            self.guard(before, 'context')  # No writes/helper before quiet guards.
            sd = self.storage.bind_current_all(self.w, self.record)
            self.guard(before, 'pre', sd=sd)
            admitted = True
            delivery_started = True
            self.storage.prepare_owned(self.w, self.record)
            for variant, app in self.bound.apps.items():
                # This hook must use the reviewed Wire upload/read/run_app,
                # exact owned ledger, raw-result retention and fresh return.
                raw = self.storage.run_owned_v3(self.w, variant, app, self.record)
                self.record(variant+'-RESULT.bin', raw)
                decoded = self.bound.admit(raw, variant)
                self.record(variant+'-decoded.json', decoded)
                current = self.observer.capture(self.w, 'after-'+variant, self.record)
                self.guard(current, 'context')
                if current['boot_id'] != before['boot_id'] or current['settings_fingerprint'] != before['settings_fingerprint']:
                    raise RuntimeError('Boot or settings changed between APPs')
                self.state['completed'].append(variant)
        except BaseException as error:
            self.state['primary_failure'] = repr(error)
        finally:
            def step(name, action, needs_channel=True):
                if needs_channel and not self.w.command_ready:
                    self.state['pending'].append(name)
                    return
                try:
                    action()
                    self.state[name] = True
                except BaseException as error:
                    self.state['finalizer_failures'].append(dict(step=name,error=repr(error)))
            if opened:
                step('raw_rx_saved', lambda:self.record('raw-rx.bin',self.w.raw), False)
                if not self.w.command_ready:
                    step('passive_return_wait', self.w.recover_command_channel, False)
                step('binary_rx_saved', lambda:self.record('binary-rx.bin',self.w.passive_raw), False)
                if delivery_started:
                    step('owned_cleanup', lambda:self.storage.cleanup_owned(self.w,self.record))
                if admitted and sd is not None:
                    def verify_sd():
                        sd.update(self.storage.verify_all_originals(self.w, sd, self.record))
                    step('ALL_SD_verified', verify_sd)
                if admitted and before is not None:
                    def verify_semantics():
                        after = self.observer.capture(self.w, 'post', self.record)
                        self.guard(after, 'post', before, sd)
                    step('public_environment_compared', verify_semantics)
                step('serial_closed', self.w.close, False)
            complete = (not self.state['primary_failure'] and not self.state['finalizer_failures'] and
                        not self.state['pending'] and self.state['completed'] == list(self.bound.apps))
            self.state['status'] = 'DRAFT_COMPARE_COMPLETE_MODEL_ONLY' if complete else 'HOLD_DRAFT_COMPARE'
            self.state['manual_recovery_required'] = bool(self.state['pending'])
            self.record('receipt.json', self.state)
        return self.state
