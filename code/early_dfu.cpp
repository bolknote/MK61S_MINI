#include "early_dfu.hpp"

#include "early_dfu_protocol.hpp"

#if defined(ARDUINO_ARCH_STM32)
  #include <Arduino.h>
#endif

#if MK61_EARLY_DFU_SUPPORTED
  #include "config.h"
  #include "keyboard_layout.hpp"
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
}

bool consume_request_internal(void) {
  const u32 magic = mk61_early_dfu_request.magic;
  const u32 inverse_magic = mk61_early_dfu_request.inverse_magic;
  mk61_early_dfu_request.magic = 0;
  mk61_early_dfu_request.inverse_magic = 0;
  __DMB();
  return early_dfu_protocol::valid(magic, inverse_magic);
}

#if MK61_EARLY_DFU_SUPPORTED

static constexpr u32 SYSTEM_MEMORY_BASE = 0x1FFF0000UL;
static constexpr u32 SYSTEM_MEMORY_LIMIT = 0x1FFF7800UL;
static constexpr u32 VALID_SRAM_BASE = 0x20000000UL;
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

bool try_enter_system_memory(void) {
  const u32 stack = *(const u32*) SYSTEM_MEMORY_BASE;
  const u32 entry = *(const u32*) (SYSTEM_MEMORY_BASE + sizeof(u32));
  if(!boot_vectors_valid(stack, entry)) return false;
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
  publish_request();
  NVIC_SystemReset();
  while(true) {}
}

} // namespace early_dfu

#if MK61_EARLY_DFU_SUPPORTED

// Newlib выполняет .preinit_array до STM32duino premain(), init(), HAL,
// USB CDC и всех C++-конструкторов. На штатной загрузке пролог возвращается,
// и weak init() ядра запускает hw_config_init() без нашего вмешательства.
extern "C" void mk61_early_dfu_preinit(void) {
  if(consume_request_internal()) {
    if(try_enter_system_memory()) return;
  }
  if(emergency_escape_pressed()) {
    if(try_enter_system_memory()) return;
  }
}

extern "C" {
__attribute__((used, section(".preinit_array")))
extern void (*const mk61_early_dfu_preinit_slot)(void) =
    mk61_early_dfu_preinit;
}

#endif
