#ifndef MK61_USB_STOP_WAKEUP_TEST_STM32_H
#define MK61_USB_STOP_WAKEUP_TEST_STM32_H

#include <assert.h>
#include <stdint.h>

// Match CMSIS: this IRQ identifier is deliberately an enum, never a macro.
typedef enum { OTG_FS_WKUP_IRQn = 42 } IRQn_Type;
#if MK61_TEST_USB_DEVICE
  #define USB_OTG_FS 1
#endif
enum { USBD_IRQ_PRIO = 5, USBD_IRQ_SUBPRIO = 0 };
static constexpr uint32_t USB_WAKE_LINE = 1U << 18;
struct TestExti { uint32_t RTSR, IMR, PR; };
inline TestExti usb_test_exti = {};
inline unsigned usb_test_priority_calls = 0;
inline unsigned usb_test_enable_calls = 0;
inline IRQn_Type usb_test_irq = OTG_FS_WKUP_IRQn;
inline uint32_t usb_test_priority = 0;
inline uint32_t usb_test_subpriority = 0;

#define __HAL_USB_OTG_FS_WAKEUP_EXTI_ENABLE_RISING_EDGE() \
  (usb_test_exti.RTSR |= USB_WAKE_LINE)
#define __HAL_USB_OTG_FS_WAKEUP_EXTI_ENABLE_IT() \
  (usb_test_exti.IMR |= USB_WAKE_LINE)

inline void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t priority, uint32_t subpriority) {
  usb_test_irq = irq;
  usb_test_priority = priority;
  usb_test_subpriority = subpriority;
  ++usb_test_priority_calls;
}
inline void HAL_NVIC_EnableIRQ(IRQn_Type irq) {
  assert(irq == OTG_FS_WKUP_IRQn);
  assert(usb_test_priority_calls == usb_test_enable_calls + 1);
  assert((usb_test_exti.RTSR & USB_WAKE_LINE) != 0);
  assert((usb_test_exti.IMR & USB_WAKE_LINE) != 0);
  ++usb_test_enable_calls;
}

#endif
