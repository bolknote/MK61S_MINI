#include <stm32f4xx.h>
#include "stm32f4_usb_wakeup.hpp"

#include <stdio.h>

#ifdef OTG_FS_WKUP_IRQn
  #error "This regression requires a CMSIS enum IRQ, not a macro"
#endif

int main() {
  usb_test_exti = {1U << 2, 1U << 3, USB_WAKE_LINE | (1U << 4)};
  for(unsigned attempt = 1; attempt <= 2; ++attempt) {
    stm32f4_usb_wakeup::arm();
#if MK61_USB_SUSPEND_SUPPORTED && MK61_TEST_USB_DEVICE
    assert(usb_test_priority_calls == attempt && usb_test_enable_calls == attempt);
    assert(usb_test_irq == OTG_FS_WKUP_IRQn);
    assert(usb_test_priority == USBD_IRQ_PRIO);
    assert(usb_test_subpriority == USBD_IRQ_SUBPRIO);
    assert(usb_test_exti.RTSR == ((1U << 2) | USB_WAKE_LINE));
    assert(usb_test_exti.IMR == ((1U << 3) | USB_WAKE_LINE));
#else
    assert(usb_test_priority_calls == 0 && usb_test_enable_calls == 0);
    assert(usb_test_exti.RTSR == (1U << 2));
    assert(usb_test_exti.IMR == (1U << 3));
#endif
    // Arming must preserve a host resume that arrived before STOP entry.
    assert(usb_test_exti.PR == (USB_WAKE_LINE | (1U << 4)));
  }
  puts("usb_stop_wakeup_self_test: ok");
}
