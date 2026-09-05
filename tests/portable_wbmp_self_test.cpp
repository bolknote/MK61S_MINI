#include "mk61_app.h"

#include <cassert>
#include <cstring>
#include <vector>
#include <cstdio>

const mk61_app_api* mk61_api;
namespace {
std::vector<uint8_t> input;
std::vector<std::vector<uint8_t>> frames;
std::vector<int32_t> keys;
size_t key_index;
uint32_t width, height, revision, starts, ends, services;
bool present_ok, begin_ok, short_read, available;

bool dark(uint32_t x, uint32_t y) { return (x * 3 + y * 5) % 11 < 5; }
void mb(uint32_t x) {
  if(x >= 128) input.push_back((x >> 7) | 128);
  input.push_back(x & 127);
}
void fixture(uint32_t w, uint32_t h) {
  input = {0, 0}; mb(w); mb(h);
  const size_t offset = input.size();
  const size_t stride = (w + 7) / 8;
  input.resize(offset + stride * h);
  for(uint32_t y = 0; y < h; ++y)
    for(uint32_t x = 0; x < w; ++x)
      if(!dark(x, y)) input[offset + y * stride + x / 8] |= 0x80 >> (x % 8);
  assert(input.size() <= 1600);
}
std::vector<uint8_t> oracle(uint32_t w, uint32_t h, uint32_t x0, uint32_t y0) {
  std::vector<uint8_t> out(width * ((height + 7) / 8));
  for(uint32_t y = 0; y < height; ++y)
    for(uint32_t x = 0; x < width; ++x)
      if(x + x0 < w && y + y0 < h && dark(x + x0, y + y0))
        out[(y / 8) * width + x] |= 1 << (y % 8);
  return out;
}

void reset() {
  frames.clear(); keys = {MK61_APP_KEY_ESC}; key_index = 0;
  width = 192; height = 64; revision = starts = ends = services = 0;
  present_ok = begin_ok = available = true; short_read = false;
}
uint32_t size(uint32_t id) { return id == 42 ? input.size() : UINT32_MAX; }
uint32_t read(uint32_t id, uint32_t offset, uint8_t* out, uint32_t length) {
  assert(id == 42 && offset == 0 && length == input.size());
  std::memcpy(out, input.data(), length); return length - (short_read ? 1 : 0);
}
void service() { assert(++services < 100); }
void delay(uint32_t) {}
int32_t key() {
  assert(key_index < keys.size());
  const auto result = keys[key_index++];
  if(result == -99) { ++revision; return MK61_APP_KEY_NONE; }
  return result;
}
uint32_t get_width() { return width; }
uint32_t get_height() { return height; }
uint32_t get_revision() { return revision; }
uint32_t get_available() { return available; }
uint32_t begin() { ++starts; return begin_ok; }
void end() { ++ends; }
uint32_t present(const uint8_t* bytes, uint32_t length) {
  frames.emplace_back(bytes, bytes + length); return present_ok;
}
}

int main() {
  mk61_app_api api{};
  api.magic = MK61_APP_API_MAGIC; api.version = MK61_APP_API_VERSION;
  api.struct_size = sizeof(api);
  api.capabilities = MK61_APP_CAP_TIME | MK61_APP_CAP_KEYBOARD |
      MK61_APP_CAP_FILES | MK61_APP_CAP_GRAPHICS;
  api.file_size = size; api.file_read = read; api.service = service;
  api.delay_ms = delay; api.key_poll = key;
  api.graphics_width = get_width; api.graphics_height = get_height;
  api.graphics_revision = get_revision; api.graphics_available = get_available;
  api.graphics_begin = begin; api.graphics_end = end;
  api.graphics_present = present; mk61_api = &api;

  reset(); fixture(208, 48);
  keys = {MK61_APP_KEY_RIGHT, MK61_APP_KEY_RIGHT, MK61_APP_KEY_RIGHT,
          MK61_APP_KEY_LEFT, MK61_APP_KEY_ESC};
  assert(mk61_app_open_file(42) == MK61_APP_OK);
  assert(frames == (std::vector<std::vector<uint8_t>>{
      oracle(208,48,0,0), oracle(208,48,8,0), oracle(208,48,16,0), oracle(208,48,8,0)}));
  assert(starts == 1 && ends == 1);
  reset(); fixture(144, 80);
  keys = {MK61_APP_KEY_SHIFT_RIGHT, MK61_APP_KEY_SHIFT_RIGHT,
          MK61_APP_KEY_SHIFT_LEFT, MK61_APP_KEY_OK};
  assert(mk61_app_open_file(42) == MK61_APP_OK);
  assert(frames == (std::vector<std::vector<uint8_t>>{
      oracle(144,80,0,0), oracle(144,80,0,16), oracle(144,80,0,0)}));
  reset(); fixture(13,9);
  keys = {-99, MK61_APP_KEY_ESC};
  assert(mk61_app_open_file(42) == MK61_APP_OK);
  assert(starts == 2 && ends == 2 && frames.size() == 2);
  assert(frames[0] == oracle(13,9,0,0) && frames[1] == frames[0]);
  reset(); fixture(13,9); present_ok = false;
  assert(mk61_app_open_file(42) == MK61_APP_RUNTIME_ERROR && ends == 1);
  reset(); begin_ok = false;
  assert(mk61_app_open_file(42) == MK61_APP_UNSUPPORTED_DISPLAY && ends == 0);
  reset(); width = 193;
  assert(mk61_app_open_file(42) == MK61_APP_UNSUPPORTED_DISPLAY && ends == 1);
  reset(); short_read = true;
  assert(mk61_app_open_file(42) == MK61_APP_IO_ERROR && starts == 0);
  reset(); input[1] = 1;
  assert(mk61_app_open_file(42) == MK61_APP_INVALID_FILE && starts == 0);
  reset(); assert(mk61_app_open_file(41) == MK61_APP_INVALID_FILE);
  api.capabilities = 0;
  assert(mk61_app_open_file(42) == MK61_APP_UNSUPPORTED_DISPLAY);
  std::puts("portable WBMP: pixel oracle, navigation, backend changes and failures PASS");
}
