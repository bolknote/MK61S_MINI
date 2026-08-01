#include <cassert>
#include <iostream>

#include "spi1_dma.hpp"

int main(void) {
  static_assert(!MK61_SPI1_DMA_SUPPORTED,
                "host test must use the explicit disabled backend");
  spi1_dma::reset_statistics();
  assert(spi1_dma::transfer(nullptr, nullptr, nullptr, 512) ==
         spi1_dma::Result::NOT_USED);
  const spi1_dma::Snapshot snapshot = spi1_dma::statistics();
  assert(!snapshot.supported);
  assert(snapshot.threshold == MK61_SPI1_DMA_THRESHOLD);
  assert(snapshot.transfers == 0);
  assert(snapshot.polling_fallbacks == 1);
  assert(snapshot.transfer_failures == 0);
  assert(snapshot.timeouts == 0);
  assert(std::string(spi1_dma::backend_name()) == "disabled");
  std::cout << "spi1_dma_self_test: ok\n";
  return 0;
}
