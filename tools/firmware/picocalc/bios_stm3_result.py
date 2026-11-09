"""Stage result protocol v2: commands 11/12 take a ceiling, return actual bytes.

HELLO flag32 identifies v2 independently of the unchanged module ABI and wire
framing. There is one command set, no legacy exact-length implementation.
"""
from pathlib import Path
from bios_stm3_input import once


def stage_stm3_result(source):
    source = Path(source)
    hp = source / 'Core/Inc/stm3_runtime.h'
    cp = source / 'Core/Src/stm3_runtime.c'
    h, c = hp.read_text(), cp.read_text()
    h = once(h, 'STM3_TRANSPORT_START_RESULT_INPUT=8 };',
             'STM3_TRANSPORT_START_RESULT_INPUT=8,STM3_TRANSPORT_RESULT_V2=32 };')
    c = once(c, '|STM3_TRANSPORT_START_RESULT_INPUT);used=40;',
             '|STM3_TRANSPORT_START_RESULT_INPUT|STM3_TRANSPORT_RESULT_V2);used=40;')
    c = once(c, 'const uint32_t input_bytes=get32(in+4),count=get32(in+12);',
             'const uint32_t input_bytes=get32(in+4);uint32_t count=get32(in+12);')
    c = once(c, '  if(count>r->job.output_bytes){error=STM3_E_SIZE;break;}',
             '  if(count>r->job.output_bytes)count=r->job.output_bytes;')
    c = once(c, ' if(!error&&r->deferred_count>r->job.output_bytes)error=STM3_E_SIZE;',
             ' const uint32_t count=r->deferred_count<r->job.output_bytes?r->deferred_count:r->job.output_bytes;')
    c = once(c, 'memcpy(r->frame+20,r->output,r->deferred_count);used=12+r->deferred_count;',
             'memcpy(r->frame+20,r->output,count);used=12+count;')
    c = once(c, "r->frame[0]=1;r->frame[1]", "r->frame[0]=2;r->frame[1]")
    c = once(c, "r->frame[0]!=1||", "r->frame[0]!=2||")
    hp.write_text(h)
    cp.write_text(c)
    return {'result_protocol_version': 2, 'result_protocol_hello_flag': 32}
