#ifndef MK61_AI_MODEL_HPP
#define MK61_AI_MODEL_HPP
#include <cstddef>
#include <cstdint>
#include "block_read.hpp"

namespace mk61ai {
// Offsets refer to an MKA package, immutable during inference. Optional write
// supports explicit lossless repacking before bind(). Backends may use indirect
// PSRAM; no pointer into external memory is ever dereferenced.
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
enum class LinearKernel : std::uint8_t { REFERENCE, FLASH_CODE, SRAM };
struct LinearBatch;
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
  bool reuse_activations = true;
  bool batch_kv = true; // Gather adjacent KV positions into bounded DMA reads.
  bool parallel_attention = true; // Independent query heads use both cores.
  bool share_kv = true; // Process up to two query heads per cached KV read.
  bool lut8 = false; // Exact INT8 LUT8 for plane-packed128-column matrices.
  std::uint32_t (*micros)(void *) = nullptr; // Optional diagnostic timing only.
  // Optional coprocessor. prepare stages the immutable vector before PSRAM
  // prefetch and returns its row capacity. submit must leave no live job on
  // refusal; join always drains a successful submission, even on failure.
  unsigned (*remote_prepare)(void *, const LinearBatch *) = nullptr;
  bool (*remote_submit)(void *, LinearBatch *) = nullptr;
  bool (*remote_join)(void *) = nullptr;
  unsigned tile_rows = 8; // 24 reuses8-row buffers; 28 also fits28 hidden-width rows.
};
struct ComputeMetrics {
  std::uint32_t rows = 0, skipped_rows = 0, worker_jobs = 0, worker_rows = 0;
  std::uint32_t checksum = 2166136261U;
  std::uint32_t prefetches = 0, prefetched_bytes = 0;
  std::uint32_t read_us = 0, matmul_us = 0, wait_us = 0;
  // Wall time: embedding + transformer body, then final norm + classifier.
  // Zero when the optional diagnostic clock is absent.
  std::uint32_t layers_us = 0, classifier_us = 0;
  // Presentation brackets the layer/head timers. Service time is nested
  // inside those timers and must not be added to them a second time.
  std::uint32_t presentation_us = 0, service_us = 0, service_calls = 0;
  std::uint32_t remote_jobs = 0, remote_rows = 0, remote_fallbacks = 0;
  std::uint32_t remote_prepare_us = 0, remote_submit_us = 0, remote_wait_us = 0;
  std::uint32_t activation_preparations = 0, activation_reuses = 0;
  std::uint32_t attention_read_bytes = 0;
  std::uint32_t attention_read_transactions = 0, attention_batches = 0;
  std::uint32_t attention_worker_jobs = 0;
  std::uint32_t attention_us = 0, attention_io_us = 0;
  std::uint32_t lut8_preparations = 0, lut8_reuses = 0, lut8_rows = 0;
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
  // Only before bind(), on a private writable exported package. On error the
  // caller must discard the partial copy and reload its immutable source.
  ModelStatus repack_lut8(bool (*service)(void *) = nullptr, void *context = nullptr);
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
