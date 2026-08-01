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

// System APP исполняется из отдельного SRAM overlay и не должен тянуть в него
// resident-состояние профилировщика или дополнительные импорты.
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
  COUNT
};

static constexpr usize POINT_COUNT = (usize) Point::COUNT;

struct Statistics {
  u64 total_cycles;
  u32 samples;
  u32 minimum_cycles;
  u32 maximum_cycles;

  constexpr Statistics(void)
    : total_cycles(0), samples(0), minimum_cycles(0), maximum_cycles(0) {}

  void reset(void) {
    total_cycles = 0;
    samples = 0;
    minimum_cycles = 0;
    maximum_cycles = 0;
  }

  void add(u32 cycles) {
    // После 2^32-1 выборок статистика замораживается, чтобы count и average
    // не стали внутренне противоречивыми после переполнения.
    if(samples == 0xFFFFFFFFUL) return;
    if(samples == 0 || cycles < minimum_cycles) minimum_cycles = cycles;
    if(samples == 0 || cycles > maximum_cycles) maximum_cycles = cycles;
    total_cycles += cycles;
    samples++;
  }

  u32 average_cycles(void) const {
    return samples == 0 ? 0 : (u32) (total_cycles / samples);
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

class Scope {
  public:
    explicit Scope(Point point)
      : point_(point), started_at_(0), active_(collection_active) {
      if(!active_) return;
      __asm__ __volatile__("" ::: "memory");
      started_at_ = DWT->CYCCNT;
      __asm__ __volatile__("" ::: "memory");
    }

    ~Scope(void) {
      if(!active_) return;
      __asm__ __volatile__("" ::: "memory");
      const u32 finished_at = DWT->CYCCNT;
      __asm__ __volatile__("" ::: "memory");
      record_sample(point_, finished_at - started_at_);
    }

    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;

  private:
    Point point_;
    u32 started_at_;
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

#endif
