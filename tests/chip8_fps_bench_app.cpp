// Finite diagnostic APP. Uses the production runner at its normal700IPS and
// 60Hz pacing; no COMPUTE request or clock writes. Put active.ch8 beside it.
#define MK61_BUILD_CHIP8_MODULE 1
#define MK61_CHIP8_FPS_BENCH_MS 10000
#include "system_compat.hpp"
#include "mk61_app.h"
#include "storage_path.hpp"
#include "chip8_runner.cpp"
extern "C" u32 mk61_app_initialize(const mk61_app_api* api,u32 crc,u32 kind) {
  return portable_system::bind(api,crc,kind)?0:MK61_APP_RUNTIME_ERROR;
}
extern "C" u32 mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow))return 0;
  // Phase0 is the board's10s run. A shorter bounded phase lets the same
  // binary exercise its complete lifetime in the ARM peripheral model.
  if(flow->current.phase>10000)return 0;
  chip8_runner::benchmark_duration_ms=flow->current.phase?flow->current.phase:10000;
  program_store::Entry app{},rom{};
  u32 result=MK61_APP_INVALID_FILE;
  if(program_store::entry_by_id(flow->current.file_id,app) &&
     storage_path::resolve_file(app.parent_id,"active.ch8",program_store::ProgramType::CHIP8,rom)==storage_path::Status::OK)
    result=(u32)chip8_runner::run_entry(rom);
  mk61_app_flow_exit(flow,result,MK61_FLOW_OK);return 1;
}
