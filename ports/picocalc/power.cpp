#include "power.hpp"
#include "io_worker.hpp"
#include "hardware/clocks.h"
#include "hardware/irq.h"
#include "hardware/pll.h"
#include "hardware/structs/scb.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"
#include "tusb.h"

namespace picocalc {
namespace {
bool usb_power() { return gpio_get(PICO_VBUS_PIN); }
void uart_clock_changed() {
#if PICO_STDIO_UART && defined(PICO_DEFAULT_UART_BAUD_RATE)
  uart_set_baudrate(uart_default, PICO_DEFAULT_UART_BAUD_RATE);
#endif
}
}
void SleepClocks::init() {
  gpio_init(PICO_VBUS_PIN);
  gpio_set_dir(PICO_VBUS_PIN, GPIO_IN);
  // The SDK normally clocks RTC from PLL_USB. XOSC / 256 provides the
  // identical 46875 Hz without keeping the USB PLL running on batteries.
  clock_configure(clk_rtc, 0, CLOCKS_CLK_RTC_CTRL_AUXSRC_VALUE_XOSC_CLKSRC,
                  XOSC_HZ, clock_get_hz(clk_rtc));
}
void SleepClocks::enter() {
  if (active_) return;
  io_worker::drain();
  usb_ = usb_power();
  sys_hz_ = clock_get_hz(clk_sys);
  peri_hz_ = clock_get_hz(clk_peri);
  sleep_en0_ = clocks_hw->sleep_en0;
  sleep_en1_ = clocks_hw->sleep_en1;
  scr_ = scb_hw->scr;
  adc_ctrl_ = clocks_hw->clk[clk_adc].ctrl;
  adc_div_ = clocks_hw->clk[clk_adc].div;
  adc_hz_ = clock_get_hz(clk_adc);
  usb_ctrl_ = clocks_hw->clk[clk_usb].ctrl;
  usb_div_ = clocks_hw->clk[clk_usb].div;
  usb_hz_ = clock_get_hz(clk_usb);
  // At 48 MHz USB continues to enumerate and serve CDC. Battery operation
  // uses XOSC at 12 MHz. Never switch off a PLL while any slice uses it.
  clock_configure_undivided(clk_sys,
      usb_ ? CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLKSRC_CLK_SYS_AUX
           : CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLK_REF,
      usb_ ? CLOCKS_CLK_SYS_CTRL_AUXSRC_VALUE_CLKSRC_PLL_USB : 0,
      usb_ ? USB_CLK_HZ : clock_get_hz(clk_ref));
  clock_configure_undivided(clk_peri, 0,
      CLOCKS_CLK_PERI_CTRL_AUXSRC_VALUE_CLK_SYS, clock_get_hz(clk_sys));
  pll_deinit(pll_sys);
  clock_stop(clk_adc);
  if (!usb_) {
    tud_disconnect();
    usb_irq_ = irq_is_enabled(USBCTRL_IRQ);
    irq_set_enabled(USBCTRL_IRQ, false);
    clock_stop(clk_usb);
    pll_deinit(pll_usb);
    ++battery_entries_;
  }
  uart_clock_changed();
  // WAKE_EN is untouched: SRAM, XIP and I2C resume automatically on wake.
  // No DMA or I2C transaction may be active at entry. Retain the alarm-pool
  // timer and watchdog; RTC continues even while both cores are asleep.
  clocks_hw->sleep_en0 = CLOCKS_SLEEP_EN0_CLK_RTC_RTC_BITS;
  clocks_hw->sleep_en1 = CLOCKS_SLEEP_EN1_CLK_SYS_TIMER_BITS |
      CLOCKS_SLEEP_EN1_CLK_SYS_WATCHDOG_BITS |
      (usb_ ? CLOCKS_SLEEP_EN1_CLK_SYS_USBCTRL_BITS |
                  CLOCKS_SLEEP_EN1_CLK_USB_USBCTRL_BITS : 0);
  scb_hw->scr |= M0PLUS_SCR_SLEEPDEEP_BITS;
  active_ = true;
  ++entries_;
}
void SleepClocks::leave() {
  if (!active_) return;
  io_worker::drain();
  // set_sys_clock_hz briefly uses PLL_USB while restarting PLL_SYS.
  if (!usb_) pll_init(pll_usb, PLL_USB_REFDIV, PLL_USB_VCO_FREQ_HZ,
                     PLL_USB_POSTDIV1, PLL_USB_POSTDIV2);
  set_sys_clock_hz(sys_hz_, true);
  clock_configure_undivided(clk_peri, 0,
      CLOCKS_CLK_PERI_CTRL_AUXSRC_VALUE_CLK_SYS, peri_hz_);
  clocks_hw->clk[clk_adc].div = adc_div_;
  clocks_hw->clk[clk_adc].ctrl = adc_ctrl_;
  clock_set_reported_hz(clk_adc, adc_hz_);
  if (!usb_) {
    clocks_hw->clk[clk_usb].div = usb_div_;
    clocks_hw->clk[clk_usb].ctrl = usb_ctrl_;
    clock_set_reported_hz(clk_usb, usb_hz_);
    irq_set_enabled(USBCTRL_IRQ, usb_irq_);
    tud_connect();
  }
  clocks_hw->sleep_en0 = sleep_en0_;
  clocks_hw->sleep_en1 = sleep_en1_;
  scb_hw->scr = scr_;
  uart_clock_changed();
  active_ = false;
}
bool SleepClocks::refresh() {
  if (!active_ || usb_ == usb_power()) return false;
  leave();
  enter();
  return true;
}
unsigned SleepClocks::pll_mask() const {
  return ((pll_sys->pwr & PLL_PWR_PD_BITS) ? 0U : 1U) |
         ((pll_usb->pwr & PLL_PWR_PD_BITS) ? 0U : 2U);
}
} // namespace picocalc
