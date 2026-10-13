#include "system_compat.hpp"
#include "setup_font_compiler.hpp"
#include "setup_ui.hpp"
#include "setup_service.hpp"
#include "prepared_font.hpp"

#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

extern "C" u32 mk61_app_initialize(const mk61_app_api*, u32, u32);
namespace {
std::vector<u8> source;
std::array<u8, 8192> workspace{}, installed{};
u32 revision = 1;
unsigned streams = 0, installs = 0;
bool supported = false, late_failure = false, stale = false;

u32 dispatch(u32 operation, u32 a, u32, u32, void* payload) {
  if(operation == MK61_SYS_SETUP && a == MK61_SETUP_VERSION)
    return MK61_SETUP_API_VERSION;
  if(operation == MK61_SERVICE_RESOURCE_READ) {
    if(a == 0) return revision;
    assert(a == 3);
    if(!payload) return supported;
    if(!supported) return 0;
    const auto& request = *static_cast<mk61_service_resource_bytes*>(payload);
    assert(request.id == 1 && request.source_size == source.size());
    if(request.revision != revision) return 0;
    ++streams;
    for(u8 value : source) if(!request.next(request.context, value)) return 0;
    if(stale) ++revision;
    return !late_failure && request.revision == revision;
  }
  assert(false); return 0;
}
u32 size(u32 id) { return id == 1 ? (u32) source.size() : 0; }
mk61_app_api app_api{};
mk61_system_api services{};
}
namespace portable_system {
const mk61_system_api* api = &services;
const mk61_app_api* app = &app_api;
bool bind(const mk61_app_api*, u32, u32) { return true; }
}
namespace language_workspace {
Lease::Lease(Owner owner, usize size) : Lease() {
  assert(owner == Owner::SETUP && size == workspace.size());
  lease_.data = workspace.data(); lease_.size = size;
}
Lease::~Lease() { reset(); }
void Lease::reset() { lease_.data = nullptr; }
}
namespace setup_ui {
bool hardware() { return true; }
bool date_time() { return true; }
bool calibration() { return true; }
bool font() { return true; }
void step_font(i8) {}
void preview(const char*, const u8*, u16) {}
u32 service(u32 operation, u32, u32, void* payload) {
  assert(operation == MK61_SETUP_PREPARED_FONT_INSTALL);
  const auto& request = *static_cast<mk61_setup_prepared_font*>(payload);
  prepared_font::Face face;
  assert(face.open(request.data, request.size));
  ++installs;
  std::memcpy(installed.data(), request.data, request.size);
  return MK61_TEXT_FONT_OK;
}
}

int main(int argc, char** argv) {
  assert(argc == 2);
  std::ifstream input(argv[1], std::ios::binary);
  assert(input.good());
  source = std::vector<u8>(std::istreambuf_iterator<char>(input),
                          std::istreambuf_iterator<char>());
  services.call = dispatch; app_api.file_size = size;
#if MK61_UI_FONT_CLIENT
  assert(mk61_app_initialize(&app_api, 0, MK61_APP_KIND_SETUP) == 1);
  supported = true;
  assert(mk61_app_initialize(&app_api, 0, MK61_APP_KIND_SETUP) == 0);
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_OK);
  assert(streams == 1 && installs == 1);
  const auto old = installed;
  late_failure = true;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_UNAVAILABLE);
  assert(installs == 1 && installed == old);
  late_failure = false; stale = true;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_UNAVAILABLE);
  assert(installs == 1 && installed == old);
  stale = false;
  source.back() ^= 1;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_INVALID);
  assert(installs == 1 && installed == old);
#else
  assert(mk61_app_initialize(&app_api, 0, MK61_APP_KIND_SETUP) == 0);
  assert(streams == 0 && installs == 0);
#endif
  std::puts("setup_font_stream_app_self_test: binary capability, one stream and late failure gates passed");
}
