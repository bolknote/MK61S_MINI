#include "ai_clock.hpp"
#include "compute_clock.hpp"
#if defined(PICO_ON_DEVICE)
#include "io_worker.hpp"
#include "psram.hpp"
#include "audio_stream.hpp"
#include "hardware/clocks.h"
#include "hardware/i2c.h"
#include "hardware/irq.h"
#include "hardware/spi.h"
#include "hardware/structs/ssi.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"
#include "tusb.h"
#endif
#ifndef MK61_PICOCALC_AI_OVERCLOCK
#define MK61_PICOCALC_AI_OVERCLOCK 0
#endif
namespace picocalc::ai_clock {
u32 hz() {
#if defined(PICO_ON_DEVICE)
  return clock_get_hz(clk_sys);
#else
  return 0;
#endif
}
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
namespace {
void retune(u32 spi0_hz,u32 spi1_hz) {
  if(spi0_hz) spi_set_baudrate(spi0,spi0_hz);
  if(spi1_hz) spi_set_baudrate(spi1,spi1_hz);
  i2c_set_baudrate(i2c1,10000);
#if LIB_PICO_STDIO_UART && defined(PICO_DEFAULT_UART_BAUD_RATE)
  uart_set_baudrate(uart_default,PICO_DEFAULT_UART_BAUD_RATE);
#endif
  psram::clock_changed();
}
bool transition(u32 sys,State& s,bool restoring) {
  // This image boots with Flash SCK / 6, hence <= 50 MHz at every allowed
  // rate. No live SSI reconfiguration, voltage increase or RTC changes.
  io_worker::drain();stdio_flush();
  const bool usb_irq=irq_is_enabled(USBCTRL_IRQ);
  tud_disconnect();irq_set_enabled(USBCTRL_IRQ,false);
  const u32 usb_ctrl=clocks_hw->clk[clk_usb].ctrl,usb_div=clocks_hw->clk[clk_usb].div;
  const u32 usb_hz=clock_get_hz(clk_usb);
  clock_stop(clk_usb);
  busy_wait_us(1); // Allow the USB clock gate to settle before lowering SYS.
  // Keep SPI/UART's parent independent of PLL_SYS while it is reconfigured.
  clock_configure_undivided(clk_peri,0,CLOCKS_CLK_PERI_CTRL_AUXSRC_VALUE_CLKSRC_PLL_USB,48000000);
  const bool ok=set_sys_clock_khz(unsigned(sys/1000),false);
  if(restoring) {
    clocks_hw->clk[clk_peri].div=s.peri_div;
    clocks_hw->clk[clk_peri].ctrl=s.peri_ctrl;
    clock_set_reported_hz(clk_peri,s.peri);
  } else {
    clock_configure_undivided(clk_peri,0,CLOCKS_CLK_PERI_CTRL_AUXSRC_VALUE_CLKSRC_PLL_USB,48000000);
  }
  retune(s.spi0_hz,s.spi1_hz);
  clocks_hw->clk[clk_usb].div=usb_div;clocks_hw->clk[clk_usb].ctrl=usb_ctrl;
  clock_set_reported_hz(clk_usb,usb_hz);
  irq_set_enabled(USBCTRL_IRQ,usb_irq);tud_connect();
  return ok && clock_get_hz(clk_sys)==sys;
}
}
#endif
bool begin(unsigned mhz,State& s) {
  if(s.changed || s.restore_attempted || (mhz!=125 && mhz!=200 && mhz!=250 && mhz!=300)) return false;
  s.sys=hz();
  if(compute_clock::active_profile())return mhz==125;
  if(mhz==125 && (!s.sys || s.sys==125000000)) return true;
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
  if(s.sys!=125000000) return false;
  if(audio_stream::active()) return false;
  if(ssi_hw->baudr!=6) return false;
  // Reject malformed/unsupported PLL requests before disconnecting USB.
  unsigned vco=0,post1=0,post2=0;
  if(!check_sys_clock_khz(mhz*1000,&vco,&post1,&post2)) return false;
  io_worker::drain();
  s.peri=clock_get_hz(clk_peri);s.peri_ctrl=clocks_hw->clk[clk_peri].ctrl;
  s.peri_div=clocks_hw->clk[clk_peri].div;
  s.spi0_hz=spi_get_baudrate(spi0);s.spi1_hz=spi_get_baudrate(spi1);
  s.changed=true;
  if(transition(mhz*1000000U,s,false)) return true;
  (void)restore(s);return false;
#else
  return false;
#endif
}
bool restore(State& s) {
  if(!s.changed) return true;
  if(s.restore_attempted) return false;
  s.restore_attempted=true;
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
  const bool ok=transition(s.sys,s,true);
  if(ok) s.changed=false;
  return ok;
#else
  return false;
#endif
}
}
