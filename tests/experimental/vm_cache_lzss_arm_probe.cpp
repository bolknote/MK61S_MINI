// Research-only, no firmware includes this probe. Workspace is NOT on stack.
#include "vm_cache_lzss.hpp"
struct Job {
  const uint8_t* input;
  size_t size;
  uint8_t* output;
  size_t capacity, logical;
  vm_cache_lzss::Workspace* workspace;
  size_t written;
};
static_assert(sizeof(Job)==28,"ARM32 probe ABI");
extern "C" bool bench_encode(Job* job) {
  return vm_cache_lzss::encode(job->input,job->size,*job->workspace,
                             job->output,job->capacity,job->written);
}
extern "C" bool bench_decode(Job* job) {
  return vm_cache_lzss::decode(job->input,job->size,job->output,job->capacity,job->logical);
}
