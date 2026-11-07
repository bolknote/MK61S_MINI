#include "mk61_ai_model.hpp"
#include <cstring>
#include <vector>
namespace {
mk61ai::Model model;
std::vector<std::uint64_t> workspace;
std::vector<std::uint8_t> cache;
const std::uint8_t *source;
unsigned size;
int cancel_after = -1;
bool read_package(void *, std::uint32_t at, void *p, unsigned n) {
  if (at > size || n > size - at)
    return false;
  std::memcpy(p, source + at, n);
  return true;
}
bool read_cache(void *, std::uint32_t at, void *p, unsigned n) {
  if (at > cache.size() || n > cache.size() - at)
    return false;
  std::memcpy(p, cache.data() + at, n);
  return true;
}
bool write_cache(void *, std::uint32_t at, const void *p, unsigned n) {
  if (at > cache.size() || n > cache.size() - at)
    return false;
  std::memcpy(cache.data() + at, p, n);
  return true;
}
bool service(void *) { return cancel_after < 0 || cancel_after-- > 0; }
} // namespace
extern "C" {
int mk_ai_open(const unsigned char *p, unsigned n) {
  source = p;
  size = n;
  auto status = model.open({nullptr, n, read_package, nullptr});
  if (status != mk61ai::ModelStatus::OK)
    return int(status);
  workspace.resize((model.workspace_bytes() + 7) / 8);
  cache.resize(model.cache_bytes());
  return int(
      model.bind(workspace.data(), workspace.size() * 8,
                 {nullptr, unsigned(cache.size()), read_cache, write_cache}));
}
int mk_ai_encode(const char *s, unsigned short *out, unsigned capacity,
                 unsigned *used, int bos) {
  return int(model.encode(s, out, capacity, *used, bos));
}
int mk_ai_decode(unsigned short id, char *out, unsigned capacity,
                 unsigned *used) {
  return int(model.decode(id, out, capacity, *used));
}
int mk_ai_forward(unsigned short token, int output, unsigned short *best,
                  float *logits, int arithmetic) {
  return int(model.forward(token, output, *best, service, nullptr,
                           static_cast<mk61ai::Arithmetic>(arithmetic),
                           logits));
}
void mk_ai_reset() {
  model.reset();
  cancel_after = -1;
}
void mk_ai_cancel_after(int n) { cancel_after = n; }
unsigned mk_ai_position() { return model.position(); }
int mk_ai_rewind(unsigned n) { return model.rewind(n); }
int mk_ai_forward_only(unsigned short token, unsigned short *best,
                       unsigned allowed) {
  return int(model.forward(
      token, true, *best, service, nullptr, mk61ai::Arithmetic::LUT_FLOAT32,
      nullptr,
      [](void *p, std::uint16_t id) {
        return id == *static_cast<unsigned *>(p);
      },
      &allowed));
}
unsigned mk_ai_workspace() { return unsigned(model.workspace_bytes()); }
unsigned mk_ai_cache() { return model.cache_bytes(); }
}
