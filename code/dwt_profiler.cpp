#include "dwt_profiler.hpp"
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
#include "loadable_module_format.hpp"
#if MK61_DWT_VM_OPCODE_PROFILE_SUPPORTED
#include "language_bytecode.hpp"
#endif
#endif

#if MK61_DWT_PROFILER_SUPPORTED

namespace dwt_profiler {
namespace {

Statistics point_statistics[POINT_COUNT];
bool dwt_available = false;
u32 core_clock_hz = 0;
u32 read_overhead_cycles = 0;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
u32 previous_cycle = 0;
u64 extended_cycles = 0;
VmCacheRow cache_rows[VM_CACHE_ROWS];
u32 cache_dropped = 0;
#if MK61_DWT_VM_OPCODE_PROFILE_SUPPORTED
u32 opcode_integers[VM_OPCODE_GROUPS] = {};
#if MK61_DWT_VM_OPCODE_DETAIL
// Only valid wire values plus one fused-block row, not a 257-slot table.
static constexpr usize OPCODE_ROWS = (usize)language_vm::Op::PRINT_PRECISION + 2;
VmOpcodeRow opcode_rows[OPCODE_ROWS];
usize opcode_index(u32 opcode) {
  return opcode == 256 ? OPCODE_ROWS - 1 : opcode;
}
#endif
#endif
VmCacheRow* cache_row(u16 id) {
  if(id == 0xFFFF) return nullptr;
  VmCacheRow* empty = nullptr;
  for(auto& row : cache_rows) {
    if(row.id == id) return &row;
    if(row.id == 0xFFFF && !empty) empty = &row;
  }
  if(empty) { empty->id = id; return empty; }
  if(cache_dropped != 0xFFFFFFFFUL) ++cache_dropped;
  return nullptr;
}
#endif

static usize point_index(Point point) {
  const usize index = (usize) point;
  return index < POINT_COUNT ? index : POINT_COUNT;
}

static u32 measure_read_overhead(void) {
  u32 best = 0xFFFFFFFFUL;
  for(u8 sample = 0; sample < 32; sample++) {
    __asm__ __volatile__("" ::: "memory");
    const u32 started_at = DWT->CYCCNT;
    __asm__ __volatile__("" ::: "memory");
    const u32 finished_at = DWT->CYCCNT;
    __asm__ __volatile__("" ::: "memory");
    const u32 elapsed = finished_at - started_at;
    if(elapsed < best) best = elapsed;
  }
  return best == 0xFFFFFFFFUL ? 0 : best;
}

} // namespace

bool collection_active = false;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
Scope* scope_top = nullptr;
u32 scope_generation = 0;
Point decode_point = Point::ZX0_OTHER;
u64 read_cycles(void) {
  // Foreground-only scopes sample more often than one CYCCNT wrap (44.7 s
  // at 96 MHz). Long VM/INPUT entries remain correct through nested services;
  // an unobserved gap of multiple wraps cannot be reconstructed from DWT alone.
  __asm__ __volatile__("" ::: "memory");
  const u32 now = DWT->CYCCNT;
  __asm__ __volatile__("" ::: "memory");
  extended_cycles += (u32)(now - previous_cycle);
  previous_cycle = now;
  return extended_cycles;
}
void record_scope(Point point, u64 elapsed, u64 children) {
  if(!collection_active) return;
  const usize index = point_index(point);
  if(index < POINT_COUNT) point_statistics[index].add(elapsed, children <= elapsed ? elapsed - children : 0);
}
#if MK61_DWT_VM_OPCODE_PROFILE_SUPPORTED
u32 vm_opcode_group(u32 opcode) {
  using language_vm::Op;
  if(opcode==256)return 8;
  if(opcode>(u32)Op::PRINT_PRECISION)return VM_OPCODE_GROUPS;
  const auto op=(Op)opcode;
  if((op>=Op::LOAD && op<=Op::STORE) || op==Op::UPDATE_LOCAL)return 1;
  if(op==Op::LOAD_ARRAY || op==Op::STORE_ARRAY || op==Op::LOAD_ARRAY_FIXED ||
     op==Op::ARRAY_CELL || op==Op::TARGET_ARRAY)return 2;
  if(op==Op::ADD || op==Op::SUB)return 3;
  if(op==Op::MUL)return 4;
  if(op==Op::DIV || op==Op::MOD || op==Op::FLOOR_DIV)return 5;
  if((op>=Op::EQ && op<=Op::XOR) || op==Op::COMPARE_FALSE)return 6;
  if((op>=Op::CONST_0 && op<=Op::CONST_15) || op==Op::CONST_I8 ||
     op==Op::CONST_I16 || op==Op::CONST_I32 || op==Op::CONST_F64 ||
     op==Op::CONST_DEC8 || op==Op::CONST_DEC16)return 0;
  return 7;
}
void record_vm_opcodes(u32 group, u32 count, u32 integers, u64 cycles) {
  if(!collection_active || group>=VM_OPCODE_GROUPS || !count || integers>count) return;
  auto& row=point_statistics[(usize)Point::VM_CONSTANTS+group];
  if(count>UINT32_MAX-row.samples) return;
  row.samples+=count;row.total_cycles+=cycles;row.self_cycles+=cycles;
  // Batch attribution retains count/total/average, not per-opcode extrema.
  row.minimum_cycles=row.maximum_cycles=0;
  opcode_integers[group]+=integers;
}
u32 vm_opcode_integers(usize group) {return group<VM_OPCODE_GROUPS?opcode_integers[group]:0;}
void record_vm_opcode(u32 opcode, u32 count, u32 integers, u64 cycles) {
  const u32 group=vm_opcode_group(opcode);
  if(opcode==256)integers=count;
  if(!collection_active || group>=VM_OPCODE_GROUPS || !count || integers>count)return;
  if(count>UINT32_MAX-point_statistics[(usize)Point::VM_CONSTANTS+group].samples)return;
#if MK61_DWT_VM_OPCODE_DETAIL
  auto& row=opcode_rows[opcode_index(opcode)];
  if(count>UINT32_MAX-row.count)return;
#endif
  record_vm_opcodes(group,count,integers,cycles);
#if MK61_DWT_VM_OPCODE_DETAIL
  row.count+=count;row.integers+=integers;row.cycles+=cycles;
#endif
}
#if MK61_DWT_VM_OPCODE_DETAIL
const VmOpcodeRow& vm_opcode_row(usize opcode) {
  static const VmOpcodeRow empty;
  return vm_opcode_group((u32)opcode)<VM_OPCODE_GROUPS ? opcode_rows[opcode_index((u32)opcode)] : empty;
}
#endif
#endif
Point app_point(u8 kind, bool entry) {
  using K = loadable_module::Kind;
  switch((K)kind) {
    case K::TINYBASIC: return entry ? Point::APP_ENTRY_BASIC : Point::APP_LOAD_BASIC;
    case K::FOCAL: return entry ? Point::APP_ENTRY_FOCAL : Point::APP_LOAD_FOCAL;
    case K::LANGUAGE_VM: return entry ? Point::APP_ENTRY_VM : Point::APP_LOAD_VM;
    case K::LANGUAGE_INPUT: return entry ? Point::APP_ENTRY_INPUT : Point::APP_LOAD_INPUT;
    default: return entry ? Point::APP_ENTRY_OTHER : Point::APP_LOAD_OTHER;
  }
}
Point app_decode_point(u8 kind) {
  using K = loadable_module::Kind;
  switch((K)kind) {
    case K::TINYBASIC: return Point::ZX0_APP_BASIC;
    case K::FOCAL: return Point::ZX0_APP_FOCAL;
    case K::LANGUAGE_VM: return Point::ZX0_APP_VM;
    case K::LANGUAGE_INPUT: return Point::ZX0_APP_INPUT;
    default: return Point::ZX0_APP_OTHER;
  }
}
void record_vm_cache(u16 id, bool hit, u16 size) {
  if(!collection_active) return;
  if(auto* row = cache_row(id)) {
    u32& count = hit ? row->hits : row->misses;
    if(count != 0xFFFFFFFFUL) ++count;
    if(size) row->size = size;
  }
}
void record_vm_image(u16 id, u16 size) {
  if(collection_active) if(auto* row = cache_row(id)) row->size = size;
}
const VmCacheRow& vm_cache_row(usize index) {
  static const VmCacheRow empty;
  return index < VM_CACHE_ROWS ? cache_rows[index] : empty;
}
u32 vm_cache_dropped(void) { return cache_dropped; }
#endif

void initialize(void) {
  collection_active = false;
  reset();

  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  __DSB();
  __ISB();

  const u32 before = DWT->CYCCNT;
  for(u8 index = 0; index < 8; index++) __NOP();
  const u32 after = DWT->CYCCNT;
  dwt_available = after != before;
  core_clock_hz = dwt_available ? SystemCoreClock : 0;
  read_overhead_cycles = dwt_available ? measure_read_overhead() : 0;
}

bool available(void) { return dwt_available; }
bool running(void) { return collection_active; }

bool start(void) {
  if(!dwt_available) return false;
  reset();
  collection_active = true;
  return true;
}

void stop(void) { collection_active = false; }

void reset(void) {
  for(usize index = 0; index < POINT_COUNT; index++) {
    point_statistics[index].reset();
  }
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
  ++scope_generation;
  scope_top = nullptr;
  decode_point = Point::ZX0_OTHER;
  previous_cycle = DWT->CYCCNT;
  extended_cycles = 0;
  for(auto& row : cache_rows) row = {};
  cache_dropped = 0;
#if MK61_DWT_VM_OPCODE_PROFILE_SUPPORTED
  for(auto& count : opcode_integers) count=0;
#if MK61_DWT_VM_OPCODE_DETAIL
  for(auto& row : opcode_rows)row={};
#endif
#endif
#endif
}

u32 clock_hz(void) { return core_clock_hz; }
u32 overhead_cycles(void) { return read_overhead_cycles; }

const char* point_name(Point point) {
  switch(point) {
    case Point::CORE_STEP:          return "core.step";
    case Point::CORE_FETCH:         return "core.fetch";
    case Point::CORE_TICKS_00_26:   return "core.ticks.00-26";
    case Point::CORE_TICKS_27_35:   return "core.ticks.27-35";
    case Point::CORE_TICKS_36_41:   return "core.ticks.36-41";
    case Point::CORE_STEP_FINISH:   return "core.finish";
    case Point::CORE_IK1302:        return "core.ik1302";
    case Point::CORE_IK1303:        return "core.ik1303";
    case Point::CORE_IK1306:        return "core.ik1306";
    case Point::IDLE_MAIN:          return "idle.main";
    case Point::DISPLAY_UPDATE:     return "display.update";
    case Point::USB_SCREEN_SERVICE: return "usb.service";
    case Point::FLASH_READ:         return "flash.read";
    case Point::FLASH_WRITE:        return "flash.write";
    case Point::FLASH_VERIFY:       return "flash.verify";
    case Point::FLASH_ERASE:        return "flash.erase";
    case Point::ZX0_DECODE:         return "zx0.decode";
#if MK61_DWT_RUNTIME_DETAIL
    case Point::APP_LOAD_BASIC: return "app.load.basic";
    case Point::APP_LOAD_FOCAL: return "app.load.focal";
    case Point::APP_LOAD_VM: return "app.load.vm";
    case Point::APP_LOAD_INPUT: return "app.load.input";
    case Point::APP_LOAD_OTHER: return "app.load.other";
    case Point::APP_ENTRY_BASIC: return "app.entry.basic";
    case Point::APP_ENTRY_FOCAL: return "app.entry.focal";
    case Point::APP_ENTRY_VM: return "app.entry.vm";
    case Point::APP_ENTRY_INPUT: return "app.entry.input";
    case Point::APP_ENTRY_OTHER: return "app.entry.other";
    case Point::FILE_SOURCE: return "file.source";
    case Point::FILE_FONT: return "file.font";
    case Point::FILE_OTHER: return "file.other";
    case Point::ZX0_APP_BASIC: return "zx0.app.basic";
    case Point::ZX0_APP_FOCAL: return "zx0.app.focal";
    case Point::ZX0_APP_VM: return "zx0.app.vm";
    case Point::ZX0_APP_INPUT: return "zx0.app.input";
    case Point::ZX0_APP_OTHER: return "zx0.app.other";
    case Point::ZX0_SOURCE: return "zx0.source";
    case Point::ZX0_FONT: return "zx0.font";
    case Point::ZX0_SWAP: return "zx0.swap";
    case Point::ZX0_OTHER: return "zx0.other";
    case Point::FONT_ACTIVATE: return "font.activate";
    case Point::VM_CACHE_LOOKUP: return "vm.cache.lookup";
    case Point::VM_PREPARE: return "vm.prepare";
    case Point::M61_RUNNER: return "m61.runner";
    case Point::VM_INVOKE: return "vm.invoke";
    case Point::M61_OPERAND: return "m61.operand";
    case Point::M61_OPEN: return "m61.open";
    case Point::TERMINAL_LOOKUP: return "terminal.lookup";
    case Point::M61_READ_LINE: return "m61.read.line";
    case Point::M61_COMMAND: return "m61.command";
#if MK61_VM_OPCODE_PROFILE
    case Point::VM_CONSTANTS: return "vm.op.constants";
    case Point::VM_LOCALS: return "vm.op.locals";
    case Point::VM_ARRAYS: return "vm.op.arrays";
    case Point::VM_ADD_SUB: return "vm.op.addsub";
    case Point::VM_MULTIPLY: return "vm.op.multiply";
    case Point::VM_DIV_MOD: return "vm.op.divmod";
    case Point::VM_COMPARE: return "vm.op.compare";
    case Point::VM_OTHER: return "vm.op.other";
    case Point::VM_INTEGER_BLOCK: return "vm.block.integer";
#endif
#if MK61_DWT_IDLE_DETAIL
    case Point::IDLE_POWER: return "idle.power";
    case Point::IDLE_RTC: return "idle.rtc";
    case Point::IDLE_MSC: return "idle.msc";
    case Point::IDLE_USB_POWER: return "idle.usb.power";
    case Point::IDLE_TERMINAL: return "idle.terminal";
    case Point::IDLE_SOUND: return "idle.sound";
    case Point::IDLE_LED: return "idle.led";
    case Point::IDLE_DISK: return "idle.disk";
    case Point::IDLE_FLUSH: return "idle.flush";
    case Point::IDLE_OLED: return "idle.oled";
    case Point::IDLE_SIGNAL: return "idle.signal";
    case Point::IDLE_WATCHDOG: return "idle.watchdog";
    case Point::IDLE_SLEEP_CONDITIONS: return "idle.sleep.conditions";
    case Point::IDLE_SLEEP_ATTEMPT: return "idle.sleep.attempt";
    case Point::IDLE_DEEP: return "idle.deep";
#endif
#endif
    case Point::COUNT:              break;
  }
  return "unknown";
}

const Statistics& statistics(Point point) {
  static const Statistics empty;
  const usize index = point_index(point);
  return index < POINT_COUNT ? point_statistics[index] : empty;
}

void record_sample(Point point, u32 elapsed_cycles) {
  if(!collection_active) return;
  const usize index = point_index(point);
  if(index < POINT_COUNT) point_statistics[index].add(elapsed_cycles);
}

} // namespace dwt_profiler

#endif
