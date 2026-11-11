#!/usr/bin/env python3
"""Calibrate a three-core offload model from the actual PicoCalc measurements.

No device I/O. Forecasts are estimates, never substituted for measurements.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
B = ROOT / '.build/mk61ai/m3-int8/run270'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def exercised_matrices(mats, result):
    # Only the first prefill skips the classifier in this archived workload.
    prefill, decode = result['prefill_tokens'], result['decode_tokens']
    return mats[:-1]*(prefill+decode) + mats[-1:]*(max(0,prefill-1)+decode)

def baseline_profile(mats, document):
    if (not document['ok'] or document['actual_hz'] != 270000000 or
            document['config']['cores'] != 2 or not document['matching_checksums']):
        raise ValueError('Expected the complete, matching two-core 270 MHz reference')
    target = document['results'][-1]
    baseline = target['decode_us']/target['decode_tokens']/1e6
    exercised = exercised_matrices(mats,target)
    macs = sum(m['rows']*m['cols'] for m in exercised)
    decode_macs = sum(m['rows']*m['cols'] for m in mats)
    # matmul_us encloses local compute and the core-1 join, but excludes
    # PSRAM read/wait, norm/attention, quantization and output processing.
    # Scale the mixed prefill/decode counter by MAC count. This is an estimate
    # of decode linear time, not a separately measured decode-only profile.
    linear = target['matmul_us']/1e6*decode_macs/macs
    if not 0 <= linear <= baseline:
        raise ValueError('Inconsistent baseline linear-time counter')
    return target, dict(baseline_seconds=baseline,measured_matmul_seconds=target['matmul_us']/1e6,
        measured_workload_macs=macs,estimated_decode_linear_seconds=linear,
        estimated_decode_other_seconds=baseline-linear,estimated_parallel_fraction=linear/baseline,
        estimation='Mixed prefill/decode matmul counter scaled by MAC count; uniform cost per MAC')

def matrices(path):
    data = path.read_bytes()
    h = struct.unpack_from('<32I', data)
    if data[:8] != b'M61AI01\0' or h[2] != 1 or h[3] != len(data):
        raise ValueError('Unsupported model package')
    layers, hidden, intermediate, heads, kv_heads, head_dim, vocab, context = h[4:12]
    indices = [2+11*layer+offset for layer in range(layers) for offset in (1,2,3,6,8,9,10)] + [0]
    result = []
    for index in indices:
        rows, cols, bits, grid, at, scale, size, scales = struct.unpack_from('<8I', data, h[15]+index*32)
        if bits != 4 or grid != 0 or size != rows*cols//2 or scales != rows*cols//16:
            raise ValueError('This model describes Q4 nibbles and FP16/group32 scales')
        result.append(dict(index=index, rows=rows, cols=cols, bytes_per_row=(size+scales)/rows))
    return result, dict(layers=layers, hidden=hidden, intermediate=intermediate, vocab=vocab, context_capacity=context)

# Exact framed-byte counts of the installed protocol, excluding occasional
# extra COBS blocks at long nonzero runs. Requests have two delimiters; replies
# have one. S3_WRITE carries a four-byte offset and at most252 data bytes.
def writes(n):
    chunks = math.ceil(n/252)
    return n+37*chunks, chunks

def prepare_cost(cols, protocol, rate, latency):
    header_bytes, header_calls = writes(16)
    vector_bytes, vector_calls = writes(cols*9//8)
    if protocol == 'stop_wait':
        # START + READ(12), twice (prepare header and activation vector).
        return (header_bytes+vector_bytes+2*(49+57))/rate + (header_calls+vector_calls+4)*latency
    # START_RESULT returning12 bytes:31 request +38 reply, twice.
    return (header_bytes+vector_bytes+2*69)/rate + (header_calls+vector_calls+2)*latency

def job_wire(cols, rows, protocol):
    stage_bytes, stage_calls = writes(16+rows*cols*9//16)
    if protocol == 'stop_wait':
        return stage_bytes+49+65+45+4*rows, stage_calls+3, stage_bytes, stage_calls
    return stage_bytes+57+4*rows, stage_calls+1, stage_bytes, stage_calls

def calibrate(mats, measurements, rate):
    # Measurements contain four forwards, with the first prefill omitting the
    # head. Compute their real weight volume and preparation commands exactly.
    observations = []
    for path in measurements:
        value=json.loads(path.read_text());r=value['results'][0]
        exercised = exercised_matrices(mats,r)
        total_rows = sum(m['rows'] for m in exercised)
        vector_wire = sum(prepare_cost(m['cols'],'stop_wait',1,0) for m in exercised)
        vector_calls = sum(prepare_cost(m['cols'],'stop_wait',1,1)-prepare_cost(m['cols'],'stop_wait',1,0) for m in exercised)
        if (not value['ok'] or value['actual_hz'] != 270000000 or r['rows'] != total_rows or
                not value['matching_checksums'] or not value['matching_tokens'] or
                r['m3']['vectors'] != len(exercised) or r['remote_jobs'] != r['remote_rows']):
            raise ValueError('Only complete, matching270MHz measurements can calibrate this model')
        if r['remote_fallbacks'] or r['m3']['error'] or r['m3']['uart_errors']:
            raise ValueError('A partial M3 run is not performance evidence')
        tile = total_rows//r['remote_rows']
        if tile*r['remote_rows'] != total_rows or tile not in (8,64):
            raise ValueError('Unexpected one-row offload layout')
        wire = sum(math.ceil(m['rows']/tile)*job_wire(m['cols'],1,'stop_wait')[0] for m in exercised)
        calls = 4*r['remote_jobs']
        # The older8-row run polled STATUS a few additional times.
        extra = r['m3']['requests']-calls-int(vector_calls)
        if extra < 0: raise ValueError('Protocol accounting mismatch')
        wire += 65*extra;calls += extra
        actual_wire = r['m3']['sent']+r['m3']['received']
        if wire+vector_wire != actual_wire:
            raise ValueError('Framed-byte accounting does not match the measured UART counters')
        seconds = (r['remote_submit_us']+r['remote_wait_us'])/1e6
        observations.append(dict(path=str(path),sha256=sha(path),tile_rows=tile,decode_seconds=r['decode_us']/r['decode_tokens']/1e6,
            offload_jobs=r['remote_jobs'],offload_path_seconds=seconds,wire_bytes=r['m3']['sent']+r['m3']['received'],
            requests=r['m3']['requests'],actual_prefetches=r['prefetches'],
            protocol_bytes_reconstructed=wire+vector_wire,protocol_bytes_match=True,
            offload_path_ms_per_job=seconds/r['remote_jobs']*1000,
            residual_latency_per_request_us=1e6*(seconds-wire/rate)/calls,
            activation_latency_per_request_us=1e6*(r['remote_prepare_us']/1e6-vector_wire/rate)/vector_calls,
            maximum_m3_group_us=r['m3']['max_slice_us']))
    return observations

def forecast(mats, a, b, c, protocol, baseline, rate, latency, activation_latency, group_us, fraction):
    total_macs=sum(m['rows']*m['cols'] for m in mats)
    # Fraction1 is intentionally optimistic: it treats every baseline second
    # as parallel linear work. Smaller fractions retain a serial Amdahl term.
    pico_seconds_per_mac=baseline*fraction*2/total_macs
    predicted=baseline*(1-fraction)
    remote_jobs=remote_rows=wire_total=0
    for m in mats:
        prep=prepare_cost(m['cols'],protocol,rate,activation_latency) if c else 0
        cpu_path=0.0;remote_path=prep;elapsed=prep
        for at in range(0,m['rows'],a+b+c):
            count=min(a+b+c,m['rows']-at)
            n3=min(c,max(0,count-2));nlocal=count-n3
            n0=(nlocal+1)//2;n1=nlocal//2
            cpu=max(n0,n1)*m['cols']*pico_seconds_per_mac
            if not n3:elapsed+=cpu;cpu_path+=cpu;continue
            remote_jobs+=1;remote_rows+=n3
            nbytes,ncalls,stage_bytes,stage_calls=job_wire(m['cols'],n3,protocol)
            wire_total+=nbytes
            stage=stage_bytes/rate+stage_calls*latency
            kernel=n3*m['cols']/32*group_us/1e6
            cpu_path+=cpu
            if protocol == 'stop_wait':
                start=49/rate+latency
                tail=(65+45+4*n3)/rate+2*latency
                elapsed+=stage+start+max(cpu,max(0,kernel-start))+tail
            else:
                rest=(nbytes-stage_bytes)/rate+latency+kernel
                elapsed+=stage+max(cpu,rest)
            remote_path+=nbytes/rate+ncalls*latency+kernel
        predicted += max(cpu_path,remote_path) if protocol == 'pipelined' else elapsed
    columns=max(m['cols']for m in mats)
    return dict(layout=[a,b,c],protocol=protocol,estimated_seconds=predicted,speedup_vs_baseline=baseline/predicted,
        remote_jobs_per_decode=remote_jobs,remote_rows_per_decode=remote_rows,job_wire_bytes_per_decode=wire_total,
        fits_current_512_byte_input=16+c*columns*9//16<=512,
        additional_M3_weight_storage_bytes=c*columns*9//16,
        M3_arena_remaining_after_weights_before_new_code=6144-2916-c*columns*9//16,
        estimated_Pico_heap_peak=102028+(a+b+c-64)*(2*columns*9//16+4),Pico_heap_capacity=109628,
        hardware_measured=protocol=='stop_wait' and (a,b,c) in ((4,3,1),(32,31,1)),
        implementation=('measured' if protocol=='stop_wait' and c==1 else
                        'host-tested, not device-tested' if protocol=='deferred' and c==1 else 'hypothetical'))

def selective_forecast(mats, batch, baseline, rate, latency, activation_latency, group_us, fraction):
    """Choose both the number and frequency of remote rows for each matrix.

    Pico cores run continuously, using small SRAM tiles independently of the
    remote batch. The entire remote lane (including preparation) overlaps
    with local work, and has no host CPU cost: a deliberately optimistic
    scheduling hypothesis. It requires a different transport/dispatcher.
    Never require all matrices to offload if their setup cost cannot amortize.
    """
    macs = sum(m['rows']*m['cols'] for m in mats)
    pico_seconds_per_mac = baseline*fraction*2/macs
    total = baseline*(1-fraction)
    decisions = []
    for (rows,cols),multiplicity in Counter((m['rows'],m['cols']) for m in mats).items():
        local_only = math.ceil(rows/2)*cols*pico_seconds_per_mac
        best = dict(estimated_seconds=local_only,remote_rows=0,local_core0_rows=math.ceil(rows/2),
                    local_core1_rows=rows//2,jobs=0,last_job_rows=0,local_seconds=local_only,
                    remote_seconds=0,wire_bytes=0)
        prep = prepare_cost(cols,'deferred',rate,activation_latency)
        times,wire = {0:0.0},{0:0}
        for n in range(1,batch+1):
            nbytes,ncalls,_,_ = job_wire(cols,n,'deferred')
            wire[n] = nbytes
            times[n] = nbytes/rate+ncalls*latency+n*cols/32*group_us/1e6
        for remote in range(1,rows+1):
            full,tail = divmod(remote,batch)
            local0,local1 = math.ceil((rows-remote)/2),(rows-remote)//2
            cpu = local0*cols*pico_seconds_per_mac
            m3 = prep+full*times[batch]+times[tail]
            seconds = max(cpu,m3)
            if seconds < best['estimated_seconds']-1e-12:
                best = dict(estimated_seconds=seconds,remote_rows=remote,local_core0_rows=local0,
                    local_core1_rows=local1,jobs=full+bool(tail),last_job_rows=tail or batch,
                    local_seconds=cpu,remote_seconds=m3,
                    wire_bytes=int(prepare_cost(cols,'deferred',1,0))+full*wire[batch]+wire[tail])
        peak_rows = min(batch,best['remote_rows'])
        peak_payload = 16+peak_rows*cols*9//16 if peak_rows else 0
        best.update(rows=rows,cols=cols,multiplicity=multiplicity,baseline_linear_seconds=local_only,
                    fits_current_input=peak_payload<=512,peak_input_bytes=peak_payload,
                    fits_current_module_row_limit=peak_rows<=2)
        total += multiplicity*best['estimated_seconds']
        decisions.append(best)
    return dict(maximum_remote_batch_rows=batch,estimated_seconds=total,
        time_saved_percent=100*(1-total/baseline),speedup_vs_baseline=baseline/total,
        hardware_measured=False,implementation='hypothetical fully overlapped remote lane',
        decisions=decisions)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,default=ROOT/'.build/mk61ai/swar-v5/MODEL-NIBBLE.MKA')
    p.add_argument('--baseline',type=Path,default=ROOT/'.build/mk61ai/clock-sweep-v6/hil/CLOCK270.result/performance.json')
    p.add_argument('--measurements',type=Path,nargs='+',default=[B/'hardware-wait/performance.json',B/'hardware-tile64/performance.json'])
    p.add_argument('--baud',type=int,default=2250000)
    p.add_argument('--spi-hz',type=int,
                   help='Hypothetical SPI wire clock: 8 bits/byte; preserves the measured UART RPC residuals')
    p.add_argument('--parallel-fraction',type=float,
                   help='Override the fraction inferred from the archived matmul counter; 1 is an optimistic extreme')
    p.add_argument('--rpc-us',type=float)
    p.add_argument('--activation-rpc-us',type=float)
    p.add_argument('--m3-group-us',type=float)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if (args.baud<=0 or (args.spi_hz is not None and args.spi_hz<=0) or
            (args.parallel_fraction is not None and not 0<=args.parallel_fraction<=1)):
        p.error('Invalid rate/fraction')
    if any(v is not None and (not math.isfinite(v) or v<0)
           for v in (args.rpc_us,args.activation_rpc_us,args.m3_group_us)):
        p.error('Timing overrides must be finite and nonnegative')
    mats,config=matrices(args.model)
    rate=args.spi_hz/8 if args.spi_hz is not None else args.baud/10
    base=json.loads(args.baseline.read_text())
    # Preserve the exact already-accepted1.114016s reference: final recorded
    # optimized pass, rather than silently averaging the earlier repeat in.
    target,profile=baseline_profile(mats,base)
    baseline=profile['baseline_seconds']
    fraction=profile['estimated_parallel_fraction'] if args.parallel_fraction is None else args.parallel_fraction
    # These measurements were taken at 2.25 Mbaud. A scenario --baud must not
    # retroactively alter their calibrated non-wire residual time.
    measured_baud=2250000
    observations=calibrate(mats,args.measurements,measured_baud/10)
    latency=(max(v['residual_latency_per_request_us']for v in observations) if args.rpc_us is None else args.rpc_us)/1e6
    activation_latency=(max(v['activation_latency_per_request_us']for v in observations) if args.activation_rpc_us is None else args.activation_rpc_us)/1e6
    group_us=args.m3_group_us if args.m3_group_us is not None else max(v['maximum_m3_group_us']for v in observations)
    weights=sum(m['rows']*m['bytes_per_row']for m in mats)
    ideal_speedup=1+baseline*rate/weights
    parallel_seconds=baseline*fraction
    profile_ideal_seconds=baseline*(1-fraction)+parallel_seconds/(1+parallel_seconds*rate/weights)
    layouts=[(4,3,1),(32,31,1),(31,31,2),(32,32,2),(32,32,4),(32,32,8),(32,32,10)]
    scenarios=[forecast(mats,*layout,mode,baseline,rate,latency,activation_latency,group_us,fraction)
        for layout in layouts for mode in ('stop_wait','deferred','pipelined')]
    selective=[selective_forecast(mats,batch,baseline,rate,latency,activation_latency,group_us,fraction)
               for batch in (1,2,4,8,10)]
    jobs=[]
    pico_seconds_per_mac=baseline*fraction*2/sum(m['rows']*m['cols']for m in mats)
    for cols in sorted({m['cols']for m in mats}):
        for batch in (1,2,4,8,10):
            nbytes,ncalls,_,_=job_wire(cols,batch,'deferred')
            seconds=nbytes/rate+ncalls*latency+batch*cols/32*group_us/1e6
            jobs.append(dict(columns=cols,rows=batch,payload_bytes=batch*cols*9//16,
                payload_minimum_ms=batch*cols*9//16/rate*1000,protocol_wire_bytes=nbytes,
                assumed_total_job_ms=seconds*1000,
                local_rows_per_core_needed_to_hide_job=(math.ceil(seconds/(cols*pico_seconds_per_mac))
                                                       if pico_seconds_per_mac else None)))
    # Structural checks: no coprocessor reproduces the recorded baseline; a
    # zero-cost coprocessor cannot shorten32 rows on the critical Pico core.
    no_m3=forecast(mats,32,32,0,'pipelined',baseline,rate,latency,activation_latency,group_us,fraction)
    assert abs(no_m3['estimated_seconds']-baseline)<1e-10
    free_m3=forecast(mats,32,31,1,'pipelined',baseline,1e100,0,0,0,1)
    assert abs(free_m3['estimated_seconds']-baseline)<1e-10
    validation=[]
    for point in observations:
        layout=[4,3,1] if point['tile_rows']==8 else [32,31,1]
        # Validate against the actual UART link, not a hypothetical scenario
        # --baud/--spi-hz. The anchors were never measured over SPI.
        prediction=forecast(mats,*layout,'stop_wait',baseline,measured_baud/10,latency,
                            activation_latency,group_us,fraction)['estimated_seconds']
        validation.append(dict(layout=layout,measured_seconds=point['decode_seconds'],predicted_seconds=prediction,
            wire_transport='UART',baud=measured_baud,relative_error=(prediction/point['decode_seconds']-1)))
    result=dict(schema=2,physical_io=False,config=config,model_sha256=sha(args.model),baseline_source=str(args.baseline),baseline_sha256=sha(args.baseline),
        baseline_seconds=baseline,baseline_pass=target['pass'],
        baud=args.baud if args.spi_hz is None else None,spi_hz=args.spi_hz,
        wire_transport='UART' if args.spi_hz is None else 'hypothetical SPI',
        serial_format='8N1' if args.spi_hz is None else '8-bit SPI words',wire_bytes_per_second=rate,
        calibration_baud=measured_baud,baseline_profile=profile,
        linear_macs_per_decode=sum(m['rows']*m['cols']for m in mats),weight_and_scale_bytes_per_decode=weights,
        full_weight_transfer_minimum_seconds=weights/rate,
        optimistic_uniform_cost_instant_M3_zero_overhead_streaming_speedup=ideal_speedup,
        optimistic_streaming_seconds=baseline/ideal_speedup,
        profile_aware_ideal_streaming_seconds=profile_ideal_seconds,
        profile_aware_ideal_time_saved_percent=100*(1-profile_ideal_seconds/baseline),
        calibrated_job_residual_us_per_request=latency*1e6,
        calibrated_activation_residual_us_per_request=activation_latency*1e6,
        assumed_M3_us_per_group32=group_us,assumed_parallel_fraction=fraction,
        measured=observations,validation_against_measurements=validation,scenarios=scenarios,
        selective_scenarios=selective,per_job_estimates=jobs,
        equations=dict(
            row_payload_bytes='9*d/16 (Q4 weights plus FP16 scale per 32 weights)',
            remote_job_seconds='framed_bytes/(baud/10) + rpc_count*rpc_latency + rows*d/32*group_seconds',
            ideal_overlapped_matrix_seconds='max(ceil((matrix_rows-remote_rows)/2)*d*pico_seconds_per_mac, prepare_seconds+sum(remote_job_seconds))',
            token_seconds='unaffected_seconds + sum(matrix_seconds)',
            profile_aware_bandwidth_limit='unaffected_seconds + linear_seconds/(1+linear_seconds*wire_bytes_per_second/weight_bytes)'),
        limitations=[
            'Only stop_wait layouts4+3+1 and32+31+1 were measured; the other rows are forecasts.',
            'The64-row measurement had DMA prefetch disabled by the2048-byte limit; anchors are not a controlled DMA ablation.',
            'RPC residual includes resident scheduling, host work and exposed M3 time; these are not separately identified.',
            'The maximum measured16us group time is used conservatively, not as a measured mean.',
            'The baseline decode linear fraction is estimated from a mixed prefill/decode counter; the remainder is held fixed.',
            'Pipelined means complete overlap of activation/weight transfers with Pico compute; it is not implemented.',
            'Selective forecasts assume independent small Pico tiles and remote batching, no per-tile join, and zero host CPU cost for UART.',
            'Batches exceeding512bytes require a new staging API; their request counts are optimistic.',
            'RAM estimates exclude added staging/driver code and allocations; they are necessary conditions, not proof of fit.',
            'The optimistic speedup uses uniform cost per MAC, a fully parallel baseline and instantaneous M3 arithmetic.',
            'These measurements use the frozen3M model, full8192 vocabulary, and short decode context.'
        ])
    if args.spi_hz is not None:
        result['limitations'].extend([
            'SPI changes only the nominal wire rate in this scenario; UART framing byte counts and calibrated RPC residuals are retained.',
            'SPI setup, readiness handshakes, inter-word gaps, pin routing and background service costs have not been measured.',
            'SPI forecasts require hardware routing changes on this board; current PC10/PC11 UART wiring is not an F103R8 SPI port.'
        ])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ('baseline_seconds','linear_macs_per_decode','weight_and_scale_bytes_per_decode','full_weight_transfer_minimum_seconds','calibrated_job_residual_us_per_request','calibrated_activation_residual_us_per_request','profile_aware_ideal_streaming_seconds','profile_aware_ideal_time_saved_percent')},indent=2))
    for layout in layouts:
        values=[s for s in scenarios if s['layout']==list(layout)]
        print('+'.join(map(str,layout)), ' '.join(f'{s["protocol"]}={s["estimated_seconds"]:.3f}s'for s in values))
    print(f'Profile: linear {parallel_seconds:.6f}s, other {baseline-parallel_seconds:.6f}s; ideal streaming {profile_ideal_seconds:.6f}s')
    for s in selective:
        print(f'Selective batch <= {s["maximum_remote_batch_rows"]}: {s["estimated_seconds"]:.6f}s, {s["time_saved_percent"]:.3f}% shorter (hypothetical)')

if __name__=='__main__':main()
