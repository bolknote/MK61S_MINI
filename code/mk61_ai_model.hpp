#ifndef MK61_AI_MODEL_HPP
#define MK61_AI_MODEL_HPP
#include <cstddef>
#include <cstdint>
#include "block_read.hpp"

namespace mk61ai {
// All offsets are relative to an immutable MKA package. Backends may use
// indirect PSRAM; no pointer into external memory is ever dereferenced.
struct Memory {
  void *context = nullptr;
  std::uint32_t size = 0;
  bool (*read)(void *, std::uint32_t, void *, unsigned) = nullptr;
  bool (*write)(void *, std::uint32_t, const void *, unsigned) = nullptr;
  // Optional immutable-source prefetch. False means no operation was started;
  // finish must stop all writes before returning, including an I/O failure.
  bool (*read_begin)(void *, const block_io::ReadSpan *, unsigned) = nullptr;
  bool (*read_finish)(void *) = nullptr;
};
enum class ModelStatus : std::uint8_t {
  OK,
  IO,
  FORMAT,
  MEMORY,
  TEXT_LONG,
  CONTEXT,
  CANCELLED,
  NUMERIC
};
enum class Arithmetic : std::uint8_t { FLOAT32, INT8, LUT_INT8, LUT_FLOAT32 };
enum class LinearKernel : std::uint8_t { REFERENCE, FLASH, SRAM };
struct ComputeExecution {
  // submit publishes one bounded SRAM-only job; join completes it before any
  // input, LUT, tile, output or job descriptor is changed or destroyed.
  void *context = nullptr;
  bool (*submit)(void *, void (*)(void *), void *) = nullptr;
  void (*join)(void *) = nullptr;
  void (*busy)(void *, bool) = nullptr;
  LinearKernel kernel = LinearKernel::REFERENCE;
  bool filter_head = false;
  bool prefetch = true;
  std::uint32_t (*micros)(void *) = nullptr; // Optional diagnostic timing only.
};
struct ComputeMetrics {
  std::uint32_t rows = 0, skipped_rows = 0, worker_jobs = 0, worker_rows = 0;
  std::uint32_t checksum = 2166136261U;
  std::uint32_t prefetches = 0, prefetched_bytes = 0;
  std::uint32_t read_us = 0, matmul_us = 0, wait_us = 0;
};
struct ModelConfig {
  std::uint32_t layers, hidden, intermediate, heads, kv_heads, head_dim;
  std::uint32_t vocab, context, bos, eos;
  float epsilon;
};
// Float32 activations and KV are the reference path. INT8 is an explicit
// alternative for linear layers, requiring separate model-quality evaluation.
// The caller supplies one reusable workspace and a separate KV allocation.
class Model {
public:
  static constexpr unsigned MAX_TEXT = 2048;
  ModelStatus open(Memory package, bool verify_crc = true);
  const ModelConfig &config() const { return config_; }
  std::size_t workspace_bytes() const;
  std::uint32_t cache_bytes() const;
  ModelStatus bind(void *workspace, std::size_t bytes, Memory cache);
  void reset() { position_ = 0; }
  bool rewind(unsigned position) {
    if (position > position_)
      return false;
    position_ = position;
    return true;
  }
  unsigned position() const { return position_; }
  void execution(ComputeExecution value) { execution_ = value; }
  ComputeExecution execution() const { return execution_; }
  const ComputeMetrics &compute_metrics() const { return compute_metrics_; }
  ModelStatus encode(const char *utf8, std::uint16_t *tokens, unsigned capacity,
                     unsigned &used, bool bos = true);
  ModelStatus decode(std::uint16_t token, char *out, unsigned capacity,
                     unsigned &used);
  // On cancellation position does not advance; repeating this token safely
  // overwrites only its incomplete KV rows. Earlier positions remain valid.
  ModelStatus forward(std::uint16_t token, bool output, std::uint16_t &best,
                      bool (*service)(void *) = nullptr,
                      void *context = nullptr,
                      Arithmetic arithmetic = Arithmetic::FLOAT32,
                      float *logits = nullptr,
                      bool (*allowed)(void *, std::uint16_t) = nullptr,
                      void *policy = nullptr);

private:
  friend class Tokenizer;
  struct Tensor {
    std::uint32_t rows, cols, bits, grid, data, scale, bytes, scales;
  };
  Memory package_{}, cache_{};
  ModelConfig config_{};
  std::uint32_t header_[32]{};
  std::uint32_t position_ = 0;
  std::uint8_t *workspace_ = nullptr;
  std::size_t bound_ = 0;
  ComputeExecution execution_{};
  ComputeMetrics compute_metrics_{};
  bool read(std::uint32_t offset, void *out, unsigned bytes) const;
  bool tensor(unsigned index, Tensor &out) const;
};
const char *model_status_text(ModelStatus status);
} // namespace mk61ai
#endif
