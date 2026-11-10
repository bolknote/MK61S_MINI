#!/usr/bin/env python3
"""Check actual probe boundary observers against the actual strict predicate."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def implementation():
    text = (ROOT/'tests/spectrum_m3_game_probe.c').read_text()
    begin = text.index('static void capture_frame(spectrum* s,uint32_t now) {')
    end = text.index('#if defined(S3_FRAME_TRACE)', begin)
    capture = text[begin:end]
    trace_begin = end
    trace_end = text.index('static void frame_report(void)', trace_begin)
    trace = text[trace_begin:trace_end]
    simple_begin = text.index('#else\nstatic void observed_paced(', trace_end)
    simple_end = text.index('#endif', simple_begin)
    trace += text[simple_begin:simple_end]+'\n#endif\n'
    begin = text.index('static uint32_t observed_run(spectrum* s,uint32_t cycles) {')
    run = text[begin:text.index('static void observed_end(spectrum* s)', begin)]
    return capture+trace+run


def harness():
    return r'''
#include <cstdint>
#ifdef OBSERVER_HOST_MAIN
#include <cassert>
#include <cstdio>
#endif
#define S3_PRODUCER_PROFILE 0
#define S3_FRAME_TRACE_LIMIT 8u
struct spectrum {uint32_t frames=0,frame_tstates=0;struct{uint32_t cyc=0;}cpu;};
static spectrum machine;
static uint32_t seen,first_us,last_us,first_cycles,last_cycles,first_frame,last_frame;
static uint32_t previous_us,min_frame_us=UINT32_MAX,max_frame_us,late_frames,max_lag_us;
static bool first_set,last_set;
static uint32_t raw_seen,first_run_us,last_run_us;
static bool first_run_set,boundary_mismatch;
static volatile uint32_t clock_word;
static uint32_t run_calls;
static uint32_t clock_us(){return clock_word;}
static uint32_t spectrum_frame_cycles(const spectrum*){return 71680;}
static uint32_t spectrum_run(spectrum*,uint32_t){++run_calls;return 0;}
''' + implementation() + r'''
extern "C" void harness_init(){}
extern "C" void reset_observer(uint32_t start_frame,uint32_t cycle_base){
    machine={};machine.frames=start_frame;machine.cpu.cyc=cycle_base;raw_seen=seen=start_frame;
    first_set=last_set=first_run_set=boundary_mismatch=false;
    first_us=last_us=first_cycles=last_cycles=first_run_us=last_run_us=first_frame=last_frame=0;
    previous_us=0;min_frame_us=UINT32_MAX;max_frame_us=late_frames=max_lag_us=run_calls=0;
#if S3_FRAME_TRACE
    frame_trace_count=paced_count=paced_previous=paced_max=paced_late=paced_max_late=paced_resyncs=0;
    paced_min=UINT32_MAX;first_slice_pending=false;
#endif
}
extern "C" void observe_boundary(uint32_t frame,uint32_t cycles,uint32_t actual_now,uint32_t observer_cost){
    machine.frames=frame;machine.cpu.cyc=cycles;machine.frame_tstates=frame==1?160:1797;
    observed_paced(&machine,actual_now-13,actual_now,actual_now-100,false);
    clock_word=actual_now+observer_cost;
    (void)observed_run(&machine,0);
}
extern "C" uint32_t observer_word(unsigned index){
    switch(index){
        case 0:return last_us-first_us;case 1:return last_cycles-first_cycles;
        case 2:return last_run_us-first_run_us;case 3:return first_us;case 4:return last_us;
        case 5:return first_run_us;case 6:return last_run_us;case 7:return first_frame;case 8:return last_frame;
        case 9:return first_set|(last_set<<1)|(first_run_set<<2)|(boundary_mismatch<<3);
        case 10:return run_calls;default:return 0xbad;
    }
}
'''


VECTORS = [(42937957,12267988,True),(42937957,12267989,False),
           (42937957,12268088,False),(3500,1001,True),(3499,1001,False),
           (3501,1001,True),(3500,1002,False),(3500,1000,True)]


def predicate():
    tree = ast.parse((ROOT/'tools/apps/spectrum/qualify_spectrum_m3_run.py').read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys,node.values):
            if isinstance(key,ast.Constant) and key.value=='z80_at_least_3_5MHz':
                return compile(ast.Expression(value),'actual strict Z80 predicate','eval')
    raise AssertionError('Missing strict predicate')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifact-dir',type=Path)
    args=parser.parse_args()
    temp=tempfile.TemporaryDirectory(prefix='spectrum-observer-')
    folder=args.artifact_dir or Path(temp.name)
    folder.mkdir(parents=True,exist_ok=True)
    cpp=harness()
    (folder/'observer-probe.cpp').write_text(cpp)
    main=r'''
int main(){
    struct Vector{uint32_t cycles,us;};
    const Vector vectors[]={VECTORS};
    for(uint32_t base:{0u,0xfffffff0u})for(uint32_t clock:{0u,0xfffffff0u})for(auto v:vectors){
        reset_observer(0,base);observe_boundary(1,base,clock,7);
        observe_boundary(600,base+v.cycles,clock+v.us,8);
        assert(observer_word(0)==v.us && observer_word(1)==v.cycles && observer_word(2)==v.us+1);
        assert(observer_word(3)==clock && observer_word(4)==uint32_t(clock+v.us));
        assert(observer_word(5)==uint32_t(clock+7) && observer_word(6)==uint32_t(clock+v.us+8));
        assert(observer_word(7)==1 && observer_word(8)==600 && observer_word(9)==7 && observer_word(10)==2);
        std::printf("%u %u %u\n",observer_word(1),observer_word(0),observer_word(2));
    }
}
'''.replace('VECTORS',','.join('{'+str(c)+','+str(t)+'}'for c,t,_ in VECTORS))
    # The test does not duplicate the acceptance comparison: evaluate the
    # exact AST expression from the production qualification tool.
    strict=predicate();count=0;legacy_false_fail=0
    for trace in (0,1):
        source=folder/('observer-test-'+str(trace)+'.cpp')
        source.write_text('#include <initializer_list>\n'+cpp+main)
        binary=source.with_suffix('')
        subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        '-DOBSERVER_HOST_MAIN=1','-DS3_FRAME_TRACE='+str(trace),str(source),'-o',str(binary)],check=True)
        output=subprocess.run([str(binary)],capture_output=True,text=True,check=True).stdout
        for i,line in enumerate(output.splitlines()):
            cycles,elapsed,legacy=map(int,line.split());expected=VECTORS[i%len(VECTORS)][2]
            result=eval(strict,{'max':max},{'timing_valid':True,'cycles':cycles,'elapsed':elapsed})
            assert result==expected,(cycles,elapsed,expected)
            old=eval(strict,{'max':max},{'timing_valid':True,'cycles':cycles,'elapsed':legacy})
            if result and not old:legacy_false_fail+=1
            count+=1
    assert legacy_false_fail>0
    result={'status':'PASS','physical_io':False,'host_cases':count,'legacy_observer_false_fail_vectors':legacy_false_fail,
            'scope':'Actual capture/paired-observer bodies, trace on/off, equality and adjacent cycle/us, real slow timing rejected,32bit time/cycle wrap; exact qualifier predicate unchanged',
            'probe_source_sha256':hashlib.sha256((ROOT/'tests/spectrum_m3_game_probe.c').read_bytes()).hexdigest()}
    (folder/'observer-host-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    temp.cleanup()


if __name__=='__main__':main()
