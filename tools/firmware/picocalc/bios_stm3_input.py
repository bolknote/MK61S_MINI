"""Stage the fused STM3 input/start/result command on an archived BIOS tree."""
from pathlib import Path


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"STM3 fused-command source anchor changed: {old!r}")
    return text.replace(old, new, 1)


def stage_stm3_input(source):
    source = Path(source)
    header_path = source / "Core/Inc/stm3_runtime.h"
    runtime_path = source / "Core/Src/stm3_runtime.c"
    header = header_path.read_text()
    header = once(
        header,
        "enum { STM3_HELLO=1,STM3_LOAD_BEGIN,STM3_LOAD_CHUNK,STM3_LOAD_COMMIT,STM3_WRITE,STM3_START,STM3_STATUS,STM3_READ,STM3_CANCEL_JOB,STM3_UNLOAD,STM3_START_RESULT };\n"
        "enum { STM3_TRANSPORT_RX_DMA=1,STM3_TRANSPORT_TX_DMA=2,STM3_TRANSPORT_START_RESULT=4 };\n"
        "#define STM3_RESULT_LIMIT (STM3_WIRE_PAYLOAD-12u)",
        "enum { STM3_HELLO=1,STM3_LOAD_BEGIN,STM3_LOAD_CHUNK,STM3_LOAD_COMMIT,STM3_WRITE,STM3_START,STM3_STATUS,STM3_READ,STM3_CANCEL_JOB,STM3_UNLOAD,STM3_START_RESULT,STM3_START_RESULT_INPUT };\n"
        "enum { STM3_TRANSPORT_RX_DMA=1,STM3_TRANSPORT_TX_DMA=2,STM3_TRANSPORT_START_RESULT=4,STM3_TRANSPORT_START_RESULT_INPUT=8 };\n"
        "#define STM3_RESULT_LIMIT (STM3_WIRE_PAYLOAD-12u)\n"
        "#define STM3_START_RESULT_INPUT_LIMIT (STM3_WIRE_PAYLOAD-16u)",
    )
    runtime = runtime_path.read_text()
    runtime = once(
        runtime,
        "static uint32_t start_job(stm3_runtime*r,const uint8_t*in){\n"
        " if(r->state!=STM3_READY&&r->state!=STM3_FINISHED&&r->state!=STM3_CANCELLED)return STM3_E_STATE;\n"
        " if(get32(in)!=r->module_id)return STM3_E_MODULE;\n"
        " if(get32(in+4)>r->header.input_limit||!get32(in+8)||get32(in+8)>10000)return STM3_E_SIZE;\n"
        " if(r->job_id==UINT32_MAX)return STM3_E_JOB;\n",
        "static uint32_t check_job(stm3_runtime*r,const uint8_t*in){\n"
        " if(r->state!=STM3_READY&&r->state!=STM3_FINISHED&&r->state!=STM3_CANCELLED)return STM3_E_STATE;\n"
        " if(get32(in)!=r->module_id)return STM3_E_MODULE;\n"
        " if(get32(in+4)>r->header.input_limit||!get32(in+8)||get32(in+8)>10000)return STM3_E_SIZE;\n"
        " if(r->job_id==UINT32_MAX)return STM3_E_JOB;\n"
        " return STM3_OK;\n"
        "}\n"
        "static uint32_t start_job(stm3_runtime*r,const uint8_t*in){\n"
        " const uint32_t error=check_job(r,in);if(error)return error;\n",
    )
    runtime = once(
        runtime,
        "put32(out+32,r->backend.baud);put32(out+36,r->backend.transport_flags|STM3_TRANSPORT_START_RESULT);used=40;break;",
        "put32(out+32,r->backend.baud);put32(out+36,r->backend.transport_flags|STM3_TRANSPORT_START_RESULT|STM3_TRANSPORT_START_RESULT_INPUT);used=40;break;",
    )
    runtime = once(
        runtime,
        " case STM3_START_RESULT:{\n"
        "  if(n!=16){error=STM3_E_ARGUMENT;break;}\n"
        "  const uint32_t count=get32(in+12);\n"
        "  if(count>STM3_RESULT_LIMIT||count>r->header.output_limit){error=STM3_E_SIZE;break;}\n"
        "  error=start_job(r,in);if(error)break;\n"
        "  if(r->state==STM3_RUNNING){r->deferred=1;r->deferred_count=count;*out_n=0;return;}\n"
        "  if(count>r->job.output_bytes){error=STM3_E_SIZE;break;}\n"
        "  put32(out+4,r->job_id);put32(out+8,r->max_slice_us);\n"
        "  memcpy(out+12,r->output,count);used=12+count;break;}",
        " case STM3_START_RESULT:\n"
        " case STM3_START_RESULT_INPUT:{\n"
        "  if(n<16){error=STM3_E_ARGUMENT;break;}\n"
        "  const uint32_t input_bytes=get32(in+4),count=get32(in+12);\n"
        "  if(count>STM3_RESULT_LIMIT||count>r->header.output_limit){error=STM3_E_SIZE;break;}\n"
        "  if(command==STM3_START_RESULT_INPUT){\n"
        "   if(input_bytes>STM3_START_RESULT_INPUT_LIMIT||n!=16u+input_bytes){error=STM3_E_SIZE;break;}\n"
        "   error=check_job(r,in);if(error)break;\n"
        "   memcpy(r->input,in+16,input_bytes);\n"
        "  }else if(n!=16){error=STM3_E_ARGUMENT;break;}\n"
        "  error=start_job(r,in);if(error)break;\n"
        "  if(r->state==STM3_RUNNING){r->deferred=1;r->deferred_count=count;*out_n=0;return;}\n"
        "  if(count>r->job.output_bytes){error=STM3_E_SIZE;break;}\n"
        "  put32(out+4,r->job_id);put32(out+8,r->max_slice_us);\n"
        "  memcpy(out+12,r->output,count);used=12+count;break;}",
    )
    header_path.write_text(header)
    runtime_path.write_text(runtime)
    return {"start_result_input": True, "maximum_inline_input_bytes": 240}
