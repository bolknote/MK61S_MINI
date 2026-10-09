#!/usr/bin/env python3
"""Measure auxiliary memory/string candidates in an APP; no firmware writes."""
import argparse
import base64
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import statistics
import struct
from hil_system_memory import connect, health, require_empty, PUBLIC, STATE_COMMANDS
from hil_packbits_firmware import fingerprint
from hil_c5_stack import read_file as get_file
from hil_usb_disk_transaction import listing_entries
from hil_c6_system_bootstrap import read_file, write_file
from hil_rtc_alarm import warm_reset

REMOTE = '/MEMAUX.APP'
LENGTHS = (0,1,2,3,4,7,8,16,32,128,512,2048)
FAMILIES = ('memmove','memset','strlen','strnlen','strcmp','strncmp','memcpy')
VARIANTS = ('resident_flash','scalar_sram','candidate_sram')
SCENARIOS = (
 ('shift_left17','shift_left1','self','shift_right1','shift_right17'),
 ('zero','value_0x1234'), ('terminated',), ('limit_at_end','limit_past_nul'),
 ('equal','different_first','different_last'), ('equal','different_first','different_last'), ('disjoint',))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def parse(data, page, fixture):
    magic, version, actual, count, failures, size, family, pages, demcr, control, sink, move, fill, compare, length, copy = struct.unpack_from('<4s15I', data)
    assert (magic,version,actual,failures,pages) == (b'MAU2',2,page,0,len(LENGTHS)*7)
    assert (size,family,count) == (LENGTHS[page//7],page%7,len(SCENARIOS[page%7])*12)
    for value, name in ((move,'memmove'),(fill,'memset'),(compare,'strcmp'),(length,'strnlen'),(copy,'memcpy')):
        assert value == fixture['symbols'][name]['address'], name
    assert len(data)==128+count*12
    for i,name in enumerate(('strcmp','strnlen')):
        at=64+count*12+i*32
        assert data[at:at+32].hex() == fixture['symbols'][name]['code_hex']
    rows = []
    iterations=512 if size<=16 else 256 if size<=128 else 128 if size<=512 else 32
    for i in range(count):
        scenario,rest=divmod(i,12);align,order=divmod(rest,3);variant=(page+order)%3
        minimum,median,maximum=struct.unpack_from('<3I',data,64+i*12)
        assert minimum<=median<=maximum
        rows.append({'family':FAMILIES[family],'bytes':size,'variant':VARIANTS[variant],
                     'alignment':align,'scenario':SCENARIOS[family][scenario],'iterations':iterations,
                     'min_cycles':minimum/iterations,'median_cycles':median/iterations,'max_cycles':maximum/iterations})
    assert len({(r['variant'],r['alignment'],r['scenario']) for r in rows})==count
    return {'page':page,'demcr_before':demcr,'dwt_control_before':control,'checksum':sink,'rows':rows}


def summarize(runs):
    groups = {}
    for run in runs:
        for batch in run:
            for row in batch['rows']:
                key=(row['family'],row['bytes'],row['scenario'],row['alignment'],row['variant'])
                groups.setdefault(key,[]).append(row['median_cycles'])
    medians={k:statistics.median(v) for k,v in groups.items()}
    results=[]
    for family in FAMILIES:
        for n in LENGTHS:
            for scenario in SCENARIOS[FAMILIES.index(family)]:
                values=[{v:medians[(family,n,scenario,a,v)] for v in VARIANTS} for a in range(4)]
                candidate='candidate_sram'; scalar='scalar_sram'; resident='resident_flash'
                results.append({'family':family,'bytes':n,'scenario':scenario,'aligned_cycles':values[0],
                    'candidate_vs_scalar_speedup_range':[min(x[scalar]/x[candidate] for x in values),max(x[scalar]/x[candidate] for x in values)],
                    'resident_vs_candidate_ratio_range':[min(x[resident]/x[candidate] for x in values),max(x[resident]/x[candidate] for x in values)],
                    'worst_candidate_vs_scalar_delta_cycles':max(x[candidate]-x[scalar] for x in values)})
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--app',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--runs',type=int,default=3)
    p.add_argument('--cleanup-reference',type=Path,
                   help='clean an interrupted own APP after flushing terminal input; saved content-before.json')
    args=p.parse_args();assert 1<=args.runs<=10
    fixture=json.loads(args.fixture.read_text());app=args.app.read_bytes();out=args.output_dir.resolve()
    out.mkdir(parents=True);runs=[];installed=False
    if args.cleanup_reference:
        expected=json.loads(args.cleanup_reference.read_text())
        with connect(args.port,fixture['build']) as port:
            port.drain();port.write_line('');port.pump(.3)
            state=health(port,fixture['build']);require_empty(state)
            read_file(port,REMOTE,app)
            removed=port.command(f'rm "{REMOTE}"',timeout=15)
            assert 'Removed 1 entry.' in removed,removed
            assert fingerprint(port)==expected
            result={'status':'PASS','state':state,'own_APP_removed':True,
                    'original_file_hashes_preserved':len(expected['files'])}
            save(out/'cleanup.json',result)
            print('Own APP removed; all original file hashes and empty calculator verified',flush=True)
        return
    reserved={f'/MEMAUX{page:02}.txt' for page in range(len(LENGTHS)*7)}
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port,fixture['build']))
        before=health(port,fixture['build']);require_empty(before)
        files=fingerprint(port)
        assert not ({p.casefold() for p in reserved|{REMOTE}} & {x.casefold() for x in files['files']})
        save(out/'content-before.json',files)
        fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close()
        port=contexts.enter_context(connect(path,fixture['build']))
        print('Pinned Classic',fixture['build'],'; original file hashes recorded',flush=True)
        def remove_reports():
            entries=listing_entries(port.command('ls /',timeout=20))
            names={line.split('\t')[-1].casefold() for line in entries if line.startswith('f\t')}
            for remote in sorted(reserved):
                if remote[1:].casefold() in names:
                    removed=port.command(f'rm "{remote}"',timeout=15)
                    assert 'Removed 1 entry.' in removed,removed
        try:
            write_file(port,REMOTE,app);installed=True;read_file(port,REMOTE,app)
            for run in range(args.runs):
                # The APP exits on its own after bounded measurements and public
                # FILE_WRITE calls. No USB Screen, private writes, or key injection.
                response=port.command(f'open "{REMOTE}"',timeout=300)
                assert 'Open failed!' not in response,response
                batches=[]
                for page in range(len(LENGTHS)*7):
                    remote=f'/MEMAUX{page:02}.txt'
                    encoded=get_file(port,remote)
                    data=base64.b64decode(encoded,validate=True)
                    batches.append(parse(data,page,fixture))
                    (out/f'report-{run}-{page}.bin').write_bytes(data)
                    if page%7==6:
                        print(f'Run {run+1}: {LENGTHS[page//7]} bytes, all seven functions PASS',flush=True)
                runs.append(batches);save(out/'runs.json',runs)
                remove_reports()
            assert len({(b['demcr_before'],b['dwt_control_before']) for run in runs for b in run})==1
        finally:
            # Reset releases retained APP cache arenas before filesystem cleanup.
            fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close()
            port=contexts.enter_context(connect(path,fixture['build']))
            if installed:
                remove_reports()
                read_file(port,REMOTE,app)
                removed=port.command(f'rm "{REMOTE}"',timeout=15)
                assert 'Removed 1 entry.' in removed,removed
            after=health(port,fixture['build'])
            for c in STATE_COMMANDS:assert before[c]==after[c],c
            files_after=fingerprint(port);assert files_after==files
            save(out/'content-after.json',files_after);(out/'terminal.txt').write_bytes(port.text)
            result={'status':'PASS' if len(runs)==args.runs else 'INCOMPLETE','fixture':fixture,
                'before':before,'after':after,'app_sha256':hashlib.sha256(app).hexdigest(),'app_bytes':len(app),
                'runs':runs,'summary':summarize(runs) if runs else [],'original_file_hashes_preserved':len(files['files']),
                'transport':'Public FILE_WRITE to bounded base64 TEXT files, read over CDC; own files removed.',
                'scope':'Existing resident Flash functions vs matched scalar/candidate SRAM APP kernels. '
                    'Includes same wrapper dispatch; not a resident replacement or end-to-end throughput claim. '
                    'strcmp/strnlen private Flash addresses are qualification-only, guarded by exact firmware CRC, public anchors and code bytes.'}
            save(out/'report.json',result)
            print('Firmware unchanged; all original files/state preserved; own temporary files removed',flush=True)


if __name__=='__main__':main()
