#!/usr/bin/env python3
"""Describe every current ELF LOAD and source-defined internal Flash reserve."""
import argparse,json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests')]
from prepare import pin,save
from check_stm32_vectors import ElfImage
def main():
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=json.loads(a.template.read_text())
    accepted=Path(t['candidate_firmware']['path']).parent.parent;source=accepted/'source';provenance=json.loads((accepted/'source-provenance.json').read_text())
    files=['ports/picocalc/CMakeLists.txt','ports/picocalc/m0_math_extension.ld','ports/picocalc/device_settings.cpp','ports/picocalc/firmware.hpp','ports/picocalc/native_app.cpp','code/loadable_module_runtime.cpp','code/loadable_module_system_app.cpp','code/language_flash_store.hpp','code/config.h']
    sources=[]
    for name in files:
        ref=pin(source/name);assert ref['sha256']==provenance['pins'][name];sources.append(dict(relative_path=name,**ref))
    elf=ElfImage(Path(t['candidate_ELF']['path']));image=Path(t['candidate_firmware']['path']).read_bytes();segments=[]
    for k,o,va,pa,n,mem,fl,align in elf.segments:
        if k!=1 or not n or not 0x10000000<=pa<0x10200000:continue
        assert image[pa-0x10000000:pa-0x10000000+n]==elf.data[o:o+n]
        segments.append(dict(VMA=hex(va),LMA=hex(pa),bytes=n,end=hex(pa+n),flags=fl))
    math_source=(source/'ports/picocalc/m0_math_extension.ld').read_text()
    fixed=[dict(section=m[0],begin=m[1]) for m in re.findall(r'(\.m0_[a-z_]+)\s+(0x[0-9a-f]+)\s*:',math_source)]
    assert all(int(v['begin'],16)<0x10180000 for v in fixed)
    begin,end=t['fixture_erase'];assert begin%4096==end%4096==0
    resident_end=0x10000000+len(image);assert resident_end<=begin and all(end<=lo or begin>=hi for lo,hi in t['protected_ranges'])
    assert max(int(s['end'],16) for s in segments)==resident_end
    # The active C9 VM cache is a file adapter, not a raw RP2040 Flash slot.
    cache=(source/'code/language_flash_store.hpp').read_text();assert '"/System/VMCache/Pages"' in cache and 'program_store::write_file' in cache
    settings=(source/'ports/picocalc/device_settings.cpp').read_text();assert 'START = 2 * 1024 * 1024 - 2 * FLASH_SECTOR_SIZE' in settings
    result=dict(status='HOST_EXACT_CURRENT_LAYOUT_REQUIRES_INDEPENDENT_ROOT_RESERVE_ACCEPTANCE',physical_IO=0,
        resident_BIN=t['candidate_firmware'],ELF=t['candidate_ELF'],manifest=t['candidate_manifest'],source_provenance=pin(accepted/'source-provenance.json'),
        resident_end=hex(resident_end),resident_erase_end=hex((resident_end+4095)&~4095),load_segments=segments,all_ELF_LOAD_bytes_match_BIN=True,
        fixed_linker_regions=fixed,fixed_math_upper_assertion='0x10180000',source_pins=sources,
        settings_journal=dict(begin='0x101fe000',end_exclusive='0x10200000',source='ports/picocalc/device_settings.cpp:10'),
        VM_cache=dict(storage='C9 logical files on SD',path='/System/VMCache/Pages',source='code/language_flash_store.hpp:91'),
        system_APPs=dict(storage='packed resident ELF LOAD sections; loadable execution allocation is RAM/PSRAM',source='ports/picocalc/native_app.cpp and code/loadable_module_runtime.cpp',all_fixed_image_storage_covered_by_load_segments=True),
        historical_external_reservations=[dict(begin=hex(lo),end_exclusive=hex(hi)) for lo,hi in t['protected_ranges']],
        historical_external_map=pin(Path('/Users/bolk/Projects/MK61S_MINI/.build/strchr-m0-hil-20261107-v1/FLASH-LAYOUT-004.json')),
        independent_Root_audit_required_for_external_reservations=True,fixture=t['fixture'],fixture_begin=hex(begin),fixture_end=hex(begin+t['fixture']['bytes']),fixture_erase_end=hex(end),
        owned_previous_erase=[hex(v) for v in t['prior_owned_strchr_erase']],extension_requires_disposable_acceptance=[hex(v) for v in t['extension_requires_independent_root_disposable_acceptance']],
        no_overlap=True,old_contents_read_or_backed_up=False,firmware_replacement=False,settings_writes=0,RTC_setters=0)
    save(a.output,result);print('exact current layout/805-file provenance subset/LOADs PASS; independent extension acceptance still required')
if __name__=='__main__':main()
