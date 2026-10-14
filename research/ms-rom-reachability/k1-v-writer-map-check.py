#!/usr/bin/env python3
"""Bounded original-IK1302 numeric-V writer map, not native reachability.

Enumerates every physical M22 emitter, then proves connected local routes.
No emulator state is injected and no keyboard programs are searched.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
addr = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)
byte = lambda a, i: ZeroExt(4, a.st[36+i]) | (ZeroExt(4, a.st[39+i]) << 4)
slots = ['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push(); p.add(~claim)
    answer = p.check()
    assert answer == unsat, (label, p.model() if answer == sat else answer)
    p.pop()


def inventory():
    # Tick 22 selects first sync program and sync position 4. Physical
    # order 24 (micro bit 20) is the only serial memory/output writer.
    found = []
    for ip, command in enumerate(q['COMMANDS']):
        micro = q['SYNCS'][(command & 127)*9+4] & 63
        choices = [micro] if micro < 60 else [2*(micro-60)+60, 2*(micro-60)+61]
        if any(q['MICROS'][n] & (1 << 20) for n in choices):
            found.append(ip)
    assert found == [0x32, 0xA8, 0xBC, 0xC7, 0xE7, 0xE9], found
    for ip in found:
        a = State('v_writer_%02x' % ip); out = []
        ex(a, ip, *keys('v_writer_keys_%02x' % ip), emitted_outputs=out)
        p = base(a, ip)
        prove(p, out[22] == a.r[19 if ip == 0xBC else 21], 'M22 exact emitter %02X' % ip)
    print('PASS all 256 primary ROM words: M22 emitters 32/A8/BC/C7/E7/E9 only; '
          'source R21, except BC source R19.', flush=True)


def formatted_single_v():
    """A Z marker, not Y/T, selects single E7(V) with return 47."""
    pages = {n: State('v_formatter_' + n).m for n in slots}
    a = State('v_formatter_entry'); a.m = pages['Y']
    p = base(a, 0x46)
    p.add(pages['Z'][22] == 15)
    sequence = [0x46, 0xE5, 0xE6, 0xE8, 0xE7]
    incoming = [a.r[3*j] for j in range(12)]
    b = a
    for i, ip in enumerate(sequence):
        here, following = slots[4+i], slots[5+i]
        prove(p, addr(b) == ip, 'formatter forced %02X(%s)' % (ip, here))
        out = []
        b = ex(b, ip, *keys('v_formatter_keys_' + str(i)),
               serial_inputs=pages[following], emitted_outputs=out)
        expected = [incoming[(j-1)//3] if ip == 0xE7 and j % 3 == 1 and j < 37
                    else pages[here][j] for j in range(42)]
        prove(p, And(*[x == y for x, y in zip(out, expected)]),
              'only E7(V) writes, all 12 numeric tetras; all other outputs held')
    prove(p, addr(b) == 0x47, 'finite single-V return 47(W)')
    print('PASS 46(Y) -> E5(Z marker) -> E6(T) -> E8(U) -> E7(V) -> 47(W): '
          'writes arbitrary incoming A only to V; T/U/W/Q and service fields held.', flush=True)


def single_a8_v():
    pages = {n: State('v_short_' + n).m for n in slots}
    a = State('v_short_entry'); a.m = pages['U']
    p = base(a, 0xEE)
    p.add(a.s1 == 14, a.r[35] == 14,
          byte(a, 0) == 0xA8, byte(a, 1) == 0x93, byte(a, 2) == 0xE5)
    sequence = [0xEE, 0xA8, 0xA9]
    b = a
    for i, ip in enumerate(sequence):
        here, following = slots[7+i], slots[8+i]
        prove(p, addr(b) == ip, 'short forced %02X(%s)' % (ip, here))
        out = []
        b = ex(b, ip, *keys('v_short_keys_' + str(i)),
               serial_inputs=pages[following], emitted_outputs=out)
        expected = [pages['U'][j] if ip == 0xA8 and j % 3 == 1 and j < 37
                    else pages[here][j] for j in range(42)]
        prove(p, And(*[x == y for x, y in zip(out, expected)]),
              'short copy only U to V; all other outputs held')
    prove(p, And(addr(b) == 0x93, b.s1 == 0), 'short return 93 with selector zero')
    print('PASS assumed EE(U), S1=E, R35=E, return stack A8/93/E5: '
          'EE(U) -> A8(V) -> A9(W) -> 93(Q), copy U only to V; no marker tests. '
          'Entry positioning and old return tag are NOT constructed here.', flush=True)


def scan_offsets():
    """Direct/indirect E6 dispatch and finite E7/A8 scan destinations."""
    families = [
        (7, [0xE5, 0xE6, 0xE7], 2, 0x47),
        (8, [0xE5, 0xE6, 0xE8, 0xE7], 3, 0x47),
        (9, [0xE5, 0xE6, 0xE9], 2, 0x47),
        (14, [0xE5, 0xE6, 0xEE, 0xA8, 0xA9], 3, 0x93),
    ]
    for marker in ('marker', 'V', 'Z'):
        for selector, sequence, distance, target in families:
            tag = 'v_scan_' + marker + '_' + str(selector)
            pages = {n: State(tag + n).m for n in slots}
            a = State(tag); a.m = pages[marker]; p = base(a, 0xE5)
            p.add(a.s1 == selector, pages[marker][22] == 15,
                  byte(a, 0) == (0xA8 if selector == 14 else target),
                  byte(a, 1) == target)
            b = a
            for i, ip in enumerate(sequence):
                here = slots[(slots.index(marker)+i) % 15]
                following = slots[(slots.index(marker)+i+1) % 15]
                prove(p, addr(b) == ip, tag + ' forced %02X(%s)' % (ip, here))
                b = ex(b, ip, *keys(tag + str(i)), serial_inputs=pages[following])
            prove(p, addr(b) == target, tag + ' finite return')
            destination = slots[(slots.index(marker)+distance) % 15]
            print('PASS scanner marker=%s selector=%X: writer target=%s, return=%02X'
                  % (marker, selector, destination, target), flush=True)


def wide_store_v():
    pages = {n: State('v_bc_' + n).m for n in slots}
    a = State('v_bc_entry'); a.m = pages['U']; p = base(a, 0xBB)
    b = a
    for i, ip in enumerate((0xBB, 0xBC)):
        here, following = slots[7+i], slots[8+i]
        prove(p, addr(b) == ip, 'BC forced %02X(%s)' % (ip, here))
        out = []
        b = ex(b, ip, *keys('v_bc_keys_' + str(i)),
               serial_inputs=pages[following], emitted_outputs=out)
        expected = [a.r[j] if ip == 0xBC and j % 3 == 1 else pages[here][j]
                    for j in range(42)]
        prove(p, And(*[x == y for x, y in zip(out, expected)]),
              'BB no writes then BC 14-tetra B store only')
    print('PASS assumed BB(U) -> BC(V): writes all 14 B tetras to V, including '
          'services 37/40; no markers required. This is not a service-preserving '
          'numeric writer unless B[37/40] equal old V[37/40].', flush=True)


def bc_zero_service_corollary():
    """Small set lemma conditional on the PREVIOUS completed ROM audit.

    Premises, not established by this function: in the digital-reset
    IK1302/03/06 model only BC changes the service pair, and every BC output
    byte belongs to the set below. See audit_bc_write_range.py and the
    independent review. This does NOT rebuild or reprove that control graph.
    """
    prior_audit_bc_outputs = {0xA3, 0xAF, *range(0xF0, 0x100)}
    assert 0x00 not in prior_audit_bc_outputs
    # Following the two physical service-tetra tokens through the ring,
    # a nonwriter retains their byte and a BC chooses only an allowed byte.
    # After the first BC on an initial 00 pair, this set is inductive.
    for current in prior_audit_bc_outputs:
        successors = {current} | prior_audit_bc_outputs
        assert successors <= prior_audit_bc_outputs
        assert 0x00 not in successors
    print('PASS conditional set corollary, ASSUMING previous completed BC '
          'writer/range audit: BC on service 00 irreversibly makes it nonzero; '
          'no later covered write or circulation can restore 00. '
          'The whole-ROM/reset-graph premises were NOT rerun here.', flush=True)


if __name__ == '__main__':
    inventory()
    formatted_single_v()
    single_a8_v()
    scan_offsets()
    wide_store_v()
    bc_zero_service_corollary()
    print('LIMIT: primary local suffixes only. No native entry, concurrent-chip '
          'effect, late continuation, or full-K1 claim.', flush=True)
