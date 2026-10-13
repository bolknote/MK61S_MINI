#include "setup_font_compiler.hpp"
#include "setup_service.hpp"
#include "fmk_font.hpp"
#include "prepared_font.hpp"
#include "program_store.hpp"
#include "workspace_swap.hpp"

#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

namespace {
std::vector<u8> file;
std::array<u8, prepared_font::MAX_IMAGE_SIZE> active{};
usize active_size = 0, fail_at = (usize) -1, change_at = (usize) -1;
u32 revision = 1;
unsigned calls = 0;
bool install_failure = false;
bool late_crc_failure = false;
unsigned streams = 0, range_reads = 0;
}

namespace workspace_swap {
bool acquire(shared_memory::Owner owner, usize required, AcquireMode,
             shared_memory::Lease& destination) {
  return destination.acquire(shared_memory::Arena::WORKSPACE, owner, required);
}
}

namespace program_store {
u32 media_revision() { return revision; }
bool entry_by_id(u16 id, Entry& entry) {
  if(id != 1) return false;
  entry.data_len = (u16) file.size();
  return true;
}
bool read_range_id(u16 id, u16 offset, u8* output, u16 length, u16* count) {
  ++range_reads;
  assert(id == 1 && length <= 128U && (usize) offset + length <= file.size());
  *count = offset >= fail_at ? (u16) (length / 2U) : length;
  std::memcpy(output, file.data() + offset, *count);
  if(offset >= change_at) ++revision;
  return true;
}
bool stream_file_id(u16 id, const FileSink& sink) {
  assert(id == 1);
  ++streams;
  for(usize byte = 0; byte < file.size(); ++byte) {
    if(byte >= fail_at) return false;
    if(byte >= change_at) ++revision;
    if(!sink.next(sink.context, file[byte])) return false;
  }
  return !late_crc_failure;
}
}

namespace setup_ui {
u32 service(u32 operation, u32, u32, void* payload) {
  assert(operation == MK61_SETUP_PREPARED_FONT_INSTALL);
  ++calls;
  const auto& request = *static_cast<mk61_setup_prepared_font*>(payload);
  assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) ==
         shared_memory::Owner::SETUP);
  assert(shared_memory::contains(shared_memory::Arena::WORKSPACE,
                                 request.data, request.size));
  prepared_font::Face face;
  assert(face.open(request.data, request.size));
  if(install_failure) return (u32) MK61_TEXT_FONT_UNAVAILABLE;
  std::memcpy(active.data(), request.data, request.size);
  active_size = request.size;
  return MK61_TEXT_FONT_OK;
}
}

int main(int argc, char** argv) {
  assert(argc == 2);
  std::ifstream input(argv[1], std::ios::binary);
  assert(input.good());
  file = std::vector<u8>(std::istreambuf_iterator<char>(input),
                        std::istreambuf_iterator<char>());
  const auto valid = file;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_OK);
  assert(calls == 1);
  assert(streams == 1 && range_reads == 0);
  const auto old = active;
  const usize old_size = active_size;
  auto unchanged = [&]() {
    assert(active == old && active_size == old_size);
    assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) ==
           shared_memory::Owner::NONE);
  };
  // A live USB overlay pins heap growth. Font streaming must still work.
  shared_memory::Lease usb(shared_memory::Arena::OVERLAY,
                            shared_memory::Owner::USB_SCREEN, 2048U);
  assert(usb.ok());
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_OK);
  unchanged();
  const unsigned good_calls = calls;
  for(usize offset = 0; offset < file.size(); offset += 128U) {
    fail_at = offset;
    assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
           MK61_TEXT_FONT_UNAVAILABLE);
    assert(calls == good_calls); unchanged();
  }
  fail_at = (usize) -1;
  for(usize offset = 0; offset < file.size(); offset += 128U) {
    change_at = offset;
    assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
           MK61_TEXT_FONT_UNAVAILABLE);
    assert(calls == good_calls); unchanged();
  }
  change_at = (usize) -1;
  late_crc_failure = true;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_UNAVAILABLE);
  assert(calls == good_calls); unchanged();
  late_crc_failure = false;
  file.back() ^= 1;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_INVALID);
  assert(calls == good_calls); unchanged();
  file = valid;
  install_failure = true;
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_UNAVAILABLE);
  assert(calls == good_calls + 1U); unchanged();
  install_failure = false;
  assert(setup_font_compiler::install(2, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_INVALID);
  unchanged();
  // Busy workspace is unavailable and cannot reach the installation service.
  shared_memory::Lease busy(shared_memory::Arena::WORKSPACE,
                             shared_memory::Owner::APPLICATION, 32U);
  assert(busy.ok());
  assert(setup_font_compiler::install(1, MK61_PREPARED_FONT_TEXT, 0, 0, 0) ==
         MK61_TEXT_FONT_UNAVAILABLE);
  assert(active == old && active_size == old_size);
  assert(range_reads == 0);
  std::puts("setup_font_stream_self_test: one-pass source, live overlay, short reads, revision changes and atomic failures passed");
}
