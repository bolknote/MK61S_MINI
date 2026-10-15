#include "dwt_profiler.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#if MK61_DWT_SERVICE_GAPS_SUPPORTED
TestDwt test_dwt;
TestCoreDebug test_core_debug;
using namespace dwt_profiler;
static void tick(u32 cycles) {test_dwt.CYCCNT+=cycles;}
int main() {
  initialize();assert(available() && start());
  note_service(Service::USB_SCREEN);
  for(u32 cycles:{48000U,192000U,576000U,1056000U,2976000U}) {
    tick(cycles);note_service(Service::USB_SCREEN);
  }
  const auto& usb=service_gap(Service::USB_SCREEN);
  assert(usb.samples==5 && usb.total_cycles==4848000 && usb.maximum_cycles==2976000);
  assert(usb.over_1ms==4 && usb.over_5ms==3 && usb.over_10ms==2 && usb.over_30ms==1);
  assert(!service_gap(Service::KEYBOARD_POLL).samples);
  stop();tick(999);note_service(Service::USB_SCREEN);assert(usb.samples==5);
  assert(start());assert(!usb.samples && !usb.maximum_cycles);
  test_dwt.CYCCNT=0xFFFFFFF0U;note_service(Service::KEYBOARD_POLL);
  tick(32);note_service(Service::KEYBOARD_POLL);
  assert(service_gap(Service::KEYBOARD_POLL).maximum_cycles==32);
  reset();
  note_keyboard_row(0);tick(96000);note_keyboard_row(1);
  tick(96000);note_keyboard_row(2);tick(96000);note_keyboard_row(3);
  tick(96000);note_keyboard_row(4);tick(96000);note_keyboard_row(0);
  assert(service_gap(Service::KEYBOARD_SAMPLE).samples==5);
  assert(service_gap(Service::KEYBOARD_SAMPLE).maximum_cycles==96000);
  assert(service_gap(Service::KEYBOARD_ROW0).samples==1);
  assert(service_gap(Service::KEYBOARD_ROW0).maximum_cycles==480000);
  note_keyboard_row(5);note_keyboard_row(255);note_service((Service)255);
  assert(service_gap(Service::KEYBOARD_SAMPLE).samples==5);
  assert(!service_gap((Service)255).samples);
  auto& saturated=const_cast<ServiceGap&>(service_gap(Service::KEYBOARD_POLL));
  saturated.samples=UINT32_MAX;saturated.maximum_cycles=17;saturated.total_cycles=123;
  note_service(Service::KEYBOARD_POLL);tick(999);note_service(Service::KEYBOARD_POLL);
  assert(saturated.samples==UINT32_MAX && saturated.maximum_cycles==17 && saturated.total_cycles==123);
  std::set<std::string> names;
  for(usize i=0;i<SERVICE_COUNT;++i) {
    const auto* name=service_name((Service)i);
    assert(strcmp(name,"unknown") && names.insert(name).second);
  }
  reset();for(usize i=0;i<SERVICE_COUNT;++i)assert(!service_gap((Service)i).samples);
  puts("DWT service gaps: true start-to-start, matrix rows, first sample, wrap, reset, stop, saturation PASS");
}
#else
int main() {
  int side_effect=0;
  MK61_SERVICE_GAP(USB_SCREEN);MK61_KEYBOARD_ROW_GAP(++side_effect);
  assert(!side_effect);
  puts("DWT service gaps: disabled probes evaluate nothing PASS");
}
#endif
