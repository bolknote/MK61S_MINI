"""Bounded, low-duty GPU use alongside the user's Qwen service."""
import json
import subprocess
import time
import torch


def gpu_free(index):
    output=subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True)
    values=output.strip().splitlines();assert len(values)==1,'Expected one isolated visible GPU'
    return int(values[0])


def configure(policy):
    torch.cuda.set_device(policy['gpu']);total=torch.cuda.get_device_properties(policy['gpu']).total_memory
    torch.cuda.set_per_process_memory_fraction(policy['allocator_MiB']*2**20/total,device=policy['gpu'])
    assert gpu_free(policy['gpu'])>=policy['minimum_free_MiB'],'Not enough shared GPU headroom; no experiment started'
    return torch.device('cuda:'+str(policy['gpu']))


def headroom(policy,status=None):
    while gpu_free(policy['gpu'])<policy['minimum_free_MiB']:
        if torch.cuda.is_initialized():torch.cuda.empty_cache()
        if gpu_free(policy['gpu'])>=policy['minimum_free_MiB']:return
        if status:status('waiting_for_shared_GPU_headroom',minimum_free_MiB=policy['minimum_free_MiB'])
        time.sleep(10)


def duty(started,policy):
    elapsed=time.monotonic()-started
    time.sleep(min(30.,max(0.,elapsed*(1/policy['GPU_duty_fraction']-1))))
