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

  const u32 first = early_dfu_protocol::diagnostic_word(
      1, early_dfu_protocol::STAGE_PUBLISHED,
      early_dfu_protocol::SOURCE_SRAM |
          early_dfu_protocol::SOURCE_BACKUP);
  const early_dfu_protocol::Diagnostic decoded =
      early_dfu_protocol::decode_diagnostic(first);
  assert(decoded.valid);
  assert(decoded.generation == 1);
  assert(decoded.stage == early_dfu_protocol::STAGE_PUBLISHED);
  assert(decoded.sources == (early_dfu_protocol::SOURCE_SRAM |
                             early_dfu_protocol::SOURCE_BACKUP));
  assert(early_dfu_protocol::next_generation(first) == 2);
  assert(early_dfu_protocol::next_generation(0) == 1);
  assert(early_dfu_protocol::next_generation(
      early_dfu_protocol::diagnostic_word(
          0xFF, early_dfu_protocol::STAGE_BRANCHING,
          early_dfu_protocol::SOURCE_ESCAPE)) == 1);
  assert(!early_dfu_protocol::decode_diagnostic(0).valid);

  using early_dfu_protocol::Attempt;
  const u32 attempt1 = early_dfu_protocol::attempt_word(
      1, early_dfu_protocol::SOURCE_SRAM |
             early_dfu_protocol::SOURCE_BACKUP);
  const Attempt decoded_attempt =
      early_dfu_protocol::decode_attempt(attempt1, ~attempt1);
  assert(decoded_attempt.valid);
  assert(decoded_attempt.number == 1);
  assert(decoded_attempt.sources ==
         (early_dfu_protocol::SOURCE_SRAM |
          early_dfu_protocol::SOURCE_BACKUP));
  assert(early_dfu_protocol::retry_after_reset(decoded_attempt, true));
  assert(!early_dfu_protocol::retry_after_reset(decoded_attempt, false));

  for(u8 number = 1; number <= early_dfu_protocol::MAX_ATTEMPTS; number++) {
    const u32 word = early_dfu_protocol::attempt_word(
        number, early_dfu_protocol::SOURCE_ESCAPE);
    const Attempt attempt = early_dfu_protocol::decode_attempt(word, ~word);
    assert(attempt.valid);
    assert(attempt.number == number);
    assert(early_dfu_protocol::retry_after_reset(attempt, true) ==
           (number < early_dfu_protocol::MAX_ATTEMPTS));
  }
  const u32 zero_attempt = early_dfu_protocol::attempt_word(
      0, early_dfu_protocol::SOURCE_ESCAPE);
  assert(!early_dfu_protocol::decode_attempt(
      zero_attempt, ~zero_attempt).valid);
  const u32 excessive_attempt = early_dfu_protocol::attempt_word(
      early_dfu_protocol::MAX_ATTEMPTS + 1,
      early_dfu_protocol::SOURCE_ESCAPE);
  assert(!early_dfu_protocol::decode_attempt(
      excessive_attempt, ~excessive_attempt).valid);
  const u32 recursive_attempt = early_dfu_protocol::attempt_word(
      1, early_dfu_protocol::SOURCE_RETRY);
  assert(!early_dfu_protocol::decode_attempt(
      recursive_attempt, ~recursive_attempt).valid);

  // A one-bit error in either retained word must never authorize a retry.
  for(u32 bit = 0; bit < 32; bit++) {
    const u32 mask = 1UL << bit;
    assert(!early_dfu_protocol::decode_attempt(
        attempt1 ^ mask, ~attempt1).valid);
    assert(!early_dfu_protocol::decode_attempt(
        attempt1, (~attempt1) ^ mask).valid);
  }

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
