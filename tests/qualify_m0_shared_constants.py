#!/usr/bin/env python3
"""Qualify explicitly shared CORE-MATH tables in an actual ARM firmware ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from m0_mpfr_oracle import Oracle, bits
from native_eabi_m0_arm_self_test import Machine, nan
from unicorn import UC_HOOK_MEM_READ


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contents(elf, name):
    address, size = elf.symbols[name], elf.sizes[name]
    for section in elf.sections:
        if section[2] & 2 and section[3] <= address and address + size <= section[3] + section[5]:
            offset = address - section[3]
            return elf.bytes_at(section)[offset:offset + size]
    raise AssertionError(('Missing allocated table', name))


def corpus(path):
    values = []
    for line in path.read_text().splitlines():
        token = line.split('#', 1)[0].strip().lower()
        if not token:
            continue
        assert len(token.split()) == 1 and ',' not in token, token
        if token in ('snan', '+snan', '-snan'):
            value = 0x7ff0000000000001 | ((1 << 63) if token.startswith('-') else 0)
        else:
            value = bits(float.fromhex(token))
        values.append(value)
    assert values
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-elf', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--corpus-dir', type=Path, required=True)
    parser.add_argument('--cases-per-operation', type=int, default=2048)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    assert args.cases_per_operation >= 2
    baseline_sha, current_sha = sha(args.baseline_elf), sha(args.elf)
    baseline, current = Machine(args.baseline_elf, True), Machine(args.elf, True)
    aliases = {}
    for owner in ('cos', 'tan'):
        for table in ('S', 'C'):
            aliases[f'_ZN8core_{owner}L1{table}E'] = f'_ZN8core_sinL1{table}E'
    aliases.update({
        '_ZN10core_log10L10_INVERSE_2E': '_ZN8core_logL10_INVERSE_2E',
        '_ZN10core_log10L10_LOG_INV_2E': '_ZN8core_logL10_LOG_INV_2E',
        '_ZN10core_log10L3P_2E': '_ZN8core_logL3P_2E',
    })
    tables = []
    for old_name, shared_name in aliases.items():
        old, new = contents(baseline.elf, old_name), contents(current.elf, shared_name)
        assert old == new and old, (old_name, shared_name)
        assert contents(baseline.elf, shared_name) == new, shared_name
        tables.append(dict(original=old_name, shared=shared_name, bytes=len(old),
                           sha256=hashlib.sha256(old).hexdigest()))
    memory_symbols = ('__data_start__', '__data_end__', '__bss_start__', '__bss_end__',
                      '__end__', '__HeapLimit', '__StackBottom', '__StackTop',
                      '__StackOneBottom', '__StackOneTop', '__lcd_dma_end__')
    for name in memory_symbols:
        assert baseline.elf.symbols[name] == current.elf.symbols[name], name

    # Actual reads of these tables ensure the numerical corpus exercises the
    # changed accurate paths, rather than only their earlier fast estimates.
    touched = {name: set() for name in set(aliases.values())}
    read_counts = {name: 0 for name in touched}
    hooks = []
    for name in touched:
        address, size = current.elf.symbols[name], current.elf.sizes[name]
        def read(uc, access, location, length, value, userdata):
            table, start = userdata
            touched[table].add((location - start) // 32)
            read_counts[table] += 1
        hooks.append(current.uc.hook_add(UC_HOOK_MEM_READ, read, (name, address),
                                          begin=address, end=address + size - 1))

    oracle = Oracle()
    operations = {}
    for name, filename in (('sin', 'sin'), ('cos', 'cos'), ('tan', 'tan'),
                           ('ln', 'log'), ('log10', 'log10')):
        path = args.corpus_dir / (filename + '.wc')
        corpus_sha = sha(path)
        values = corpus(path)
        limit = min(len(values), args.cases_per_operation)
        indexes = sorted({i * (len(values) - 1) // (limit - 1) for i in range(limit)})
        before_touches = {key: len(value) for key, value in touched.items()}
        before_counts = dict(read_counts)
        digest = hashlib.sha256()
        symbol = 'mk61_m0_cr_' + name
        for index in indexes:
            x = values[index]
            expected = oracle.reference(name, x)
            before = baseline.call(symbol, x)[0]
            got = current.call(symbol, x)[0]
            assert got == before, (name, index, 'baseline mismatch', hex(x), hex(before), hex(got))
            assert got == expected or (nan(expected) and nan(got) and got & (1 << 51)), (
                name, index, 'RNE mismatch', hex(x), hex(got), hex(expected))
            digest.update(struct.pack('<4Q', x, before, got, expected))
        assert sha(path) == corpus_sha
        table_reads = {key: len(touched[key]) - before_touches[key] for key in touched}
        table_counts = {key: read_counts[key] - before_counts[key] for key in touched}
        assert any(table_counts.values()), (name, 'No shared accurate table was reached')
        operations[name] = dict(status='PASS',cases=len(indexes),wrong_rounding=0,
            baseline_mismatches=0,corpus_cases=len(values),complete_corpus=len(indexes)==len(values),
            corpus_sha256=corpus_sha,result_sha256=digest.hexdigest(),new_table_rows_read=table_reads,
            shared_table_read_count=table_counts)
        print('PASS', name, len(indexes), 'accurate hard cases', flush=True)
    for hook in hooks:
        current.uc.hook_del(hook)
    assert sha(args.elf) == current_sha and sha(args.baseline_elf) == baseline_sha
    assert all(touched.values()), 'Every shared table must be read by the actual ARM code'
    allocated = lambda elf: sum(section[5] for section in elf.sections if section[2] & 2 and section[1] != 8)
    report = dict(status='PASS',elf_sha256=current_sha,baseline_elf_sha256=baseline_sha,
        identical_table_aliases=tables,shared_duplicate_table_bytes=sum(row['bytes'] for row in tables),
        allocated_payload_saving_bytes=allocated(baseline.elf)-allocated(current.elf),
        static_ram_and_stack_boundaries_unchanged=list(memory_symbols),operations=operations,
        shared_table_rows_read={key:len(value) for key,value in touched.items()},mpfr=oracle.version,
        abi='Every actual ARM call checks R4-R11, SP and bounded stack writes.',
        scope='All shared table bytes are identical. Deterministic samples span each complete saved hard-case file; numerical testing is finite. Fixed extension placements can keep the UF2 image extent unchanged despite a smaller allocated payload.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
