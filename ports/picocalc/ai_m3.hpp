#ifndef MK61_PICOCALC_AI_M3_HPP
#define MK61_PICOCALC_AI_M3_HPP
#include "mk61_ai_linear.hpp"
namespace picocalc::ai_m3 {
struct Statistics {
  bool active = false;
  int error = 0;
  std::uint32_t setup_us = 0, sent = 0, received = 0, requests = 0;
  std::uint32_t vectors = 0, jobs = 0, rows = 0, max_slice_us = 0;
  std::uint32_t uart_errors = 0, unload_failures = 0, context_bytes = 0;
};
#if defined(PICO_ON_DEVICE)
// Core 0 only. Refuses audio's UART and any resident foreign module.
bool open(const char *path = "/AI/M3LINE.S3M");
void close();
bool open_draft(const char *path = "/AI/M3DRAFT.S3M");
void close_draft();
bool predict(const std::uint16_t *tail, unsigned count, unsigned generated,
             std::uint16_t &token, std::uint8_t &confidence);
inline constexpr unsigned draft_history_limit = 118;
unsigned prepare(const mk61ai::LinearBatch *);
bool submit(mk61ai::LinearBatch *);
bool join();
Statistics statistics();
#else
inline bool open(const char * = "/AI/M3LINE.S3M") { return false; }
inline void close() {}
inline void close_draft() {}
inline unsigned prepare(const mk61ai::LinearBatch *) { return 0; }
inline bool submit(mk61ai::LinearBatch *) { return false; }
inline bool join() { return false; }
inline Statistics statistics() { return {}; }
#endif
}
#endif
