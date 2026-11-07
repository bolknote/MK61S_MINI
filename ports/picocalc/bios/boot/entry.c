#include "hal_interface.h"
#include "m3b_entry.h"
#include "protocol.h"
volatile uint8_t bios_update_requested;
__attribute__((noinline, used)) int bios_boot_keep_pico(void) {
  volatile uint32_t *box = (volatile uint32_t *)M3B_MAILBOX;
  const int keep = box[2] == M3B_KEEP && box[3] == ~M3B_KEEP;
  box[2] = box[3] = 0;
  return keep;
}
/* Called from the main loop after its single ACK has left USART3. GPIO and
 * PMU outputs stay latched; the boot reset handler reinitializes only RAM. */
__attribute__((naked, noreturn)) static void enter(uint32_t address
                                                   __attribute__((unused))) {
  __asm volatile("cpsid i\nmovw r1, #0xed08\nmovt r1, #0xe000\nstr r0, "
                 "[r1]\nldr r1, [r0]\nldr r0, [r0, #4]\nmovs r2, #0\nmsr "
                 "control, r2\nmsr msp, r1\ndsb\nisb\nbx r0");
}
__attribute__((noinline, used)) void bios_boot_enter(void) {
  __disable_irq();
  SysTick->CTRL = 0;
  for (unsigned i = 0; i < 3; ++i) {
    NVIC->ICER[i] = ~0u;
    NVIC->ICPR[i] = ~0u;
  }
  volatile uint32_t *box = (volatile uint32_t *)M3B_MAILBOX;
  box[0] = M3B_FORCE;
  box[1] = ~M3B_FORCE;
  __DSB();
  enter(M3B_FLASH);
}
