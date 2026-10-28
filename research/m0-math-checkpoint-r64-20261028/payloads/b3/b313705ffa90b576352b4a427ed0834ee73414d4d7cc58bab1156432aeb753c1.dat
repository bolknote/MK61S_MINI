#ifndef MK61_STM32F4_USB_WAKEUP_HPP
#define MK61_STM32F4_USB_WAKEUP_HPP

namespace stm32f4_usb_wakeup {

inline void arm() {
#if MK61_USB_SUSPEND_SUPPORTED && defined(USB_OTG_FS)
  // CMSIS declares OTG_FS_WKUP_IRQn as an enum value, not a preprocessor
  // macro. F401/F411 with OTG FS have this interrupt; testing defined(IRQn)
  // would silently remove the wake configuration.
  __HAL_USB_OTG_FS_WAKEUP_EXTI_ENABLE_RISING_EDGE();
  __HAL_USB_OTG_FS_WAKEUP_EXTI_ENABLE_IT();
  HAL_NVIC_SetPriority(OTG_FS_WKUP_IRQn, USBD_IRQ_PRIO, USBD_IRQ_SUBPRIO);
  HAL_NVIC_EnableIRQ(OTG_FS_WKUP_IRQn);
#endif
}

} // namespace stm32f4_usb_wakeup

#endif
