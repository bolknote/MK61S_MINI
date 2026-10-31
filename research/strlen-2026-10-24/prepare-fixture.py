#!/usr/bin/env python3
"""Create an isolated, host-only research firmware source with Flash fixtures."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage

COMMIT = '92be3a44c784238ebf76429c9e9230059dbdc910'
LIMIT, STRIDE, COPIES = 2048, 2064, 8


def digest(data):
    return hashlib.sha256(data).hexdigest()


def array(name, data):
    return ('__attribute__((used,externally_visible,aligned(16)))\nconst unsigned char ' + name +
            '[' + str(len(data)) + ']={\n' +
            '\n'.join(','.join(str(value) for value in data[i:i+32]) + ',' for i in range(0,len(data),32)) + '\n};\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernels-root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--m4-phase', choices=['all','a','b'], default='all')
    args = parser.parse_args()
    destination = args.source.resolve()
    assert not destination.exists()
    destination.mkdir(parents=True)
    raw = subprocess.check_output(['git','archive','--format=tar',COMMIT], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        archive.extractall(destination, filter='data')
    strings = bytearray()
    for copy in range(COPIES):
        row = bytearray(((i*31+(i>>3)*7)%255)+1 for i in range(STRIDE))
        row[LIMIT+copy] = 0
        row[LIMIT+copy+1:] = b'\x01' * (STRIDE-LIMIT-copy-1)
        strings += row
    declarations = {}
    proofs = {}
    for cpu in ['m0','m4']:
        directory = args.kernels_root.resolve() / ('kernels-'+cpu+'-sram-v1')
        metadata = json.loads((directory/'kernels.json').read_text())
        image = ElfImage(directory/'kernels.elf')
        flash = ElfImage(args.kernels_root.resolve()/('kernels-'+cpu+'-flash-v1')/'kernels.elf')
        current = ElfImage(args.kernels_root.resolve()/('kernels-'+cpu+'-sram-v2')/'kernels.elf')
        original_blob = (directory/'kernels.bin').read_bytes()
        selected = list(metadata['functions'])
        if cpu == 'm4' and args.m4_phase == 'a':
            selected = ['baseline','libc_strlen','byte1','byte4','word1','word2']
        elif cpu == 'm4' and args.m4_phase == 'b':
            selected = ['baseline','word4','dsp1','dsp4','dsp8','dsp32']
        blob = bytearray()
        table = {}
        for name, item in metadata['functions'].items():
            start = image.symbols[name] & ~1
            def body(elf):
                address = elf.symbols[name] & ~1
                return next(elf.data[offset+address-va:offset+address-va+item['bytes']]
                    for kind,offset,va,pa,fs,ms,flags,alignment in elf.segments
                    if kind==1 and va<=address and address+item['bytes']<=va+fs)
            data = body(image)
            assert data == body(flash) == body(current)
            old_offset = start-metadata['base']
            assert original_blob[old_offset:old_offset+item['bytes']] == data
            offset = None
            if name in selected:
                blob += bytes((-len(blob)) % 16)
                offset = len(blob)
                blob += data
            table[name] = dict(offset=offset,bytes=item['bytes'],sha256=digest(data),
                granule=item['read_granule'],prefix=item['prefix_read_bytes'])
        declarations[cpu] = array('mk61_strlen_flash_code',blob)
        proofs[cpu] = dict(ELF_sha256=digest(image.data),blob_bytes=len(blob),blob_sha256=digest(blob),
            functions=table,selected=selected,leaf_bodies_byteexact_SRAM_Flash_and_runtime_build=True,
            input_and_stack_reads_only_verified_by_ARM_tests=True)
    fixture = ('/* Generated research-only constants. No firmware behavior/ABI changes. */\n'
        '#if defined(__ARM_ARCH_6M__)\n'+declarations['m0']+'#else\n'+declarations['m4']+'#endif\n'+
        array('mk61_strlen_flash_strings',strings))
    path = destination/'code/strlen_research_fixture.c'
    assert not path.exists()
    path.write_text(fixture)
    cmake = destination/'ports/picocalc/CMakeLists.txt'
    original = cmake.read_text()
    cmake.write_text(original+'\n# Research-only, not part of the shipping source.\n'
        'target_sources(mk61s-picocalc-pico-h PRIVATE "$'+'{MK61_ROOT}/code/strlen_research_fixture.c")\n'
        'target_link_options(mk61s-picocalc-pico-h PRIVATE "-Wl,-u,mk61_strlen_flash_code,-u,mk61_strlen_flash_strings")\n')
    stm32_cmake = destination/'tools/.mk61-gcc/CMakeLists.txt'
    stm32_original = stm32_cmake.read_text()
    stm32_cmake.write_text(stm32_original+'\n# Research-only, retained Flash fixtures.\n'
        'target_link_options(resident PRIVATE "-Wl,-u,mk61_strlen_flash_code,-u,mk61_strlen_flash_strings")\n')
    result = dict(status='HOST_ONLY_RESEARCH_SOURCE_READY_NOT_HARDWARE_GO',source_commit=COMMIT,
        source_tree=subprocess.check_output(['git','rev-parse',COMMIT+'^{tree}'],cwd=ROOT,text=True).strip(),
        source=str(destination), archive_sha256=digest(raw),
        delta=dict(generated_fixture=dict(path=str(path),sha256=digest(path.read_bytes())),
            pico_CMake=dict(before_sha256=digest(original.encode()),after_sha256=digest(cmake.read_bytes())),
            STM32_CMake=dict(before_sha256=digest(stm32_original.encode()),after_sha256=digest(stm32_cmake.read_bytes()))),
        m4_phase=args.m4_phase,kernels=proofs, data=dict(limit=LIMIT,stride=STRIDE,copies=COPIES,bytes=len(strings),
            sha256=digest(strings),first_NUL_offsets=[LIMIT+i for i in range(COPIES)],
            source_pointer='base+copy*stride+limit+copy-length; copy=(alignment+length)&7',
            matched_SRAM_bytes=True,hardware_access=False),
        source_or_ports_outside_this_new_snapshot_changed=False,hardware_GO=False)
    (destination.parent/'fixture-source-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],source=str(destination),data_bytes=len(strings),
        kernel_bytes={cpu:proofs[cpu]['blob_bytes'] for cpu in proofs}),indent=2))


if __name__ == '__main__':
    main()
