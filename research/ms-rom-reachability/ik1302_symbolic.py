#!/usr/bin/env python3
"""IK1302 command semantics; arbitrary serial input overapproximates the ring."""

import json
import os
import subprocess
from itertools import count
from pathlib import Path

from z3 import And, BitVec, BitVecVal, Concat, Extract, If, Or, Solver, ZeroExt, sat, unsat, simplify


REFERENCE_ROOT = Path(os.environ.get(
    "MK61_REFERENCE_ROOT", Path(__file__).resolve().parents[3] / "MK-61"))
ROM_PATH = REFERENCE_ROOT / "tests/emulator/rom.cjs"


def load_rom():
    source = (
        "const r=require(" + json.dumps(str(ROM_PATH)) + ").ИК1302;"
        "console.log(JSON.stringify(r))"
    )
    raw = subprocess.check_output(["node", "-e", source], text=True)
    rom = json.loads(raw)
    return rom["команды"], rom["синхропрограммы"], rom["микрокоманды"]


COMMANDS, SYNCS, MICROS = load_rom()
N4 = lambda value: BitVecVal(value & 15, 4)
N1 = lambda value: BitVecVal(value & 1, 1)
SERIAL_GENERATION = count()


class State:
    def __init__(self, prefix):
        self.r = [BitVec(f"{prefix}_r{i}", 4) for i in range(42)]
        self.m = [BitVec(f"{prefix}_m{i}", 4) for i in range(42)]
        self.st = [BitVec(f"{prefix}_st{i}", 4) for i in range(42)]
        self.s = BitVec(f"{prefix}_s", 4)
        self.s1 = BitVec(f"{prefix}_s1", 4)
        self.l = BitVec(f"{prefix}_l", 1)
        self.t = BitVec(f"{prefix}_t", 1)
        self.carry = BitVec(f"{prefix}_carry", 1)

    def copy(self):
        other = object.__new__(State)
        other.r = list(self.r)
        other.m = list(self.m)
        other.st = list(self.st)
        other.s = self.s
        other.s1 = self.s1
        other.l = self.l
        other.t = self.t
        other.carry = self.carry
        return other


def choose(cond, yes, no):
    return If(cond, yes, no)


def apply_dest(state, number, sigma, tick, cond):
    r = state.r
    st = state.st
    if number == 15:
        r[tick] = choose(cond, r[(tick + 3) % 42], r[tick])
    elif number == 16:
        r[tick] = choose(cond, sigma, r[tick])
    elif number == 17:
        r[tick] = choose(cond, state.s, r[tick])
    elif number == 18:
        value = r[tick] | state.s | sigma
        r[tick] = choose(cond, value, r[tick])
    elif number == 19:
        r[tick] = choose(cond, state.s | sigma, r[tick])
    elif number == 20:
        r[tick] = choose(cond, r[tick] | state.s, r[tick])
    elif number == 21:
        r[tick] = choose(cond, r[tick] | sigma, r[tick])
    elif number == 22:
        dst = (tick + 41) % 42
        r[dst] = choose(cond, sigma, r[dst])
    elif number == 23:
        dst = (tick + 40) % 42
        r[dst] = choose(cond, sigma, r[dst])
    elif number == 24:
        state.m[tick] = choose(cond, state.s, state.m[tick])
    elif number == 25:
        state.l = choose(cond, state.carry, state.l)
    elif number == 26:
        state.s = choose(cond, state.s1, state.s)
    elif number == 27:
        state.s = choose(cond, sigma, state.s)
    elif number == 28:
        state.s = choose(cond, state.s1 | sigma, state.s)
    elif number == 29:
        state.s1 = choose(cond, sigma, state.s1)
    elif number == 30:
        pass
    elif number == 31:
        state.s1 = choose(cond, state.s1 | sigma, state.s1)
    elif number == 32:
        a, b, c = st[tick], st[(tick + 1) % 42], st[(tick + 2) % 42]
        st[(tick + 2) % 42] = choose(cond, b, c)
        st[(tick + 1) % 42] = choose(cond, a, b)
        st[tick] = choose(cond, sigma, a)
    elif number == 33:
        a, b, c = st[tick], st[(tick + 1) % 42], st[(tick + 2) % 42]
        st[tick] = choose(cond, b, a)
        st[(tick + 1) % 42] = choose(cond, c, b)
        st[(tick + 2) % 42] = choose(cond, a, c)
    elif number == 34:
        a, b, c = st[tick], st[(tick + 1) % 42], st[(tick + 2) % 42]
        st[tick] = choose(cond, sigma | b, a)
        st[(tick + 1) % 42] = choose(cond, a | c, b)
        st[(tick + 2) % 42] = choose(cond, b | a, c)
    else:
        raise ValueError(number)


def source_value(state, number, tick):
    if number == 0:
        return state.r[tick]
    if number == 1:
        return state.m[tick]
    if number == 2:
        return state.st[tick]
    if number == 3:
        return ~state.r[tick]
    if number == 4:
        return choose(state.l == 0, N4(10), N4(0))
    if number == 5:
        return state.s
    if number == 6:
        return N4(4)
    if number == 7:
        return state.s
    if number == 8:
        return ~state.s
    if number == 9:
        return state.s1
    if number == 10:
        return N4(6)
    if number == 11:
        return N4(1)
    if number == 12:
        return ZeroExt(3, state.l)
    if number == 13:
        return ZeroExt(3, ~state.l)
    if number == 14:
        return ZeroExt(3, ~state.t)
    raise ValueError(number)


def execute_command(initial, ip, key_x=0, key_y=0, serial_inputs=None,
                    emitted_outputs=None):
    state = initial.copy()
    if serial_inputs is None:
        generation = next(SERIAL_GENERATION)
        serial_inputs = [BitVec(f"serial_{generation}_{i}", 4) for i in range(42)]
    word = COMMANDS[ip]
    has_user_opcode = ((word >> 16) & 0x3F) > 0
    if not has_user_opcode:
        state.t = N1(0)
    sync_address = word & 0x7F

    for tick in range(42):
        nine = tick // 9
        tick_in_nine = tick - nine * 9
        if tick_in_nine == 0 and not (0 < nine < 3):
            if nine < 3:
                sync_address = word & 0x7F
            elif nine == 3:
                sync_address = (word >> 7) & 0x7F
            elif nine == 4:
                sync_address = (word >> 14) & 0xFF
                if sync_address > 31:
                    if tick == 36:
                        state.r[37] = N4(sync_address)
                        state.r[40] = N4(sync_address >> 4)
                    sync_address = 95

        sync_cell = SYNCS[sync_address * 9 + (tick if tick < 6 else (tick % 3 + 3 if tick < 21 else tick % 9))] & 0x3F
        if sync_cell > 59:
            even = (sync_cell - 60) * 2 + 60
            micro_index = choose(state.l == 0, BitVecVal(even + 1, 7), BitVecVal(even, 7))
            candidates = [MICROS[even], MICROS[even + 1]]
            mos = [choose(micro_index == even + 1,
                          BitVecVal((candidates[1] >> bit) & 1, 1),
                          BitVecVal((candidates[0] >> bit) & 1, 1)) == 1
                   for bit in range(28)]
        else:
            micro = MICROS[sync_cell]
            mos = [((micro >> bit) & 1) == 1 for bit in range(28)]

        trio = tick // 3
        kx = key_x[tick] if isinstance(key_x, list) else key_x
        ky = key_y[tick] if isinstance(key_y, list) else N4(key_y)
        state.s1 = choose(And(mos[25], trio != kx - 1),
                          state.s1 | ky, state.s1)

        alpha, beta, gamma = N4(0), N4(0), N4(0)
        for number in range(12):
            alpha_or_beta = source_value(state, number, tick)
            if number <= 6:
                alpha = choose(mos[number], alpha | alpha_or_beta, alpha)
            else:
                beta = choose(mos[number], beta | alpha_or_beta, beta)

        if has_user_opcode:
            state.t = choose(ky == 0, N1(0), state.t)
        else:
            key_active = And(trio == kx - 1, ky != 0)
            state.s1 = choose(key_active, ky, state.s1)
            state.t = choose(key_active, N1(1), state.t)

        for number in range(12, 15):
            gamma = choose(mos[number], gamma | source_value(state, number, tick), gamma)

        total = ZeroExt(2, alpha) + ZeroExt(2, beta) + ZeroExt(2, gamma)
        sigma = Extract(3, 0, total)
        state.carry = Extract(4, 4, total)

        if ((word >> 22) & 1) == 0 or nine == 4:
            field = If(mos[17], BitVecVal(4, 3), BitVecVal(0, 3)) \
                | If(mos[16], BitVecVal(2, 3), BitVecVal(0, 3)) \
                | If(mos[15], BitVecVal(1, 3), BitVecVal(0, 3))
            for value in range(1, 8):
                apply_dest(state, value + 14, sigma, tick, field == value)
            for bit, number in [(18, 22), (19, 23)]:
                apply_dest(state, number, sigma, tick, mos[bit])

        for bit, number in [(20, 24), (21, 25)]:
            apply_dest(state, number, sigma, tick, mos[bit])

        for group in range(3):
            field = If(mos[23 + group * 2], BitVecVal(2, 2), BitVecVal(0, 2)) \
                | If(mos[22 + group * 2], BitVecVal(1, 2), BitVecVal(0, 2))
            for value in range(1, 4):
                apply_dest(state, value + 25 + group * 3, sigma, tick, field == value)

        if emitted_outputs is not None:
            emitted_outputs.append(simplify(state.m[tick]))
        # Serial input replaces M[tick] after its last read in this cycle.
        # Arbitrary fresh inputs deliberately overapproximate the other chips
        # and ring. UNSAT remains conclusive; SAT is not physical reachability.
        state.m[tick] = serial_inputs[tick]

    for group in ("r", "m", "st"):
        setattr(state, group, [simplify(value) for value in getattr(state, group)])
    for name in ("s", "s1", "l", "t", "carry"):
        setattr(state, name, simplify(getattr(state, name)))
    return state


def arbitrary_keys(prefix):
    # Every tick may have different row/column signals. Row indices are even
    # allowed beyond the real 2..11 range: a deliberate conservative superset.
    xs = [BitVec(f'{prefix}_key_x_{i}', 4) for i in range(42)]
    ys = [Concat(BitVec(f'{prefix}_key_hi_{i}', 1), BitVecVal(0, 2),
                 BitVec(f'{prefix}_key_lo_{i}', 1)) for i in range(42)]
    return xs, ys


def possible_values(expr, solver, limit=256):
    values = []
    while len(values) < limit:
        outcome = solver.check()
        assert outcome in (sat, unsat), solver.reason_unknown()
        if outcome == unsat:
            break
        model = solver.model()
        value = model.eval(expr, model_completion=True).as_long()
        values.append(value)
        solver.add(expr != value)
    return sorted(values)


def analyze_sources(sources, keys=((0, 0),)):
    for source in sources:
        for key_x, key_y in keys:
            initial = State(f"i{source:02x}_{key_x}_{key_y}")
            final = execute_command(initial, source, key_x, key_y)
            solver = Solver()
            solver.add(initial.r[36] == N4(source), initial.r[39] == N4(source >> 4))
            solver.add(Or(initial.l == 0, initial.l == 1))
            solver.add(Or(initial.t == 0, initial.t == 1))
            solver.add(Or(initial.carry == 0, initial.carry == 1))
            next_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
            s1_solver = Solver()
            s1_solver.add(*solver.assertions())
            ips = possible_values(next_ip, solver, 257)
            s1s = possible_values(final.s1, s1_solver, 17)
            print(f"{source:02X} key={key_x},{key_y}: next={' '.join(f'{v:02X}' for v in ips)}; s1={' '.join(f'{v:X}' for v in s1s)}")


def find_direct_predecessors(targets, key_x=0, key_y=0):
    hits = {target: [] for target in targets}
    for source in range(256):
        initial = State(f"p{source:02x}_{key_x}_{key_y}")
        final = execute_command(initial, source, key_x, key_y)
        solver = Solver()
        solver.add(initial.r[36] == N4(source), initial.r[39] == N4(source >> 4))
        solver.add(Or(initial.l == 0, initial.l == 1))
        solver.add(Or(initial.t == 0, initial.t == 1))
        solver.add(Or(initial.carry == 0, initial.carry == 1))
        next_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
        for target in targets:
            solver.push()
            solver.add(next_ip == target)
            if solver.check() == sat:
                hits[target].append(source)
            solver.pop()
    for target, sources in hits.items():
        print(f"predecessors({target:02X}) key={key_x},{key_y}: " + " ".join(f"{x:02X}" for x in sources))


def constrain_except(solver, initial, source, allowed):
    solver.add(initial.r[36] == N4(source), initial.r[39] == N4(source >> 4))
    for i, value in enumerate(initial.r):
        if i not in (36, 39) and "r" not in allowed:
            solver.add(value == 0)
    for value in initial.m:
        if "m" not in allowed:
            solver.add(value == 0)
    for value in initial.st:
        if "st" not in allowed:
            solver.add(value == 0)
    for name in ("s", "s1", "l", "t", "carry"):
        value = getattr(initial, name)
        if name not in allowed:
            solver.add(value == 0)


def nonzero_model_values(model, initial):
    values = []
    for group in ("r", "m", "st"):
        for i, value in enumerate(getattr(initial, group)):
            number = model.eval(value, model_completion=True).as_long()
            if number:
                values.append(f"{group}{i}={number:X}")
    for name in ("s", "s1", "l", "t", "carry"):
        value = getattr(initial, name)
        number = model.eval(value, model_completion=True).as_long()
        if number:
            values.append(f"{name}={number:X}")
    return values


def explain_target(source, target, key_x=0, key_y=0):
    print(f"explain {source:02X}->{target:02X} key={key_x},{key_y}")
    for allowed in [set(), {"m"}, {"st"}, {"r"}, {"s"}, {"s1"},
                    {"l"}, {"t"}, {"carry"},
                    {"s", "s1", "l", "t", "carry"},
                    {"r", "m", "st", "s", "s1", "l", "t", "carry"}]:
        tag = "+".join(sorted(allowed)) or "fixed-zero"
        initial = State(f"x{source:02x}_{target:02x}_{key_x}_{key_y}_{tag}")
        final = execute_command(initial, source, key_x, key_y)
        solver = Solver()
        constrain_except(solver, initial, source, allowed)
        next_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
        solver.add(next_ip == target)
        outcome = solver.check()
        if outcome == sat:
            model = solver.model()
            witness = " ".join(nonzero_model_values(model, initial))
            print(f"  {tag}: sat {witness}")
        else:
            print(f"  {tag}: {outcome}")


def disassemble_sync(address):
    print(f"sync {address:02X}")
    for j in range(9):
        cell = SYNCS[address * 9 + j] & 0x3F
        choices = []
        if cell > 59:
            even = (cell - 60) * 2 + 60
            choices = [even, even + 1]
        else:
            choices = [cell]
        rendered = []
        for index in choices:
            micro = MICROS[index]
            bits = [str(bit) for bit in range(28) if (micro >> bit) & 1]
            rendered.append(f"u{index:02X}=" + ",".join(bits))
        print(f"  j{j}: cell={cell:02X} " + " / ".join(rendered))


def analyze_sequence(sequence, key_x=0, key_y=0):
    initial = State("q_" + "_".join(f"{ip:02x}" for ip in sequence))
    state = initial
    solver = Solver()
    solver.add(initial.r[36] == N4(sequence[0]),
               initial.r[39] == N4(sequence[0] >> 4))
    for index, ip in enumerate(sequence):
        state = execute_command(state, ip, key_x, key_y)
        if index + 1 < len(sequence):
            solver.add(state.r[36] == N4(sequence[index + 1]),
                       state.r[39] == N4(sequence[index + 1] >> 4))
    next_ip = ZeroExt(4, state.r[36]) | (ZeroExt(4, state.r[39]) << 4)
    ip_solver = Solver()
    ip_solver.add(*solver.assertions())
    ips = possible_values(next_ip, ip_solver, 257)
    s1s = possible_values(state.s1, solver, 17)
    print("sequence " + "->".join(f"{ip:02X}" for ip in sequence)
          + ": next=" + " ".join(f"{ip:02X}" for ip in ips)
          + "; s1=" + " ".join(f"{value:X}" for value in s1s))


def explain_sequence_target(sequence, target, key_x=0, key_y=0):
    print("explain sequence " + "->".join(f"{ip:02X}" for ip in sequence)
          + f"->{target:02X} key={key_x},{key_y}")
    variants = [set(), {"m"}, {"st"}, {"r"}, {"s"}, {"s1"}, {"l"}, {"t"},
                {"carry"}, {"r", "m"}, {"r", "st"}, {"m", "st"},
                {"r", "m", "st", "s", "s1", "l", "t", "carry"}]
    for allowed in variants:
        tag = "+".join(sorted(allowed)) or "fixed-zero"
        initial = State("z_" + "_".join(f"{ip:02x}" for ip in sequence) + "_" + tag)
        state = initial
        solver = Solver()
        constrain_except(solver, initial, sequence[0], allowed)
        for index, ip in enumerate(sequence):
            state = execute_command(state, ip, key_x, key_y)
            expected = sequence[index + 1] if index + 1 < len(sequence) else target
            solver.add(state.r[36] == N4(expected), state.r[39] == N4(expected >> 4))
        outcome = solver.check()
        if outcome == sat:
            witness = " ".join(nonzero_model_values(solver.model(), initial))
            print(f"  {tag}: sat {witness}")
        else:
            print(f"  {tag}: {outcome}")


def find_stack_writers(target, allowed):
    hits = []
    for source in range(256):
        initial = State(f"w{source:02x}_{target:02x}_" + "_".join(sorted(allowed)))
        final = execute_command(initial, source)
        solver = Solver()
        constrain_except(solver, initial, source, allowed)
        solver.add(final.st[36] == N4(target), final.st[39] == N4(target >> 4))
        if solver.check() == sat:
            model = solver.model()
            hits.append((source, nonzero_model_values(model, initial)))
    print(f"stack-writers({target:02X}) allowed={'+'.join(sorted(allowed))}: ")
    for source, witness in hits:
        print(f"  {source:02X}: " + " ".join(witness))


def base_solver(initial, source):
    solver = Solver()
    solver.add(initial.r[36] == N4(source), initial.r[39] == N4(source >> 4))
    solver.add(Or(initial.l == 0, initial.l == 1))
    solver.add(Or(initial.t == 0, initial.t == 1))
    solver.add(Or(initial.carry == 0, initial.carry == 1))
    return solver


def prove_r38_invariants():
    keys = [(0, 0)] + [(x, y) for x in range(2, 12) for y in (1, 8, 9)]
    for source, expected in [(0xCD, 8)]:
        for key_x, key_y in keys:
            initial = State(f"const_{source:02x}_{key_x}_{key_y}")
            final = execute_command(initial, source, key_x, key_y)
            solver = base_solver(initial, source)
            solver.add(final.r[38] != N4(expected))
            assert solver.check() != sat, (
                f"{source:02X} can leave r38 != {expected:X} with key {key_x},{key_y}"
            )
        print(f"proved {source:02X}: final r38={expected:X} for arbitrary state and all keys")

    for source in (0xC9, 0x06, 0x07, 0x6D):
        for key_x, key_y in keys:
            initial = State(f"preserve_{source:02x}_{key_x}_{key_y}")
            final = execute_command(initial, source, key_x, key_y)
            solver = base_solver(initial, source)
            solver.add(final.r[38] != initial.r[38])
            assert solver.check() != sat, (
                f"{source:02X} can alter r38 with key {key_x},{key_y}"
            )
        print(f"proved {source:02X}: preserves r38 for arbitrary state and all keys")


def prove_60_transition():
    keys = [(0, 0)] + [(x, y) for x in range(2, 12) for y in (1, 8, 9)]
    for key_x, key_y in keys:
        initial = State(f"formula60_{key_x}_{key_y}")
        final = execute_command(initial, 0x60, key_x, key_y)
        solver = base_solver(initial, 0x60)
        next_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
        condition = And(initial.r[25] == initial.r[31], initial.r[38] == N4(4))
        solver.add((next_ip == 0xC8) != condition)
        assert solver.check() != sat, f"60->C8 formula fails with key {key_x},{key_y}"
    print("proved 60: next=C8 iff r25=r31 and r38=4, for arbitrary state and all keys")


def list_r38_writers():
    writers = []
    for source in range(256):
        initial = State(f"r38writer_{source:02x}")
        final = execute_command(initial, source)
        solver = base_solver(initial, source)
        solver.add(final.r[38] != initial.r[38])
        if solver.check() == sat:
            values_solver = base_solver(initial, source)
            values = possible_values(final.r[38], values_solver, 17)
            writers.append((source, values))
    print("r38 writers:")
    for source, values in writers:
        print(f"  {source:02X}: " + " ".join(f"{value:X}" for value in values))


def show_commands(addresses):
    for address in addresses:
        word = COMMANDS[address]
        fields = [word & 0x7f, (word >> 7) & 0x7f,
                  (word >> 14) & 0xff, (word >> 22) & 1]
        print(f"{address:02X}: word={word:06X} fields="
              + "/".join(f"{field:02X}" for field in fields))
        for part, sync in enumerate(fields[:3]):
            disassemble_sync(0x5f if part == 2 and sync > 0x1f else sync)


def build_graph(key_x=0, key_y=0):
    graph = {}
    for source in range(256):
        initial = State(f"g{source:02x}_{key_x}_{key_y}")
        final = execute_command(initial, source, key_x, key_y)
        solver = base_solver(initial, source)
        next_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
        graph[source] = possible_values(next_ip, solver, 257)
    return graph


def show_reverse_slice(target, depth=8):
    graph = build_graph()
    returns = {0x62, 0x9A, 0xA9, 0xBC, 0xC7, 0xC8, 0xC9,
               0xD4, 0xD6, 0xE7, 0xE9, 0xEE}
    frontier = {target}
    seen = {target}
    print(f"reverse non-return slice to {target:02X}")
    for level in range(1, depth + 1):
        incoming = {}
        for source, destinations in graph.items():
            if source in returns:
                continue
            hits = sorted(frontier.intersection(destinations))
            if hits:
                incoming[source] = hits
        if not incoming:
            break
        print(f"  level {level}: " + " ".join(
            f"{source:02X}->" + ",".join(f"{x:02X}" for x in hits)
            for source, hits in sorted(incoming.items())))
        frontier = set(incoming) - seen
        seen.update(incoming)
        if not frontier:
            break


def show_next_r38(source, key_x=0, key_y=0):
    initial = State(f"pair_{source:02x}_{key_x}_{key_y}")
    final = execute_command(initial, source, key_x, key_y)
    solver = base_solver(initial, source)
    next_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
    pair = (ZeroExt(8, final.r[38]) << 8) | ZeroExt(4, next_ip)
    values = possible_values(pair, solver, 4097)
    grouped = {}
    for value in values:
        grouped.setdefault(value & 0xff, []).append((value >> 8) & 0xf)
    print(f"next/r38 for {source:02X} key={key_x},{key_y}")
    for target, r38s in sorted(grouped.items()):
        print(f"  {target:02X}: " + " ".join(f"{x:X}" for x in r38s))


def classify_stack_commands(key_x=0, key_y=0):
    classifications = {}
    for source in range(256):
        initial = State(f"sp_{source}_{key_x}_{key_y}")
        final = execute_command(initial, source, key_x, key_y)
        old = [ZeroExt(4, initial.st[36 + lane]) |
               (ZeroExt(4, initial.st[39 + lane]) << 4) for lane in range(3)]
        new = [ZeroExt(4, final.st[36 + lane]) |
               (ZeroExt(4, final.st[39 + lane]) << 4) for lane in range(3)]
        pushed = (source & 0xF0) | ((source + 1) & 15)
        candidates = {'same': old, 'rotate': [old[1], old[2], old[0]],
                      'push': [BitVecVal(pushed, 8), old[0], old[1]]}
        conditions = {name: And(*[a == b for a, b in zip(new, values)])
                      for name, values in candidates.items()}
        solver = base_solver(initial, source)
        solver.add(~Or(*conditions.values()))
        assert solver.check() != sat, f"unclassified stack operation {source:02X}"
        possible = []
        for name, condition in conditions.items():
            solver = base_solver(initial, source)
            solver.add(condition)
            for other in conditions:
                if other != name:
                    solver.add(~conditions[other])
            if solver.check() == sat:
                possible.append(name)
        classifications[source] = possible
    for kind in ('same', 'rotate', 'push'):
        print(f"stack {kind}: " + " ".join(f"{ip:02X}" for ip, kinds in
              classifications.items() if kind in kinds))
    print('PASS: every stack transition is identity, full-byte rotation, or PC-nibble+1 push')
    return classifications


if __name__ == "__main__":
    print("Use check_symbolic.py, check_ms_facts.py, check_ms_gates.py, or analyze_gates.py.")
