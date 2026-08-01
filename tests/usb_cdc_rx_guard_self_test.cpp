#include "usb_cdc_rx_guard.hpp"

#include <cassert>
#include <cstring>
#include <iostream>

int main() {
  usb_cdc_rx_guard::reset_statistics();
  const usb_cdc_rx_guard::Snapshot snapshot =
      usb_cdc_rx_guard::statistics();
  assert(!snapshot.supported);
  assert(!snapshot.linked);
  assert(snapshot.throttles == 0);
  assert(std::strcmp(usb_cdc_rx_guard::backend_name(), "disabled") == 0);
  std::cout << "usb_cdc_rx_guard_self_test: ok\n";
  return 0;
}
