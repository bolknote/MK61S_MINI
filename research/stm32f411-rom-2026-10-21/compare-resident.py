#!/usr/bin/env python3
"""Compare the original resident with the compiled helper in its real slot."""
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent

def main():
    original=json.loads((HERE/'flash-comparison.json').read_text())
    installed=json.loads((HERE/'flash-hil-resident/report.json').read_text())
    assert installed['status']=='PASS' and len(installed['runs'])==3
    runs=[[r for p in run['pages'] for r in p['rows']] for run in installed['runs']]
    rows=[]
    for i,before in enumerate(original['rows']):
        group=[r[i] for r in runs]
        assert all((r['bytes'],r['alignment'])==(before['bytes'],before['alignment']) for r in group)
        current=median(r['baseline_cycles'] for r in group)
        rom=median(r['cycles']['rom'] for r in group)
        rows.append({'bytes':before['bytes'],'alignment':before['alignment'],
            'original_cycles':before['baseline_cycles'],'new_resident_cycles':current,'rom_cycles':rom,
            'new_over_original':current/before['baseline_cycles'],
            'new_over_rom':current/rom,
            'rom_control_change_cycles':rom-before['cycles']['rom'],
            'same_code_other_address_change_cycles':current-median(r['cycles']['style4'] for r in group),
            'new_aa_drift_cycles':max(abs(r['before_cycles']-r['after_cycles']) for r in group)})
    large=[r for r in rows if r['bytes']>=16]
    small=[r for r in rows if r['bytes']<16]
    assert all(r['new_over_original']<1 and r['new_over_rom']<1 for r in large)
    assert max(abs(r['new_resident_cycles']-r['original_cycles']) for r in small)<=1
    summary={'status':'PASS','original_build':'3AB3DD45','candidate_build':installed['resident_candidate']['build'],
        'implementation':'Local backward aligned 16-byte fill in the existing resident bulk slot',
        'large_faster_cases':len(large),'large_cases':len(large),
        'small_cases':len(small),'small_max_change_cycles':max(abs(r['new_resident_cycles']-r['original_cycles']) for r in small),
        'large_cycle_reduction_percent':{'min':100*(1-max(r['new_over_original'] for r in large)),
            'median':100*(1-median(r['new_over_original'] for r in large)),
            'max':100*(1-min(r['new_over_original'] for r in large))},
        'versus_rom_cycle_reduction_percent':{'min':100*(1-max(r['new_over_rom'] for r in large)),
            'max':100*(1-min(r['new_over_rom'] for r in large))},
        'max_unchanged_rom_control_shift_cycles':max(abs(r['rom_control_change_cycles']) for r in rows),
        'max_same_code_address_effect_cycles':max(abs(r['same_code_other_address_change_cycles']) for r in rows),
        'max_new_aa_drift_cycles':max(r['new_aa_drift_cycles'] for r in rows),
        'checks_per_run':installed['runs'][0]['pages'][-1]['correctness_checks'],'runs':3,
        'full_flash_restored':installed['full_flash_restored'],
        'files_unchanged':installed['files_unchanged'],'state_unchanged':installed['state_unchanged'],
        'limits':['Warm DWT microbenchmark with interrupts enabled; not a whole-firmware speedup.',
            'Only the attached Classic STM32F411 was measured; F401/Mini hardware was not available.',
            'Measured resident replaces the existing function slot without relinking unrelated code. The release image was not rebuilt or left installed.'],
        'rows':rows}
    (HERE/'resident-comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},indent=2))
    for r in rows:
        if r['bytes'] in (16,64,256,4096) and r['alignment'] in (0,1):print(r)

if __name__=='__main__':main()
