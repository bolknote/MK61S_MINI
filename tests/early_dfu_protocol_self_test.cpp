#include "early_dfu_protocol.hpp"

#include <assert.h>
#include <stdio.h>

int main(void) {
  using early_dfu_protocol::MAGIC;
  using early_dfu_protocol::Request;

  static_assert(sizeof(Request) == 8, "retained DFU request must stay atomic-sized");
  static_assert(alignof(Request) == alignof(u32), "unexpected request alignment");
  static_assert(early_dfu_protocol::valid(MAGIC, ~MAGIC),
                "valid request rejected at compile time");

  assert(!early_dfu_protocol::valid(0, 0));
  assert(!early_dfu_protocol::valid(MAGIC, 0));
  assert(!early_dfu_protocol::valid(0, ~MAGIC));

  // Любое одиночное повреждение любого из двух retained-слов должно
  // отменять запрос, а не зацикливать плату в DFU.
  for(u32 bit = 0; bit < 32; bit++) {
    const u32 mask = 1UL << bit;
    assert(!early_dfu_protocol::valid(MAGIC ^ mask, ~MAGIC));
    assert(!early_dfu_protocol::valid(MAGIC, (~MAGIC) ^ mask));
  }

  // При publish magic пишется последним: оба промежуточных состояния
  // при reset невалидны, завершённое — валидно.
  Request request = {0xDEADBEEFUL, 0x01234567UL};
  request.magic = 0;
  assert(!early_dfu_protocol::valid(request.magic, request.inverse_magic));
  request.inverse_magic = ~MAGIC;
  assert(!early_dfu_protocol::valid(request.magic, request.inverse_magic));
  request.magic = MAGIC;
  assert(early_dfu_protocol::valid(request.magic, request.inverse_magic));

  printf("early_dfu_protocol_self_test: ok\n");
  return 0;
}
