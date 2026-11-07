"""Replay the original Q4 CUDA operations; no fusion or different arithmetic."""


class CudaQ4:
    def __init__(self, quantizer):
        self.quantizer=quantizer;self.signature=None;self.graph=None;self.output=None

    def __call__(self, weight):
        import torch
        if weight.device.type!='cuda':return self.quantizer(weight)
        signature=(weight.data_ptr(),tuple(weight.shape),tuple(weight.stride()),weight.dtype,weight.device)
        if signature!=self.signature:
            current=torch.cuda.current_stream(weight.device)
            stream=torch.cuda.Stream(device=weight.device);stream.wait_stream(current)
            with torch.cuda.stream(stream):
                for _ in range(3):warm=self.quantizer(weight)
            current.wait_stream(stream)
            graph=torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph,stream=stream):output=self.quantizer(weight)
            current.wait_stream(stream)
            self.graph=graph;self.output=output;self.signature=signature
        self.graph.replay()
        return self.output


def main():
    import argparse
    import json
    from pathlib import Path
    import statistics
    import time
    import torch
    from common import core,load_model,quantize
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',required=True)
    p.add_argument('--output',required=True);p.add_argument('--device',default='cuda');p.add_argument('--seed',type=int,default=7731)
    args=p.parse_args();assert args.device=='cuda' and not Path(args.output).exists()
    model,_,_=load_model(args);model.eval().requires_grad_(False)
    records=[];benchmark=None;subnormal_confirmed=False;zero_confirmed=False
    with torch.no_grad():
        matrices=[(n,w.detach())for n,w in model.named_parameters()if w.ndim==2]
        matrices.append(('synthetic_noncontiguous_padded',torch.arange(210,dtype=torch.float32,device='cuda').reshape(3,70)[:,::2]/1000))
        for name,original in matrices:
            weight=original.clone() if name!='synthetic_noncontiguous_padded' else torch.empty(3,70,device='cuda')[:,::2]
            graph=CudaQ4(quantize.dequantized)
            variants=[original,original*.03125,original*1e-4,original*1e-7,torch.zeros_like(original)]
            for value in variants:
                weight.copy_(value);expected=quantize.dequantized(weight);actual=graph(weight)
                torch.cuda.synchronize();assert torch.equal(actual,expected),name
                if name=='synthetic_noncontiguous_padded':
                    scale,_,_=quantize.blocks(weight)
                    subnormal_confirmed|=bool(((scale.abs()>0)&(scale.abs()<torch.finfo(torch.float16).tiny)).any())
                    zero_confirmed|=bool((scale==0).any())
            records.append({'name':name,'shape':list(weight.shape),'updated_data_variants_bitwise_equal':len(variants)})
            if benchmark is None:
                weight.copy_(original);eager=[];replay=[]
                for _ in range(3):
                    for function,measure in [(quantize.dequantized,eager),(graph,replay)]:
                        torch.cuda.synchronize();start=time.monotonic()
                        for _ in range(10):result=function(weight)
                        torch.cuda.synchronize();measure.append((time.monotonic()-start)/10)
                benchmark={'shape':list(weight.shape),'eager_median_seconds':statistics.median(eager),
                    'graph_median_seconds':statistics.median(replay),'observed_speedup':statistics.median(eager)/statistics.median(replay),
                    'scope':'Quantizer only; concurrent GPU workload can affect timing; not overall training speed'}
    assert subnormal_confirmed and zero_confirmed
    report={'matrices':records,'all_outputs_bitwise_equal':True,'updated_inputs_tested':True,
        'zero_and_subnormal_scale_inputs_tested':True,'quantizer_benchmark':benchmark,
        'model_sha256':core.digest(Path(args.model)/'model.safetensors'),
        'quality_improvement_measured':False,'teacher_untouched':True}
    core.save(args.output,report);print(json.dumps({'matrices':len(records),'all_outputs_bitwise_equal':True,'benchmark':benchmark}),flush=True)


if __name__=='__main__':main()
