#ifndef MK61_AI_LINEAR_HPP
#define MK61_AI_LINEAR_HPP
#include "mk61_ai_model.hpp"

namespace mk61ai {
// All pointers refer to SRAM supplied by core 0. A worker never reads the
// model package, tokenizer, KV, or shared-memory backend. Input/LUT lifetime
// ends only after join(); output rows and per-job status have one writer.
struct LinearBatch {
  Arithmetic arithmetic = Arithmetic::LUT_FLOAT32;
  unsigned columns = 0, bits = 4, grid = 256, rows = 0;
  const float *input = nullptr, *activation_scales = nullptr;
  const float *input_sums = nullptr, *lookup = nullptr;
  const std::int8_t *quant = nullptr;
  const std::uint8_t *weights = nullptr, *scales = nullptr;
  float *output = nullptr;
  ModelStatus status = ModelStatus::OK;
};
void linear_batch_flash(void *batch);
void linear_batch_sram(void *batch);
} // namespace mk61ai
#endif
