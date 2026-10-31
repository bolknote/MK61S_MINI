#!/usr/bin/env python3
"""Summarise only physical INTERP002 outputs; preserve all rows and paired samples."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,statistics
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'.build/rp2040-interpolator-20261023/hardware-INTERP002'

def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def main():
 global OUT
 parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=OUT)
 OUT=parser.parse_args().directory.resolve()
 receipt=json.loads((OUT/'receipt.json').read_text())
 assert receipt['status']=='PASS_CLOSED' and receipt['measurement_complete'] and receipt['current_data_preserved'] and not receipt['failures']
 summary=dict(status='PASS_PHYSICAL_INTERP002_CLOSED',recorded_utc=datetime.now(timezone.utc).isoformat(),
  uid='E6657CD423721C35',build='A7483AE6',clock_hz=125000000,rows=0,checks=0,variants={},comparisons=[],
  method='7 alternating ABBA/BAAB rounds; raw totals, no empty subtraction. Scalar4096 calls include loop/checksum. POP/audio32 complete blocks: output writes and per-block setup/restore in transaction mode; output verification/hash follow the stop timer.',
  baseline_scope='ln uses embedded frozen A748 Q62 whole function; sqrt uses the V3-qualified compact packed-polynomial whole function; rsqrt includes Q63 Newton and exact rounding boundary. POP/audio are new complete buffer-producing kernels.',
  evidence=dict(receipt=pin(OUT/'receipt.json'),process_exit=pin(OUT/'process-exit-proof.json')))
 lines=['Physical INTERP002 / RP2040 125 MHz: PASS_CLOSED','Units: microseconds per item; POP/audio additionally show complete block microseconds.','All seven paired rounds retained in the per-APP decoded JSON files.','']
 for variant in ('lookup','pop','sqrt','rsqrt'):
  path=OUT/(variant+'-decoded.json');d=json.loads(path.read_text());assert d['hardware_verified'] and d['physical_timing'] and d['status']=='PASS'
  summary['variants'][variant]=dict(raw=pin(OUT/(variant+'-RESULT.bin')),decoded=pin(path),rows=d['rows'],checks=d['checks'])
  summary['rows']+=d['rows'];summary['checks']+=d['checks'];grouped={}
  for row in d['results']:
   key=(row['group'],row['mode'],row['block_items'] if variant=='pop' else None)
   grouped.setdefault(key,[]).append(row)
  for (group,mode,block),rows in grouped.items():
   pairs=[r for row in rows for r in row['rounds']]
   cpu=statistics.median(r['cpu_us_per_item'] for r in pairs);candidate=statistics.median(r['candidate_us_per_item'] for r in pairs)
   deltas=[r['delta_us_per_item'] for r in pairs]
   result=dict(group=group,mode=mode,block_items=block,input_streams=len(rows),paired_rounds=len(pairs),
      cpu_us_per_item=cpu,candidate_us_per_item=candidate,candidate_over_cpu=candidate/cpu,
      median_paired_delta_us_per_item=statistics.median(deltas),empirical_delta_range=[min(deltas),max(deltas)],
      per_input=[dict(input=row['input'],cpu_us_per_item=statistics.median(v['cpu_us_per_item'] for v in row['rounds']),candidate_us_per_item=statistics.median(v['candidate_us_per_item'] for v in row['rounds'])) for row in rows])
   if block:result.update(cpu_us_per_block=cpu*block,candidate_us_per_block=candidate*block)
   summary['comparisons'].append(result)
   lines.append('%-23s %-21s %s CPU %.6f  candidate %.6f  ratio %.4f' % (group,mode,('N='+str(block)) if block else '',cpu,candidate,candidate/cpu))
 assert (summary['rows'],summary['checks'])==(42,672)
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'RESULTS.txt').write_text('\n'.join(lines)+'\n')
 print('\n'.join(lines))
if __name__=='__main__':main()
