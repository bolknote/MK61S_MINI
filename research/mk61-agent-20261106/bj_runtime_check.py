"""Real-ROM behavioral checks for the new recovery contract, without a network."""
import copy
from bj_common import PARENT, rows
from bj_runtime import Session, SPEC_DIAG
from bh_spec import install
from ay_codec import encode
from ba_lessons import wrong_program
from full_isa_vm import FullVM


def main():
    install(); vm = FullVM()
    goal = next(g for g in rows(PARENT / 'closed-clean.jsonl') if g['family'] == 'numeric')
    good = goal['reference_body']; bad, _ = wrong_program(goal, vm, 'operation')
    s = Session(goal, good, vm, 'spec', goal['spec'], True)
    s.apply_action('write', encode({'X': 'R0', 'writes': {}, 'angle': goal['spec']['angle']}, goal['pool']))
    s.apply_action('unsure', []); s.finalize(); assert s.body == good and s.rollback_performed
    s = Session(goal, bad, vm, 'spec', goal['spec'], True)
    case = s.case; s.apply_action('write', goal['spec_body']); s.apply_action('done', [])
    assert s.pending_runs == [1 - case] and not s.pending_replan
    s.apply_action('run', [s.pending_runs.pop(0)]); s.apply_action('done', []); s.finalize()
    assert s.finished and s.body == good and not s.rollback_performed
    wrong_spec = {'X': ['ln', ['neg', ['square', 'R0']]], 'writes': {}, 'angle': goal['spec']['angle']}
    s = Session(goal, good, vm, 'spec', wrong_spec, True); s.apply_action('done', [])
    assert s.gate_checks[-1]['reason'] == 'SPEC_DOMAIN' and s.pending_replan and s.body == good
    state = s.replan_state(); assert state['body'] is None and 'declared_spec' not in state
    assert not set(state['view']) & {'spec', 'expected', 'reference_body', 'audit_inputs'}
    s.apply_replan(goal['spec_body']); assert s.body == good and s.declared_spec == goal['spec']
    s.apply_action('done', []); assert s.finished
    s = Session(goal, good, vm, 'spec', wrong_spec, True); s.apply_action('diag', SPEC_DIAG)
    assert s.pending_replan and s.body == good
    print('PASS: rollback, commit, missing RUN, SPEC_DOMAIN, condition-only replan, DIAG04; actual ROM')


if __name__ == '__main__':
    main()
