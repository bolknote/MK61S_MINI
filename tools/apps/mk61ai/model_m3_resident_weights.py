#!/usr/bin/env python3
"""Estimate M3 offload with weights loaded once, using the archived 270 MHz reference.

Host calculation only. The cached-weight module and background dispatcher are
proposals, not implemented or measured firmware. Both full logits and greedy
argmax replies are modeled; argmax cannot replace logits for general sampling.
"""
import argparse
import json
import math
from pathlib import Path

import model_m3_offload as offload

ROOT = offload.ROOT


def cache_budgets(firmware, module, module_growth=512, safety_gap=2048,
                  flash_cache_bytes=32768, flash_header=64):
    # The module arena is ALREADY included in firmware global_ram_bytes.
    # Expand it only into the remaining gap, retaining the existing 4 KiB
    # stack and the linker's 2 KiB unallocated safety gap.
    ram_gap = 20480-firmware['global_ram_bytes']-firmware['stack_reserved_bytes']
    if ram_gap != firmware['ram_unallocated_bytes']:
        raise ValueError('Inconsistent firmware RAM accounting')
    arena_spare = module['memory_limit']-module['memory_bytes']
    current = max(0,arena_spare-module_growth)
    expanded = max(0,arena_spare+max(0,ram_gap-safety_gap)-module_growth)
    page = firmware['flash']['page_bytes']
    flash_base = int(firmware['flash']['start'],16)
    settings_start = int(firmware['flash']['preserved_settings'][0],16)
    image_end = flash_base+math.ceil(firmware['image_bytes']/page)*page
    flash_free = settings_start-image_end
    if (flash_free<0 or flash_cache_bytes>flash_free or flash_cache_bytes%page or
            flash_cache_bytes<flash_header):
        raise ValueError('Flash cache does not fit whole pages before settings')
    return dict(ram_bytes=20480,flash_bytes=65536,firmware_globals=firmware['global_ram_bytes'],
        stack_reserved=firmware['stack_reserved_bytes'],unallocated_ram=ram_gap,
        module_arena_limit=module['memory_limit'],module_code_and_bss=module['memory_bytes'],
        arena_spare_before_new_code=arena_spare,proposed_module_growth_and_metadata=module_growth,
        retained_ram_safety_gap=safety_gap,current_slot_weight_budget=current,
        expanded_slot_weight_budget=expanded,flash_page_bytes=page,
        flash_page_aligned_free_bytes=flash_free,flash_cache_partition_bytes=flash_cache_bytes,
        flash_cache_header_bytes=flash_header,flash_weight_budget=flash_cache_bytes-flash_header,
        flash_pages_left_for_firmware_growth=flash_free-flash_cache_bytes)


def resident_wire(columns, rows, output):
    """A proposed fused VECTOR_RUN followed by cached-vector RUN ranges.

    WRITE input: 16-byte descriptor plus INT8 vector and group32 FP32 scales.
    START_RESULT: at most 244 bytes of output, i.e. 61 float logits per job.
    Each subsequent range reuses the vector and sends only a descriptor.
    COBS totals follow the same convention as the calibrated streaming model.
    """
    if not rows:
        return dict(bytes=0,rpcs=0,jobs=0,activation_bytes=0,result_bytes=0)
    activation = columns*9//8
    chunks = [8] if output=='argmax' else [4*min(61,rows-at) for at in range(0,rows,61)]
    wire=calls=0
    for i,result in enumerate(chunks):
        stage,nwrite=offload.writes(16+(activation if i==0 else 0))
        # 31-byte START_RESULT request; 26-byte reply prefix plus result.
        wire += stage+57+result
        calls += nwrite+1
    return dict(bytes=wire,rpcs=calls,jobs=len(chunks),activation_bytes=activation,
                result_bytes=sum(chunks))


def resident_case(name, bank_budgets, head, result, group_us=16, scheduler_gap_us=0):
    baseline = result['baseline_seconds']
    linear = baseline*result['assumed_parallel_fraction']
    seconds_per_mac = 2*linear/result['linear_macs_per_decode']
    cols,rows = head['cols'],head['rows']
    row_bytes = int(head['bytes_per_row'])
    # Keep complete rows within each memory bank; do not assume their bytes
    # form one contiguous allocation across SRAM and Flash.
    bank_rows = [budget//row_bytes for budget in bank_budgets]
    cached = min(rows,sum(bank_rows))
    cached -= cached%2  # Removing one odd row does not shorten the busy M0.
    head_base = math.ceil(rows/2)*cols*seconds_per_mac
    local0,local1 = math.ceil((rows-cached)/2),(rows-cached)//2
    local = local0*cols*seconds_per_mac
    groups = cached*cols//32
    rate = result['wire_bytes_per_second']
    latency = result['calibrated_job_residual_us_per_request']/1e6
    kernel = groups*group_us/1e6
    gap = groups*scheduler_gap_us/1e6
    cases=[]
    for output in ('logits','argmax'):
        traffic = resident_wire(cols,cached,output)
        transfer = traffic['bytes']/rate+traffic['rpcs']*latency
        remote = transfer+kernel+gap
        # Only this classifier changes; all other measured baseline work
        # remains. Offload transfers are assumed to run in the background.
        token = baseline-head_base+max(local,remote)
        cases.append(dict(output=output,token_seconds=token,time_saved_ms=(baseline-token)*1000,
            time_saved_percent=100*(1-token/baseline),remote_seconds=remote,
            remote_kernel_seconds=kernel,assumed_scheduler_gap_seconds=gap,
            transport_seconds=transfer,traffic=traffic,fully_hidden=remote<=local,
            maximum_effective_group_us_to_hide=(max(0,local-transfer)*1e6/groups if groups else None)))
    saved_compute = head_base-local
    return dict(name=name,weight_bank_budgets=bank_budgets,cached_rows=cached,
        cached_weights_and_scales_bytes=cached*row_bytes,cached_parameters=cached*cols,
        local_core0_rows=local0,local_core1_rows=local1,local_classifier_seconds=local,
        baseline_classifier_seconds=head_base,
        compute_saving_upper_bound_ms=saved_compute*1000,
        one_time_weight_upload_wire_floor_ms=cached*row_bytes/rate*1000,
        minimum_tokens_to_amortize_wire_only=(math.ceil(cached*row_bytes/rate/saved_compute)
                                             if saved_compute else None),
        predictions=cases)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-results',type=Path,default=ROOT/'.build/mk61ai/m3-int8/model/results.json')
    p.add_argument('--model',type=Path,default=ROOT/'.build/mk61ai/swar-v5/MODEL-NIBBLE.MKA')
    p.add_argument('--firmware-manifest',type=Path,default=ROOT/'firmware/picocalc-southbridge/manifest.json')
    p.add_argument('--module-manifest',type=Path,default=ROOT/'.build/mk61ai/m3-int8/module/manifest.json')
    p.add_argument('--module-growth-reserve',type=int,default=512)
    p.add_argument('--m3-group-us',type=float)
    p.add_argument('--scheduler-gap-us',type=float,default=0,
                   help='Additional service/scheduling delay per group32; not a measured value')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.module_growth_reserve<0 or any(v is not None and (not math.isfinite(v) or v<0)
        for v in (args.m3_group_us,args.scheduler_gap_us)):
        p.error('Reserves and timings must be finite and nonnegative')
    prior=json.loads(args.model_results.read_text())
    fw=json.loads(args.firmware_manifest.read_text())
    module=json.loads(args.module_manifest.read_text())
    if offload.sha(args.model)!=prior['model_sha256']:
        raise ValueError('Model does not match the frozen performance reference')
    mats,config=offload.matrices(args.model)
    head=mats[-1]
    budgets=cache_budgets(fw,module,args.module_growth_reserve)
    group_us=prior['assumed_M3_us_per_group32'] if args.m3_group_us is None else args.m3_group_us
    banks=[('current_module_SRAM',[budgets['current_slot_weight_budget']]),
           ('expanded_module_SRAM',[budgets['expanded_slot_weight_budget']]),
           ('Flash_32_KiB_partition',[budgets['flash_weight_budget']]),
           ('expanded_SRAM_plus_Flash',[budgets['expanded_slot_weight_budget'],budgets['flash_weight_budget']])]
    scenarios=[resident_case(name,b,head,prior,group_us,args.scheduler_gap_us)for name,b in banks]
    # Sweep unmeasured per-group service delays instead of mistaking the
    # measured 16 us maximum invocation time for a complete job throughput.
    sensitivity=[dict(scheduler_gap_us=gap,scenarios=[
        resident_case(name,b,head,prior,group_us,gap)for name,b in banks])
        for gap in (0,16,64,256)]
    report=dict(schema=1,physical_io=False,hardware_measured=False,config=config,
        baseline_seconds=prior['baseline_seconds'],model_sha256=prior['model_sha256'],
        sources={str(path):offload.sha(path)for path in
                 (args.model_results,args.firmware_manifest,args.module_manifest)},
        memory=budgets,classifier=head,assumed_group_us=group_us,assumed_scheduler_gap_us=args.scheduler_gap_us,
        baseline_profile=prior['baseline_profile'],scenarios=scenarios,scheduler_sensitivity=sensitivity,
        equations=dict(row_bytes='d/2+d/16',activation_bytes='d+d/8',
            matrix_seconds='max(ceil((N-cached_rows)/2)*d*Pico_seconds_per_MAC, activation_and_result_transport+M3_compute+service_gaps)',
            token_seconds='baseline_seconds-baseline_classifier_seconds+matrix_seconds',
            uniform_cost_memory_saving_limit='baseline_linear_seconds*cached_weight_bytes/all_linear_weight_bytes'),
        limitations=[
            'The cached-weight module, fused VECTOR_RUN and background result dispatcher are proposals, not measured code.',
            '512 bytes are reserved for added module code/metadata; final fit requires compiling that module.',
            'Expanded SRAM retains the current 4 KiB stack and 2 KiB unallocated gap; the arena is not counted twice.',
            'The 32 KiB Flash partition includes a 64-byte header and leaves 3 KiB for firmware growth in this archived image.',
            'One-time upload times are wire-only lower bounds; Flash erase/program and protocol overhead are excluded.',
            'Per-group computation uses the previous maximum invocation duration, not a measured cached-job throughput.',
            'SRAM/Flash execution differences and keyboard/PMU service delays are unmeasured; group-time thresholds and sensitivity are provided.',
            'All transfers must overlap useful Pico work. Blocking submission can exceed the sub-millisecond SRAM saving.',
            'Full logits preserve the complete output vector. Argmax is only valid for greedy selection with matching filters and tie-breaking.',
            'No additional PSRAM-read saving is credited; the archived non-matmul time remains fixed.',
            'Small predicted gains are below the previous model validation error and are not evidence of a physical speedup.'
        ])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(budgets,indent=2))
    for s in scenarios:
        full=s['predictions'][0]
        print(f'{s["name"]}: {s["cached_rows"]} rows, {s["cached_weights_and_scales_bytes"]} bytes; '
              f'{full["token_seconds"]:.6f} s/token, saving {full["time_saved_percent"]:.3f}%; '
              f'remote {full["remote_seconds"]*1000:.3f} ms / local {s["local_classifier_seconds"]*1000:.3f} ms')


if __name__=='__main__':
    main()
