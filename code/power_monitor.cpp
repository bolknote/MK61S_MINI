#include "power_monitor.hpp"

#include "power_monitor_policy.hpp"

#if MK61_POWER_MONITOR_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>
#endif

namespace power_monitor {
namespace {

#if MK61_POWER_MONITOR_SUPPORTED

static constexpr u32 BREADCRUMB_MAGIC = 0x50564421UL; // "PVD!"
static constexpr u32 META_INITIALIZED = 1UL << 0;
static constexpr u32 META_PREVIOUS_UNSTABLE = 1UL << 1;
static constexpr u32 META_EDGE_SEEN = 1UL << 2;
static constexpr u32 META_LAST_EDGE_LOW = 1UL << 3;

struct Breadcrumb {
  u32 inverse_magic;
  u32 edge_ms;
  u32 inverse_edge_ms;
  u32 magic;
};

static_assert(sizeof(Breadcrumb) == 16,
              "PVD breadcrumb must remain compact");

extern "C" {
__attribute__((used, aligned(4), section(".noinit.mk61_power_monitor")))
volatile Breadcrumb mk61_power_monitor_breadcrumb;
}

static volatile u32 g_policy_flags;
static volatile u32 g_recovery_started_ms;
static volatile u32 g_meta_flags;
static volatile u32 g_low_events;
static volatile u32 g_recovery_events;
static volatile u32 g_rejected_programs;
static volatile u32 g_rejected_erases;
static volatile u32 g_rejected_msc_writes;
static volatile u32 g_last_edge_ms;
static volatile u32 g_last_edge_cycles;
static u32 g_previous_edge_ms;

static void increment_saturated(volatile u32& counter) {
  u32 current = __atomic_load_n(&counter, __ATOMIC_RELAXED);
  while(current != 0xFFFFFFFFUL &&
        !__atomic_compare_exchange_n(
            &counter, &current, current + 1U, true,
            __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}

static power_monitor_policy::State load_policy(void) {
  const u32 flags = __atomic_load_n(&g_policy_flags, __ATOMIC_ACQUIRE);
  const u32 recovery = __atomic_load_n(
      &g_recovery_started_ms, __ATOMIC_RELAXED);
  return {flags, recovery};
}

static void store_policy(const power_monitor_policy::State& state) {
  __atomic_store_n(&g_recovery_started_ms, state.recovery_started_ms,
                   __ATOMIC_RELAXED);
  __atomic_store_n(&g_policy_flags, state.flags, __ATOMIC_RELEASE);
}

static bool breadcrumb_valid(void) {
  const u32 magic = mk61_power_monitor_breadcrumb.magic;
  const u32 inverse_magic = mk61_power_monitor_breadcrumb.inverse_magic;
  const u32 edge_ms = mk61_power_monitor_breadcrumb.edge_ms;
  const u32 inverse_edge_ms =
      mk61_power_monitor_breadcrumb.inverse_edge_ms;
  return magic == BREADCRUMB_MAGIC &&
         inverse_magic == ~BREADCRUMB_MAGIC &&
         inverse_edge_ms == ~edge_ms;
}

static void clear_breadcrumb(void) {
  mk61_power_monitor_breadcrumb.magic = 0;
  __DMB();
}

static void publish_breadcrumb(u32 edge_ms) {
  mk61_power_monitor_breadcrumb.magic = 0;
  __DMB();
  mk61_power_monitor_breadcrumb.inverse_magic = ~BREADCRUMB_MAGIC;
  mk61_power_monitor_breadcrumb.edge_ms = edge_ms;
  mk61_power_monitor_breadcrumb.inverse_edge_ms = ~edge_ms;
  __DMB();
  mk61_power_monitor_breadcrumb.magic = BREADCRUMB_MAGIC;
  __DSB();
}

static bool comparator_is_low(void) {
  return (PWR->CSR & PWR_CSR_PVDO) != 0;
}

static u32 configured_level(void) {
  static constexpr u32 levels[] = {
    PWR_PVDLEVEL_0, PWR_PVDLEVEL_1, PWR_PVDLEVEL_2, PWR_PVDLEVEL_3,
    PWR_PVDLEVEL_4, PWR_PVDLEVEL_5, PWR_PVDLEVEL_6, PWR_PVDLEVEL_7
  };
  return levels[MK61_PVD_LEVEL];
}

static void note_sample(bool below, u32 now_ms, u32 now_cycles) {
  power_monitor_policy::State state = load_policy();
  if(!power_monitor_policy::note_edge(state, below, now_ms)) return;
  store_policy(state);
  __atomic_fetch_or(&g_meta_flags, META_EDGE_SEEN, __ATOMIC_RELEASE);
  if(below) {
    __atomic_fetch_or(&g_meta_flags, META_LAST_EDGE_LOW, __ATOMIC_RELEASE);
  } else {
    __atomic_fetch_and(&g_meta_flags, ~META_LAST_EDGE_LOW, __ATOMIC_RELEASE);
  }
  g_last_edge_ms = now_ms;
  g_last_edge_cycles = now_cycles;
  if(below) {
    increment_saturated(g_low_events);
    publish_breadcrumb(now_ms);
  } else {
    increment_saturated(g_recovery_events);
  }
}

#endif

} // namespace

void initialize(void) {
#if MK61_POWER_MONITOR_SUPPORTED
  const bool previous_unstable = breadcrumb_valid();
  g_previous_edge_ms = previous_unstable
      ? mk61_power_monitor_breadcrumb.edge_ms : 0;
  clear_breadcrumb();

  g_policy_flags = 0;
  g_recovery_started_ms = 0;
  g_meta_flags = previous_unstable ? META_PREVIOUS_UNSTABLE : 0;
  g_low_events = 0;
  g_recovery_events = 0;
  g_rejected_programs = 0;
  g_rejected_erases = 0;
  g_rejected_msc_writes = 0;
  g_last_edge_ms = 0;
  g_last_edge_cycles = 0;

  __HAL_RCC_PWR_CLK_ENABLE();
  HAL_NVIC_DisableIRQ(PVD_IRQn);
  HAL_PWR_DisablePVD();
  PWR_PVDTypeDef config = {};
  config.PVDLevel = configured_level();
  config.Mode = PWR_PVD_MODE_IT_RISING_FALLING;
  HAL_PWR_ConfigPVD(&config);
  __HAL_PWR_PVD_EXTI_CLEAR_FLAG();
  HAL_PWR_EnablePVD();
  __DSB();

  const u32 now_ms = HAL_GetTick();
  const bool below = comparator_is_low();
  store_policy(power_monitor_policy::initial_state(below, now_ms));
  if(below) {
    increment_saturated(g_low_events);
    g_last_edge_ms = now_ms;
    g_last_edge_cycles = DWT->CYCCNT;
    g_meta_flags |= META_EDGE_SEEN;
    g_meta_flags |= META_LAST_EDGE_LOW;
    publish_breadcrumb(now_ms);
  }
  g_meta_flags |= META_INITIALIZED;

  // Power-fail gating must preempt the SPI DMA completion IRQ (priority 2),
  // but its handler does not abort the operation already in flight.
  HAL_NVIC_SetPriority(PVD_IRQn, 1, 0);
  // Do not clear EXTI again after the initial comparator sample. If the rail
  // crossed during setup, the pending IRQ must replay that level; note_edge()
  // makes a configuration-generated duplicate harmless.
  HAL_NVIC_EnableIRQ(PVD_IRQn);
#endif
}

void poll(u32 now_ms) {
#if MK61_POWER_MONITOR_SUPPORTED
  const u32 primask = __get_PRIMASK();
  __disable_irq();
  // Sampling in foreground closes the small interval in which an edge can be
  // pending while its IRQ is masked by another critical section. Replaying
  // the IRQ later is harmless because note_edge() rejects duplicate levels.
  note_sample(comparator_is_low(), now_ms, DWT->CYCCNT);
  power_monitor_policy::State state = load_policy();
  const bool stable = !comparator_is_low() &&
      power_monitor_policy::poll_stable(
          state, now_ms, MK61_PVD_RECOVERY_STABLE_MS);
  if(stable) {
    store_policy(state);
    clear_breadcrumb();
  }
  __set_PRIMASK(primask);
#else
  (void) now_ms;
#endif
}

bool writes_allowed(void) {
#if MK61_POWER_MONITOR_SUPPORTED
  const u32 meta = __atomic_load_n(&g_meta_flags, __ATOMIC_ACQUIRE);
  return (meta & META_INITIALIZED) != 0 &&
         power_monitor_policy::writes_allowed(load_policy());
#else
  return true;
#endif
}

bool allow(Operation operation) {
  if(writes_allowed()) return true;
#if MK61_POWER_MONITOR_SUPPORTED
  switch(operation) {
    case Operation::NOR_PROGRAM:
      increment_saturated(g_rejected_programs);
      break;
    case Operation::NOR_ERASE:
      increment_saturated(g_rejected_erases);
      break;
    case Operation::MSC_WRITE:
      increment_saturated(g_rejected_msc_writes);
      break;
  }
#else
  (void) operation;
#endif
  return false;
}

Snapshot snapshot(void) {
  Snapshot out = {};
  out.supported = MK61_POWER_MONITOR_SUPPORTED != 0;
  out.level = MK61_PVD_LEVEL;
#if MK61_POWER_MONITOR_SUPPORTED
  const u32 meta = __atomic_load_n(&g_meta_flags, __ATOMIC_ACQUIRE);
  const power_monitor_policy::State state = load_policy();
  out.initialized = (meta & META_INITIALIZED) != 0;
  out.below_threshold = power_monitor_policy::below_threshold(state);
  out.recovering = power_monitor_policy::recovering(state);
  out.writes_allowed = out.initialized &&
      power_monitor_policy::writes_allowed(state);
  out.previous_unstable = (meta & META_PREVIOUS_UNSTABLE) != 0;
  out.edge_seen = (meta & META_EDGE_SEEN) != 0;
  out.last_edge_low = (meta & META_LAST_EDGE_LOW) != 0;
  out.stable_remaining_ms = power_monitor_policy::stable_remaining_ms(
      state, HAL_GetTick(), MK61_PVD_RECOVERY_STABLE_MS);
  out.low_events = g_low_events;
  out.recovery_events = g_recovery_events;
  out.rejected_programs = g_rejected_programs;
  out.rejected_erases = g_rejected_erases;
  out.rejected_msc_writes = g_rejected_msc_writes;
  out.last_edge_ms = g_last_edge_ms;
  out.last_edge_cycles = g_last_edge_cycles;
  out.previous_edge_ms = g_previous_edge_ms;
#else
  out.initialized = false;
  out.writes_allowed = true;
#endif
  return out;
}

ThresholdRange threshold_range(void) {
  // Conservative common ranges from the STM32F401xB/C, STM32F401xD/E and
  // STM32F411xC/E datasheets. Compile only the selected row: keeping an
  // eight-row runtime table wastes scarce F401 Flash for a build-time choice.
#if MK61_PVD_LEVEL == 0
  return {1980, 2040, 2080, 2090, 2140, 2190};
#elif MK61_PVD_LEVEL == 1
  return {2130, 2190, 2250, 2230, 2300, 2370};
#elif MK61_PVD_LEVEL == 2
  return {2290, 2350, 2390, 2390, 2450, 2510};
#elif MK61_PVD_LEVEL == 3
  return {2440, 2510, 2560, 2540, 2600, 2650};
#elif MK61_PVD_LEVEL == 4
  return {2590, 2660, 2710, 2700, 2760, 2820};
#elif MK61_PVD_LEVEL == 5
  return {2650, 2830, 2920, 2860, 2930, 2990};
#elif MK61_PVD_LEVEL == 6
  return {2850, 2930, 2990, 2960, 3030, 3100};
#else
  return {2950, 3030, 3090, 3070, 3140, 3210};
#endif
}

const char* backend_name(void) {
#if MK61_POWER_MONITOR_SUPPORTED
  return "STM32-PVD/EXTI16";
#else
  return "disabled";
#endif
}

void interrupt_handler(void) {
#if MK61_POWER_MONITOR_SUPPORTED
  if(__HAL_PWR_PVD_EXTI_GET_FLAG() == RESET) return;
  const bool below = comparator_is_low();
  note_sample(below, HAL_GetTick(), DWT->CYCCNT);
  __HAL_PWR_PVD_EXTI_CLEAR_FLAG();
#endif
}

} // namespace power_monitor

#if MK61_POWER_MONITOR_SUPPORTED
extern "C" void PVD_IRQHandler(void) {
  power_monitor::interrupt_handler();
}
#endif
