#ifndef MK61_DWT_PROFILER_HPP
#define MK61_DWT_PROFILER_HPP

#include "rust_types.h"

// Профилировщик собирается по умолчанию для поддерживаемой STM32-платформы,
// но до явной команды `prof start` выполняет только одну дешёвую проверку в
// каждой отмеченной точке. Размер-чувствительная сборка может полностью убрать
// его через -DMK61_ENABLE_DWT_PROFILER=0.
#ifndef MK61_ENABLE_DWT_PROFILER
  #define MK61_ENABLE_DWT_PROFILER 1
#endif
#if MK61_ENABLE_DWT_PROFILER != 0 && MK61_ENABLE_DWT_PROFILER != 1
  #error "MK61_ENABLE_DWT_PROFILER must be 0 or 1"
#endif

// Детальный замер каждого вызова IK1302/03/06_Tick нужен только для
// исследовательской сборки: он добавляет шесть чтений CYCCNT на микротакт.
#ifndef MK61_DWT_CORE_DETAIL
  #define MK61_DWT_CORE_DETAIL 0
#endif
#if MK61_DWT_CORE_DETAIL != 0 && MK61_DWT_CORE_DETAIL != 1
  #error "MK61_DWT_CORE_DETAIL must be 0 or 1"
#endif

// Optional runtime attribution for VM investigations. Default builds retain
// the original point table, statistics layout and scope implementation.
#ifndef MK61_DWT_RUNTIME_DETAIL
  #define MK61_DWT_RUNTIME_DETAIL 0
#endif
#if MK61_DWT_RUNTIME_DETAIL != 0 && MK61_DWT_RUNTIME_DETAIL != 1
  #error "MK61_DWT_RUNTIME_DETAIL must be 0 or 1"
#endif

// APP исполняется из динамически выделенного блока SRAM и не должен тянуть в
// образ resident-состояние профилировщика или дополнительные импорты.
#if defined(MK61_BUILD_FOCAL_MODULE) || \
    defined(MK61_BUILD_TINYBASIC_MODULE) || \
    defined(MK61_BUILD_WBMP_MODULE) || \
    defined(MK61_BUILD_MARKDOWN_MODULE) || \
    defined(MK61_BUILD_CHIP8_MODULE)
  #define MK61_DWT_PROFILER_MODULE_BUILD 1
#else
  #define MK61_DWT_PROFILER_MODULE_BUILD 0
#endif

#if MK61_ENABLE_DWT_PROFILER && defined(ARDUINO_ARCH_STM32) && \
    !MK61_DWT_PROFILER_MODULE_BUILD
  // CMSIS достаточно для DWT/CoreDebug и, в отличие от Arduino.h, не вводит
  // макрос bit(), конфликтующий с методом ZX0 BitInput::bit().
  #include <stm32f4xx.h>
  #define MK61_DWT_PROFILER_SUPPORTED 1
#else
  #define MK61_DWT_PROFILER_SUPPORTED 0
#endif

#define MK61_DWT_CORE_DETAIL_SUPPORTED \
  (MK61_DWT_CORE_DETAIL && MK61_DWT_PROFILER_SUPPORTED)
#define MK61_DWT_RUNTIME_DETAIL_SUPPORTED \
  (MK61_DWT_RUNTIME_DETAIL && MK61_DWT_PROFILER_SUPPORTED)

namespace dwt_profiler {

enum class Point : u8 {
  CORE_STEP = 0,
  CORE_FETCH,
  CORE_TICKS_00_26,
  CORE_TICKS_27_35,
  CORE_TICKS_36_41,
  CORE_STEP_FINISH,
  CORE_IK1302,
  CORE_IK1303,
  CORE_IK1306,
  IDLE_MAIN,
  DISPLAY_UPDATE,
  USB_SCREEN_SERVICE,
  FLASH_READ,
  FLASH_WRITE,
  FLASH_VERIFY,
  FLASH_ERASE,
  ZX0_DECODE,
#if MK61_DWT_RUNTIME_DETAIL
  APP_LOAD_BASIC, APP_LOAD_FOCAL, APP_LOAD_VM, APP_LOAD_INPUT, APP_LOAD_OTHER,
  APP_ENTRY_BASIC, APP_ENTRY_FOCAL, APP_ENTRY_VM, APP_ENTRY_INPUT, APP_ENTRY_OTHER,
  FILE_SOURCE, FILE_FONT, FILE_OTHER,
  ZX0_APP_BASIC, ZX0_APP_FOCAL, ZX0_APP_VM, ZX0_APP_INPUT, ZX0_APP_OTHER,
  ZX0_SOURCE, ZX0_FONT, ZX0_SWAP, ZX0_OTHER,
  FONT_ACTIVATE, VM_CACHE_LOOKUP, VM_PREPARE,
#endif
  COUNT
};

static constexpr usize POINT_COUNT = (usize) Point::COUNT;

struct Statistics {
  u64 total_cycles;
  u32 samples;
  u32 minimum_cycles;
  u32 maximum_cycles;
#if MK61_DWT_RUNTIME_DETAIL
  u64 self_cycles = 0;
#endif

  constexpr Statistics(void)
    : total_cycles(0), samples(0), minimum_cycles(0), maximum_cycles(0) {}

  void reset(void) {
    total_cycles = 0;
    samples = 0;
    minimum_cycles = 0;
    maximum_cycles = 0;
#if MK61_DWT_RUNTIME_DETAIL
    self_cycles = 0;
#endif
  }

#if MK61_DWT_RUNTIME_DETAIL
  void add(u64 cycles, u64 own_cycles) {
    if(samples == 0xFFFFFFFFUL) return;
    const u32 bounded = cycles > 0xFFFFFFFFUL ? 0xFFFFFFFFUL : (u32)cycles;
    if(samples == 0 || bounded < minimum_cycles) minimum_cycles = bounded;
    if(samples == 0 || bounded > maximum_cycles) maximum_cycles = bounded;
    total_cycles += cycles;
    self_cycles += own_cycles;
    samples++;
  }
  void add(u32 cycles) { add(cycles, cycles); }
#else
  void add(u32 cycles) {
    // После 2^32-1 выборок статистика замораживается, чтобы count и average
    // не стали внутренне противоречивыми после переполнения.
    if(samples == 0xFFFFFFFFUL) return;
    if(samples == 0 || cycles < minimum_cycles) minimum_cycles = cycles;
    if(samples == 0 || cycles > maximum_cycles) maximum_cycles = cycles;
    total_cycles += cycles;
    samples++;
  }
#endif

  u32 average_cycles(void) const {
#if MK61_DWT_RUNTIME_DETAIL
    const u64 average = samples == 0 ? 0 : total_cycles / samples;
    return average > 0xFFFFFFFFUL ? 0xFFFFFFFFUL : (u32)average;
#else
    return samples == 0 ? 0 : (u32) (total_cycles / samples);
#endif
  }
};

#if MK61_DWT_PROFILER_SUPPORTED

extern bool collection_active;

void initialize(void);
bool available(void);
bool running(void);
bool start(void);
void stop(void);
void reset(void);
u32 clock_hz(void);
u32 overhead_cycles(void);
const char* point_name(Point point);
const Statistics& statistics(Point point);
void record_sample(Point point, u32 elapsed_cycles);

#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
class Scope;
extern Scope* scope_top;
extern u32 scope_generation;
u64 read_cycles(void);
void record_scope(Point, u64 elapsed, u64 children);
Point app_point(u8 kind, bool entry);
Point app_decode_point(u8 kind);
extern Point decode_point;

struct VmCacheRow {
  u16 id = 0xFFFF, size = 0;
  u32 hits = 0, misses = 0;
};
static constexpr usize VM_CACHE_ROWS = 32;
void record_vm_cache(u16 id, bool hit, u16 size);
void record_vm_image(u16 id, u16 size);
const VmCacheRow& vm_cache_row(usize index);
u32 vm_cache_dropped(void);

class DecodeContext {
 public:
  explicit DecodeContext(Point point) : previous_(decode_point), generation_(scope_generation) {
    decode_point = point;
  }
  ~DecodeContext() { if(generation_ == scope_generation) decode_point = previous_; }
  DecodeContext(const DecodeContext&) = delete;
  DecodeContext& operator=(const DecodeContext&) = delete;
 private:
  Point previous_;
  u32 generation_;
};
#endif

class Scope {
  public:
    explicit Scope(Point point)
      : point_(point), started_at_(0), active_(collection_active) {
      if(!active_) return;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
      generation_ = scope_generation;
      parent_ = scope_top;
      scope_top = this;
      started_at_ = read_cycles();
#else
      __asm__ __volatile__("" ::: "memory");
      started_at_ = DWT->CYCCNT;
      __asm__ __volatile__("" ::: "memory");
#endif
    }

    ~Scope(void) {
      if(!active_) return;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
      if(generation_ != scope_generation) return;
      const u64 elapsed = read_cycles() - started_at_;
      scope_top = parent_;
      if(parent_) parent_->children_ += elapsed;
      record_scope(point_, elapsed, children_);
#else
      __asm__ __volatile__("" ::: "memory");
      const u32 finished_at = DWT->CYCCNT;
      __asm__ __volatile__("" ::: "memory");
      record_sample(point_, finished_at - started_at_);
#endif
    }

    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;

  private:
    Point point_;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
    u64 started_at_, children_ = 0;
    Scope* parent_ = nullptr;
    u32 generation_ = 0;
#else
    u32 started_at_;
#endif
    bool active_;
};

// Несколько коротких участков горячего цикла суммируются локально, а глобальная
// статистика обновляется лишь один раз при уничтожении Accumulator. Это сохраняет
// детализацию, не добавляя min/max/total bookkeeping в каждый микротакт.
class Accumulator {
  public:
    explicit Accumulator(Point point)
      : point_(point), total_cycles_(0), segments_(0),
        active_(collection_active) {}

    ~Accumulator(void) {
      if(active_ && segments_ != 0) record_sample(point_, total_cycles_);
    }

    Accumulator(const Accumulator&) = delete;
    Accumulator& operator=(const Accumulator&) = delete;

    bool active(void) const { return active_; }

  private:
    friend class AccumulatingScope;

    void add(u32 cycles) {
      total_cycles_ += cycles;
      segments_++;
    }

    Point point_;
    u32 total_cycles_;
    u16 segments_;
    bool active_;
};

class AccumulatingScope {
  public:
    explicit AccumulatingScope(Accumulator& accumulator)
      : accumulator_(accumulator), started_at_(0),
        active_(accumulator.active_) {
      if(!active_) return;
      __asm__ __volatile__("" ::: "memory");
      started_at_ = DWT->CYCCNT;
      __asm__ __volatile__("" ::: "memory");
    }

    ~AccumulatingScope(void) {
      if(!active_) return;
      __asm__ __volatile__("" ::: "memory");
      const u32 finished_at = DWT->CYCCNT;
      __asm__ __volatile__("" ::: "memory");
      accumulator_.add(finished_at - started_at_);
    }

    AccumulatingScope(const AccumulatingScope&) = delete;
    AccumulatingScope& operator=(const AccumulatingScope&) = delete;

  private:
    Accumulator& accumulator_;
    u32 started_at_;
    bool active_;
};

#else

inline void initialize(void) {}
inline bool available(void) { return false; }
inline bool running(void) { return false; }
inline bool start(void) { return false; }
inline void stop(void) {}
inline void reset(void) {}
inline u32 clock_hz(void) { return 0; }
inline u32 overhead_cycles(void) { return 0; }
inline const char* point_name(Point) { return "unsupported"; }
inline const Statistics& statistics(Point) {
  static const Statistics empty;
  return empty;
}

class Scope {
  public:
    explicit constexpr Scope(Point) {}
};

class Accumulator {
  public:
    explicit constexpr Accumulator(Point) {}
};

class AccumulatingScope {
  public:
    explicit constexpr AccumulatingScope(Accumulator&) {}
};

#endif

} // namespace dwt_profiler

#define MK61_DWT_JOIN_INNER(left, right) left##right
#define MK61_DWT_JOIN(left, right) MK61_DWT_JOIN_INNER(left, right)

#if MK61_DWT_PROFILER_SUPPORTED
  #define MK61_PROFILE_SCOPE(point) \
    dwt_profiler::Scope MK61_DWT_JOIN(mk61_dwt_scope_, __LINE__)(point)
  #define MK61_PROFILE_ACCUMULATE_SCOPE(accumulator) \
    dwt_profiler::AccumulatingScope \
      MK61_DWT_JOIN(mk61_dwt_accumulating_scope_, __LINE__)(accumulator)
#else
  #define MK61_PROFILE_SCOPE(point) ((void) 0)
  #define MK61_PROFILE_ACCUMULATE_SCOPE(accumulator) ((void) 0)
#endif

#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
  #define MK61_RUNTIME_PROFILE_SCOPE(point) MK61_PROFILE_SCOPE(point)
#else
  #define MK61_RUNTIME_PROFILE_SCOPE(point) ((void) 0)
#endif

#endif
