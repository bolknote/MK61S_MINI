#include "early_dfu.hpp"

#include "early_dfu_protocol.hpp"

#if defined(ARDUINO_ARCH_STM32)
  #include <Arduino.h>
#endif

#if MK61_EARLY_DFU_SUPPORTED
  #include "config.h"
  #include "keyboard_layout.hpp"
  #include "rtc_backup_layout.hpp"
  #include <stm32f4xx.h>
#endif

namespace {

extern "C" {
__attribute__((used, aligned(8), section(".noinit.mk61_dfu_request")))
volatile early_dfu_protocol::Request mk61_early_dfu_request;
}

void publish_request(void) {
  // Magic записывается последним: reset между любыми двумя присваиваниями
  // оставляет невалидную пару и не может случайно зациклить загрузку.
  mk61_early_dfu_request.magic = 0;
  __DMB();
  mk61_early_dfu_request.inverse_magic = ~early_dfu_protocol::MAGIC;
  __DMB();
  mk61_early_dfu_request.magic = early_dfu_protocol::MAGIC;
  __DSB();

#if MK61_EARLY_DFU_SUPPORTED
  // SRAM is specified to survive SYSRESETREQ, and .noinit is the primary
  // channel. DR8/DR9 form an independent retained copy so a future startup or
  // linker change cannot silently break the recovery path; the diagnostic
  // records which copies the preinit code actually accepted. RTC calendar and
  // alarm metadata occupy only DR11..DR19.
  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 saved_pwr_cr = PWR->CR;
  PWR->CR = saved_pwr_cr | PWR_CR_DBP;
  (void) PWR->CR;
  __DMB();

  RTC->BKP8R = 0;
  __DMB();
  RTC->BKP9R = ~early_dfu_protocol::MAGIC;
  __DMB();
  RTC->BKP8R = early_dfu_protocol::MAGIC;
  const u8 generation = early_dfu_protocol::next_generation(RTC->BKP5R);
  RTC->BKP5R = early_dfu_protocol::diagnostic_word(
      generation, early_dfu_protocol::STAGE_PUBLISHED,
      early_dfu_protocol::SOURCE_SRAM |
          early_dfu_protocol::SOURCE_BACKUP);
  __DSB();
  (void) RTC->BKP8R;

  if((saved_pwr_cr & PWR_CR_DBP) == 0) PWR->CR &= ~PWR_CR_DBP;
  RCC->APB1ENR = saved_apb1enr;
  __DSB();
#endif
}

bool consume_sram_request(void) {
  const u32 magic = mk61_early_dfu_request.magic;
  const u32 inverse_magic = mk61_early_dfu_request.inverse_magic;
  mk61_early_dfu_request.magic = 0;
  mk61_early_dfu_request.inverse_magic = 0;
  __DMB();
  return early_dfu_protocol::valid(magic, inverse_magic);
}

#if MK61_EARLY_DFU_SUPPORTED
void write_diagnostic(early_dfu_protocol::Stage stage, u8 sources) {
  static_assert(rtc_backup_layout::EARLY_DFU_DIAGNOSTIC_REGISTER == 5,
                "early DFU diagnostic register changed");
  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 saved_pwr_cr = PWR->CR;
  PWR->CR = saved_pwr_cr | PWR_CR_DBP;
  (void) PWR->CR;
  __DMB();

  const early_dfu_protocol::Diagnostic previous =
      early_dfu_protocol::decode_diagnostic(RTC->BKP5R);
  const u8 generation = previous.valid ? previous.generation : 1;
  RTC->BKP5R = early_dfu_protocol::diagnostic_word(
      generation, stage, sources);
  __DSB();
  (void) RTC->BKP5R;

  if((saved_pwr_cr & PWR_CR_DBP) == 0) PWR->CR &= ~PWR_CR_DBP;
  RCC->APB1ENR = saved_apb1enr;
  __DSB();
}

early_dfu_protocol::Diagnostic read_diagnostic(void) {
  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 word = RTC->BKP5R;
  RCC->APB1ENR = saved_apb1enr;
  __DMB();
  return early_dfu_protocol::decode_diagnostic(word);
}

bool consume_backup_request(void) {
  static_assert(rtc_backup_layout::EARLY_DFU_MAGIC_REGISTER == 8 &&
                    rtc_backup_layout::EARLY_DFU_INVERSE_REGISTER == 9,
                "early DFU hardware registers changed");

  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 saved_pwr_cr = PWR->CR;
  PWR->CR = saved_pwr_cr | PWR_CR_DBP;
  (void) PWR->CR;
  __DMB();

  const u32 magic = RTC->BKP8R;
  const u32 inverse_magic = RTC->BKP9R;
  RTC->BKP8R = 0;
  RTC->BKP9R = 0;
  __DSB();
  (void) RTC->BKP9R;

  if((saved_pwr_cr & PWR_CR_DBP) == 0) PWR->CR &= ~PWR_CR_DBP;
  RCC->APB1ENR = saved_apb1enr;
  __DSB();
  return early_dfu_protocol::valid(magic, inverse_magic);
}

early_dfu_protocol::Attempt read_attempt(void) {
  static_assert(rtc_backup_layout::EARLY_DFU_ATTEMPT_REGISTER == 6 &&
                    rtc_backup_layout::EARLY_DFU_ATTEMPT_INVERSE_REGISTER == 7,
                "early DFU attempt registers changed");

  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 word = RTC->BKP6R;
  const u32 inverse_word = RTC->BKP7R;
  RCC->APB1ENR = saved_apb1enr;
  __DMB();
  return early_dfu_protocol::decode_attempt(word, inverse_word);
}

void publish_attempt(u8 number, u8 sources) {
  const u32 word = early_dfu_protocol::attempt_word(number, sources);
  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 saved_pwr_cr = PWR->CR;
  PWR->CR = saved_pwr_cr | PWR_CR_DBP;
  (void) PWR->CR;
  __DMB();

  // As with the external request, the authoritative word is committed last.
  // Any reset between stores leaves a pair that decode_attempt() rejects.
  RTC->BKP6R = 0;
  __DMB();
  RTC->BKP7R = ~word;
  __DMB();
  RTC->BKP6R = word;
  __DSB();
  (void) RTC->BKP6R;

  if((saved_pwr_cr & PWR_CR_DBP) == 0) PWR->CR &= ~PWR_CR_DBP;
  RCC->APB1ENR = saved_apb1enr;
  __DSB();
}

void clear_attempt(void) {
  const u32 saved_apb1enr = RCC->APB1ENR;
  RCC->APB1ENR = saved_apb1enr | RCC_APB1ENR_PWREN;
  (void) RCC->APB1ENR;
  const u32 saved_pwr_cr = PWR->CR;
  PWR->CR = saved_pwr_cr | PWR_CR_DBP;
  (void) PWR->CR;
  __DMB();

  RTC->BKP6R = 0;
  __DMB();
  RTC->BKP7R = 0;
  __DSB();
  (void) RTC->BKP7R;

  if((saved_pwr_cr & PWR_CR_DBP) == 0) PWR->CR &= ~PWR_CR_DBP;
  RCC->APB1ENR = saved_apb1enr;
  __DSB();
}
#endif

u8 consume_request_sources_internal(void) {
  const bool sram = consume_sram_request();
#if MK61_EARLY_DFU_SUPPORTED
  // Always consume both copies.  Short-circuiting here could leave a valid
  // backup request behind and create a DFU loop on the bootloader's leave.
  const bool backup = consume_backup_request();
  const u8 sources =
      (sram ? (u8) early_dfu_protocol::SOURCE_SRAM : (u8) 0) |
      (backup ? (u8) early_dfu_protocol::SOURCE_BACKUP : (u8) 0);
  if(sources != early_dfu_protocol::SOURCE_NONE) {
    write_diagnostic(early_dfu_protocol::STAGE_ACCEPTED, sources);
  }
  return sources;
#else
  return sram ? early_dfu_protocol::SOURCE_SRAM : 0U;
#endif
}

bool consume_request_internal(void) {
  return consume_request_sources_internal() != early_dfu_protocol::SOURCE_NONE;
}

#if MK61_EARLY_DFU_SUPPORTED

static constexpr u32 SYSTEM_MEMORY_BASE = 0x1FFF0000UL;
static constexpr u32 SYSTEM_MEMORY_LIMIT = 0x1FFF7800UL;
static constexpr u32 VALID_SRAM_BASE = 0x20000000UL;
static constexpr u32 RESET_HSI_HZ = 16000000UL;
static constexpr u32 HSE_OFF_SETTLE_MS = 20;
static constexpr u32 HSE_OFF_SETTLE_TICKS =
    (RESET_HSI_HZ / 1000UL) * HSE_OFF_SETTLE_MS;
static constexpr u32 RESET_CAUSE_FLAGS =
    RCC_CSR_LPWRRSTF | RCC_CSR_WWDGRSTF | RCC_CSR_IWDGRSTF |
    RCC_CSR_SFTRSTF | RCC_CSR_PORRSTF | RCC_CSR_PINRSTF |
    RCC_CSR_BORRSTF;
static_assert(HSE_OFF_SETTLE_TICKS > 0 &&
                  HSE_OFF_SETTLE_TICKS <= SysTick_LOAD_RELOAD_Msk,
              "early DFU oscillator settle interval does not fit SysTick");
#if defined(STM32F401xC)
static constexpr u32 VALID_SRAM_LIMIT = 0x20010000UL;
#elif defined(STM32F401xE)
static constexpr u32 VALID_SRAM_LIMIT = 0x20018000UL;
#else
static constexpr u32 VALID_SRAM_LIMIT = 0x20020000UL;
#endif
static constexpr u32 ROW_BIT = 1UL << 4; // PB4 on every supported profile.

#if defined(CDU)
static constexpr u32 COLUMN_BIT = 1UL << 0; // PA0.
static GPIO_TypeDef* const COLUMN_GPIO = GPIOA;
static constexpr u32 COLUMN_CLOCK = RCC_AHB1ENR_GPIOAEN;
static constexpr u8 COLUMN_INDEX = 0;
static_assert(PIN_KBD_COL0 == PA0, "CDU emergency ESC column must stay on PA0");
#else
static constexpr u32 COLUMN_BIT = 1UL << 12; // PB12.
static GPIO_TypeDef* const COLUMN_GPIO = GPIOB;
static constexpr u32 COLUMN_CLOCK = RCC_AHB1ENR_GPIOBEN;
static constexpr u8 COLUMN_INDEX = 12;
static_assert(PIN_KBD_COL0 == PB12,
              "F401/F411 emergency ESC column must stay on PB12");
#endif

static_assert(PIN_KBD_ROW0 == PB4,
              "F401/F411 emergency ESC row must stay on PB4");
// keyboard.cpp разворачивает порядок scan-строк и битов bus_in(),
// поэтому физическое пересечение ROW0/COL0 имеет scan-код 39.
static_assert(keyboard_layout::ACTIVE.esc == 39,
              "emergency ROW0/COL0 probe must remain the ESC key");

bool boot_vectors_valid(u32 stack, u32 entry) {
  const u32 code = entry & ~1UL;
  return (stack & 7U) == 0 &&
         stack >= VALID_SRAM_BASE && stack <= VALID_SRAM_LIMIT &&
         (entry & 1U) != 0 &&
         code >= SYSTEM_MEMORY_BASE && code < SYSTEM_MEMORY_LIMIT;
}

void settle_hse_before_system_memory(void) {
  // AN2606 documents an F411-specific path: after USB cable detection the ROM
  // must start HSE, and an HSE detection failure causes another system reset.
  // SystemInit() has just selected the 16 MHz HSI and requested HSE off, but a
  // rapid application -> reset -> ROM sequence otherwise gives the crystal
  // virtually no off-time. This interval removes prior oscillator state as a
  // variable; correctness still comes from the bounded retry below because
  // the ROM performs its own independent HSE qualification.
  RCC->CR &= ~RCC_CR_HSEON;
  __DSB();

  // HSERDY normally clears in a few HSI cycles. Keep the wait bounded even if
  // the clock-status circuit is faulty; the fixed off interval below remains
  // deterministic and the ROM still performs its own HSE validation.
  u32 ready_timeout = RESET_HSI_HZ / 1000UL;
  while((RCC->CR & RCC_CR_HSERDY) != 0 && ready_timeout != 0) {
    ready_timeout--;
  }

  // No HAL or Arduino timebase exists in .preinit_array. At this point AHB is
  // the reset-state 16 MHz HSI, so a one-shot SysTick gives an exact 20 ms
  // oscillator off-time. branch_to_system_memory() clears SysTick again.
  SysTick->CTRL = 0;
  SysTick->LOAD = HSE_OFF_SETTLE_TICKS - 1U;
  SysTick->VAL = 0;
  SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk | SysTick_CTRL_ENABLE_Msk;
  while((SysTick->CTRL & SysTick_CTRL_COUNTFLAG_Msk) == 0) {}
  SysTick->CTRL = 0;
  SysTick->LOAD = 0;
  SysTick->VAL = 0;
  __DSB();
}

u32 reset_cause_flags(void) {
  return RCC->CSR & RESET_CAUSE_FLAGS;
}

void clear_reset_cause_flags(void) {
  RCC->CSR |= RCC_CSR_RMVF;
  __DSB();
  (void) RCC->CSR;
}

[[noreturn]] void branch_to_system_memory(u32 stack, u32 entry) {
  __disable_irq();
  SysTick->CTRL = 0;
  SysTick->LOAD = 0;
  SysTick->VAL = 0;

  // Reset_Handler уже выполнил SystemInit(), поэтому PLL и RCC находятся в
  // исходном HSI-состоянии. Убираем лишь возможные pending IRQ рантайма и
  // переназначаем System Flash без вызова HAL или Arduino-библиотек.
  for(u8 bank = 0; bank < 8; bank++) {
    NVIC->ICER[bank] = 0xFFFFFFFFUL;
    NVIC->ICPR[bank] = 0xFFFFFFFFUL;
  }
  SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
  SCB->SHCSR = 0;

  RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;
  (void) RCC->APB2ENR;
  SYSCFG->MEMRMP =
      (SYSCFG->MEMRMP & ~SYSCFG_MEMRMP_MEM_MODE) |
      SYSCFG_MEMRMP_MEM_MODE_0;
  SCB->VTOR = SYSTEM_MEMORY_BASE;
  __set_BASEPRI(0);
  __set_FAULTMASK(0);
  __DSB();
  __ISB();

  // MSP меняется в той же asm-последовательности, что и безусловный branch:
  // компилятор не успеет обратиться к стеку приложения после msr msp.
  __asm volatile(
      "movs r2, #0\n"
      "msr control, r2\n"
      "msr msp, %[stack]\n"
      "isb\n"
      "cpsie i\n"
      "bx %[entry]\n"
      :
      : [stack] "r" (stack), [entry] "r" (entry)
      : "r2", "memory");
  __builtin_unreachable();
}

bool try_enter_system_memory(u8 sources, u8 attempt_number,
                             early_dfu_protocol::Stage stage) {
  const u32 stack = *(const u32*) SYSTEM_MEMORY_BASE;
  const u32 entry = *(const u32*) (SYSTEM_MEMORY_BASE + sizeof(u32));
  if(!boot_vectors_valid(stack, entry)) {
    clear_attempt();
    write_diagnostic(early_dfu_protocol::STAGE_VECTOR_INVALID, sources);
    return false;
  }

  publish_attempt(attempt_number, sources);
  const u8 diagnostic_sources = sources |
      (attempt_number > 1
          ? (u8) early_dfu_protocol::SOURCE_RETRY : (u8) 0);
  write_diagnostic(stage, diagnostic_sources);
  settle_hse_before_system_memory();

  // The application reset that delivered the one-shot request has already
  // set SFTRSTF. Clear all historical causes immediately before entering ROM:
  // a new SFTRSTF can then only be the F411 bootloader's documented HSE-failure
  // reset. A successful USB DFU leave jumps directly to user Flash and sets no
  // reset flag, which lets the next preinit invocation retire the marker.
  clear_reset_cause_flags();
#if defined(MK61_EARLY_DFU_QUALIFY_RETRY) && \
    MK61_EARLY_DFU_QUALIFY_RETRY
  // Qualification-only fault injection: reproduce the exact SYSRESETREQ
  // signature used by the F411 ROM when HSE qualification times out. The
  // second preinit pass must consume the retained attempt and enter real ROM
  // DFU. This code is absent from every production profile.
  if(attempt_number == 1) {
    NVIC_SystemReset();
    while(true) {}
  }
#endif
  branch_to_system_memory(stack, entry);
}

bool emergency_escape_pressed(void) {
  const u32 saved_ahb1enr = RCC->AHB1ENR;
  RCC->AHB1ENR = saved_ahb1enr |
      RCC_AHB1ENR_GPIOBEN | COLUMN_CLOCK;
  (void) RCC->AHB1ENR;

  const u32 saved_b_moder = GPIOB->MODER;
  const u32 saved_b_otyper = GPIOB->OTYPER;
  const u32 saved_b_pupdr = GPIOB->PUPDR;
  const u32 saved_b_odr = GPIOB->ODR;
#if defined(CDU)
  const u32 saved_column_moder = COLUMN_GPIO->MODER;
  const u32 saved_column_pupdr = COLUMN_GPIO->PUPDR;
#endif

  // Сначала выставляем высокий уровень в ODR, затем переводим PB4 в output —
  // так на строке клавиатуры не возникает короткого низкого импульса.
  GPIOB->BSRR = ROW_BIT;
  GPIOB->OTYPER &= ~ROW_BIT;
  GPIOB->PUPDR &= ~(3UL << (4U * 2U));
  GPIOB->MODER = (GPIOB->MODER & ~(3UL << (4U * 2U))) |
                 (1UL << (4U * 2U));

  const u32 column_shift = (u32) COLUMN_INDEX * 2U;
  COLUMN_GPIO->MODER &= ~(3UL << column_shift);
  COLUMN_GPIO->PUPDR = (COLUMN_GPIO->PUPDR & ~(3UL << column_shift)) |
                       (2UL << column_shift); // input pulldown

  // Никакого SysTick ещё нет: несколько десятков HSI-тактов дают матрице
  // установиться, а восемь подряд чтений отсекают одиночный фронт питания.
  for(u8 settle = 0; settle < 64; settle++) __NOP();
  u32 stable_high = COLUMN_BIT;
  for(u8 sample = 0; sample < 8; sample++) {
    stable_high &= COLUMN_GPIO->IDR;
    for(u8 gap = 0; gap < 8; gap++) __NOP();
  }

  GPIOB->MODER = saved_b_moder;
  GPIOB->OTYPER = saved_b_otyper;
  GPIOB->PUPDR = saved_b_pupdr;
  GPIOB->BSRR = (saved_b_odr & ROW_BIT) != 0
      ? ROW_BIT : (ROW_BIT << 16U);
#if defined(CDU)
  COLUMN_GPIO->MODER = saved_column_moder;
  COLUMN_GPIO->PUPDR = saved_column_pupdr;
#endif
  RCC->AHB1ENR = saved_ahb1enr;
  __DSB();
  return (stable_high & COLUMN_BIT) != 0;
}

#endif // MK61_EARLY_DFU_SUPPORTED

} // namespace

namespace early_dfu {

bool consume_request(void) {
  return consume_request_internal();
}

[[noreturn]] void request(void) {
  prepare_request();
  reset_prepared();
}

void prepare_request(void) {
  publish_request();
}

[[noreturn]] void reset_prepared(void) {
  NVIC_SystemReset();
  while(true) {}
}

Diagnostic diagnostic(void) {
#if MK61_EARLY_DFU_SUPPORTED
  return read_diagnostic();
#else
  return {false, 0, early_dfu_protocol::STAGE_NONE,
          early_dfu_protocol::SOURCE_NONE};
#endif
}

const char* diagnostic_stage_name(early_dfu_protocol::Stage stage) {
  switch(stage) {
    case early_dfu_protocol::STAGE_PUBLISHED:      return "published";
    case early_dfu_protocol::STAGE_ACCEPTED:       return "accepted";
    case early_dfu_protocol::STAGE_VECTOR_INVALID: return "vector-invalid";
    case early_dfu_protocol::STAGE_BRANCHING:      return "branching";
    case early_dfu_protocol::STAGE_RETRYING:       return "retrying";
    case early_dfu_protocol::STAGE_COMPLETED:      return "completed";
    case early_dfu_protocol::STAGE_RETRY_EXHAUSTED:
      return "retry-exhausted";
    case early_dfu_protocol::STAGE_ABORTED:        return "aborted";
    case early_dfu_protocol::STAGE_NONE:           return "none";
  }
  return "invalid";
}

} // namespace early_dfu

#if MK61_EARLY_DFU_SUPPORTED

// Newlib выполняет .preinit_array до STM32duino premain(), init(), HAL,
// USB CDC и всех C++-конструкторов. На штатной загрузке пролог возвращается,
// и weak init() ядра запускает hw_config_init() без нашего вмешательства.
extern "C" void mk61_early_dfu_preinit(void) {
  const u8 sources = consume_request_sources_internal();
  if(sources != early_dfu_protocol::SOURCE_NONE) {
    // A fresh explicit request supersedes any stale interrupted attempt.
    clear_attempt();
    (void) try_enter_system_memory(
        sources, 1, early_dfu_protocol::STAGE_BRANCHING);
    return;
  }

  const early_dfu_protocol::Attempt attempt = read_attempt();
  if(attempt.valid) {
    const u32 reset_flags = reset_cause_flags();
    const bool software_reset = (reset_flags & RCC_CSR_SFTRSTF) != 0;
    if(early_dfu_protocol::retry_after_reset(attempt, software_reset)) {
      (void) try_enter_system_memory(
          attempt.sources, (u8) (attempt.number + 1U),
          early_dfu_protocol::STAGE_RETRYING);
      return;
    }

    clear_attempt();
    const u8 diagnostic_sources = attempt.sources |
        (attempt.number > 1
            ? (u8) early_dfu_protocol::SOURCE_RETRY : (u8) 0);
    if(software_reset &&
       attempt.number >= early_dfu_protocol::MAX_ATTEMPTS) {
      write_diagnostic(early_dfu_protocol::STAGE_RETRY_EXHAUSTED,
                       diagnostic_sources);
    } else if(reset_flags == 0) {
      // USB DFU manifestation uses the ROM's direct jump to user Flash.
      write_diagnostic(early_dfu_protocol::STAGE_COMPLETED,
                       diagnostic_sources);
    } else {
      // Power, pin or watchdog reset cancels the transaction safely.
      write_diagnostic(early_dfu_protocol::STAGE_ABORTED,
                       diagnostic_sources);
    }
    // Do not sample ESC in the same boot: a key that was held for the original
    // emergency entry must not immediately start a second DFU transaction.
    return;
  }

  if(emergency_escape_pressed()) {
    write_diagnostic(early_dfu_protocol::STAGE_ACCEPTED,
                     early_dfu_protocol::SOURCE_ESCAPE);
    clear_attempt();
    (void) try_enter_system_memory(
        early_dfu_protocol::SOURCE_ESCAPE, 1,
        early_dfu_protocol::STAGE_BRANCHING);
    return;
  }
}

extern "C" {
__attribute__((used, section(".preinit_array")))
extern void (*const mk61_early_dfu_preinit_slot)(void) =
    mk61_early_dfu_preinit;
}

#endif
