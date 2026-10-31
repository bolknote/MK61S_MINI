#!/usr/bin/env python3
"""Freeze host-only strlen payload and pins for Root review, never hardware GO."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COMMIT='92be3a44c784238ebf76429c9e9230059dbdc910'


def pin(path):
    path=Path(path).resolve()
    data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    build=a.build_root.resolve();out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    files={}
    def add(path):
        path=Path(path).resolve()
        files[str(path)]=pin(path)
    for path in HERE.iterdir():
        if path.is_file():
            shutil.copyfile(path,out/path.name)
    shutil.copyfile(ROOT/'tests/system_strlen_arm_self_test.py',out/'system_strlen_arm_self_test.py')
    archive=subprocess.check_output(['git','archive','--format=tar',COMMIT],cwd=ROOT)
    original={}
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tar:
        for member in tar:
            if member.isfile():
                original[member.name]=tar.extractfile(member).read()
    sources=[]
    for dirname in ['research-fw-v3a','research-fw-v3b','research-fw-v2']:
        directory=build/dirname
        source=directory/'source'
        changed=[]
        for name,data in original.items():
            current=(source/name).read_bytes()
            if current!=data:
                assert name in ['ports/picocalc/CMakeLists.txt','tools/.mk61-gcc/CMakeLists.txt']
                assert current.startswith(data) and b'# Research-only' in current[len(data):]
                changed.append(name)
                add(source/name)
        assert set(changed)=={'ports/picocalc/CMakeLists.txt','tools/.mk61-gcc/CMakeLists.txt'}
        actual={str(path.relative_to(source)) for path in source.rglob('*') if path.is_file()}
        extra=actual-set(original)
        byproducts={name for name in extra if name.startswith('tests/__pycache__/check_stack_usage.cpython-') and name.endswith('.pyc')}
        assert extra-byproducts=={'code/strlen_research_fixture.c'}, sorted(extra)
        add(source/'code/strlen_research_fixture.c')
        add(directory/'fixture-source-manifest.json')
        sources.append(dict(source=str(source),base_commit=COMMIT,tracked_regular_files=len(original),
            unchanged_regular_files=len(original)-len(changed),changed=changed,added=sorted(extra-byproducts),
            ignored_builder_bytecode=sorted(byproducts),
            archive_sha256=hashlib.sha256(archive).hexdigest(),normal_source_unchanged=True))
    phases=[]
    for cpu,phase,experiment_dir,proof_dir,decoder in [
        ('m4','a','classic-a-apps-v2','classic-a-proof-v2','classic-a-decoder-test-v1.json'),
        ('m4','b','classic-b-apps-v2','classic-b-proof-v2','classic-b-decoder-test-v1.json'),
        ('m0','all','pico-apps-v4','pico-proof-v4','pico-decoder-test-v1.json')]:
        d=build/experiment_dir
        exp=json.loads((d/'experiment.json').read_text())
        anchor=json.loads(Path(exp['anchors']['path']).read_text())
        corpus=json.loads(Path(exp['corpus']['path']).read_text())
        for path in d.rglob('*'):
            if path.is_file():add(path)
        for ref in anchor['firmware'].values():
            if ref:add(ref['path'])
        for path in (build/proof_dir).iterdir():
            if path.is_file():add(path)
        add(build/decoder)
        proof=json.loads((build/proof_dir/'proof.json').read_text())
        assert proof['status']=='PASS_HOST_ONLY_NOT_HARDWARE' and proof['physical_timings']==0
        tests=json.loads((build/decoder).read_text())
        assert tests['status']=='PASS_HOST_ONLY' and tests['physical_reports']==0
        for key in ['ELF','BIN']:
            assert pin(anchor['firmware'][key]['path'])==anchor['firmware'][key]
        floor=131072 if cpu=='m4' else None
        if floor:assert 524288-anchor['firmware']['BIN']['bytes']>=floor
        phases.append(dict(cpu=cpu,phase=phase,experiment=pin(d/'experiment.json'),
            anchors=pin(d/'anchors.json'),corpus=pin(d/'corpus.json'),
            proof=pin(build/proof_dir/'proof.json'),decoder_tests=pin(build/decoder),
            build=f'{anchor["build"]:08X}',crc=f'{anchor["crc32"]:08X}',
            firmware=anchor['firmware'],Flash_headroom_floor=floor,
            Flash_candidate_mask=[leaf['offset'] is not None for leaf in anchor['leaves']],
            APPs=4,batches=4*len(corpus['batches']),groups=4*corpus['groups'],rounds=7,
            namespace=exp['directory'],physical_timings=0))
    for directory in ['kernels-m0-sram-v1','kernels-m4-sram-v1','kernels-m0-flash-v1','kernels-m4-flash-v1',
                      'kernels-m0-sram-v2','kernels-m4-sram-v2','kernels-m0-flash-v2','kernels-m4-flash-v2']:
        for path in (build/directory).iterdir():
            if path.is_file():add(path)
    for relative in ['tests/check_stm32_vectors.py','tools/.mk61-app/app_relocations.py',
                     'tools/.mk61-app/mk61_module_pack.py','tools/build_portable_app.py',
                     'sdk/portable/memory.c','sdk/portable/start.c','sdk/portable/shared_runtime.c',
                     'sdk/portable/system/runtime.S','code/loadable_system_runtime.def',
                     'code/loadable_app_services.h','code/loadable_app_api.h',
                     'research/rp2040-memset-2026-10-21/capture/bootrom.bin',
                     'research/rp2040-memset-2026-10-21/capture/rom.json']:
        add(ROOT/relative)
    (out/'source-proof.json').write_text(json.dumps(sources,indent=2)+'\n')
    (out/'external-pins.json').write_text(json.dumps(files,indent=2)+'\n')
    plan=dict(status='FROZEN_HOST_PACKET_INDEPENDENT_REVIEW_PENDING',scope='STRLEN_M4_M0_20261024',
        source_commit=COMMIT,source_tree=subprocess.check_output(['git','rev-parse',COMMIT+'^{tree}'],cwd=ROOT,text=True).strip(),
        owner_thread='01a15d77-6fe3-74d3-a025-dbf484687484',
        coordinator_thread='01a164b7-9caa-7011-90d1-807e9630921c',
        Classic=dict(uid='AEB505B6E0067623',serial='2068336B4731',port='/dev/cu.usbmodem2068336B47311',
            phases=['a','b'],fresh_double_full_backup_required=True,full_backup_bytes=524288,
            original_reference_admission_only='412f036e278a75beb63c96d95f4ca72798b59d66d6549e43e420261cafa602d1',
            per_image_headroom_floor=131072,original_return_in_parent_finally=True,
            switch_requires_APP_exit_owned_namespace_cleanup_and_typed_idle=True),
        Pico=dict(uid='E6657CD423721C35',port='/dev/cu.usbmodem11301',phase='all',
            queue_after_fixed_warm_native400_and_other_root_scopes=True,full_original_return_in_parent_finally=True),
        phases=phases,source_proof=pin(out/'source-proof.json'),external_pins=pin(out/'external-pins.json'),
        adapter=pin(out/'adapter.py'),decoder=pin(out/'decode.py'),
        parent_required='Separately reviewed Root-owned complete transport/restore carrier; this packet has no FD/Flash/lease implementation',
        required_return=['full original Flash readback','fresh exact files and directories','calculator/cache/typed state',
                         'RTC trajectory and unset flag','FD closed','advisory lock released','no holder','Root CLOSED'],
        hardware_GO=False,execution_enabled=False,physical_timings=0,shipping_qualified=False)
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    local={path.name:pin(path) for path in out.iterdir() if path.is_file()}
    (out/'manifest.json').write_text(json.dumps(dict(status='FROZEN_HOST_ONLY',files=local,
        hardware_GO=False,execution_enabled=False),indent=2)+'\n')
    for path in out.iterdir():
        if path.is_file():path.chmod(0o444)
    # Only owned build artifacts are protected. Source worktrees/toolchains are read-only inputs.
    for name in files:
        path=Path(name)
        if build in path.parents:path.chmod(0o444)
    print(json.dumps(dict(packet=str(out),plan=pin(out/'plan.json'),manifest=pin(out/'manifest.json'),
        external_files=len(files),physical_timings=0),indent=2))


if __name__=='__main__':
    main()
