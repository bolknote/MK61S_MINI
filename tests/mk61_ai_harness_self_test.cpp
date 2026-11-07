#include "mk61emu_core.h"

#include "mk61_ai_harness.hpp"
#include "mk61_ref.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <vector>
namespace {
struct Disk {
  std::map<std::string, std::vector<unsigned char>> files;
  int writes = -1;
  mk61ai::Store store() { return {this, read, write, exists}; }
  static bool exists(void *p, const char *name) {
    return static_cast<Disk *>(p)->files.count(name) != 0;
  }
  static bool read(void *p, const char *name, void *out, unsigned cap,
                   unsigned &n) {
    auto &d = *static_cast<Disk *>(p);
    auto at = d.files.find(name);
    if (at == d.files.end() || at->second.size() > cap)
      return false;
    n = unsigned(at->second.size());
    std::memcpy(out, at->second.data(), n);
    return true;
  }
  static bool write(void *p, const char *name, const void *data, unsigned n) {
    auto &d = *static_cast<Disk *>(p);
    if (d.writes == 0)
      return false;
    if (d.writes > 0)
      --d.writes;
    auto *b = static_cast<const unsigned char *>(data);
    d.files[name] = {b, b + n};
    return true;
  }
};
struct Service {
  core_61::ContextBuffer original{};
  unsigned calls = 0, cancel_at = 0;
  bool cancel = false;
  static bool tick(void *p) {
    auto &s = *static_cast<Service *>(p);
    core_61::ContextBuffer now{};
    assert(core_61::save_context(now));
    assert(!std::memcmp(now.bytes, s.original.bytes, sizeof(now.bytes)));
    ++s.calls;
    return !s.cancel && (!s.cancel_at || s.calls < s.cancel_at);
  }
};
} // namespace
int main(int argc, char **argv) {
  using namespace mk61ai;
  Reply reply{};
  assert(parse_reply("<plan>сложить</plan><write>60 61 10 50</write><run/>",
                     reply));
  assert(reply.write && reply.run && reply.size == 4);
  assert(!parse_reply("<write>60 61 10</write>", reply));
  assert(!parse_reply("<write>60 FFF 50</write><run/>", reply));
  assert(!parse_reply("<write>60 50</write><run/><shell>bad</shell>", reply));
  assert(!parse_reply("<run/><run/>", reply));
  assert(parse_reply("<plan><write>60 50</write><run/></plan><done/>", reply) &&
         !reply.write);
  assert(parse_reply("<ask>Где вход?</ask>", reply) && reply.question[0]);
  assert(parse_reply("<write>60611050</write><run/>", reply) &&
         reply.size == 4);
  assert(parse_reply("<patch>02:1150;00:60</patch><run/>", reply) &&
         reply.patch);
  assert(!parse_reply("<patch>00:60;00:61</patch><run/>", reply));
  assert(!parse_reply("<patch>69:50</patch><run/>", reply));
  Example example{};
  assert(parse_example("R0=7 R1=5 => X=12; ATOL=0 RTOL=0 ANGLE=RAD STEPS=64",
                       example));
  assert(example.inputs == 3 && example.has_expected &&
         example.expected == 12 && example.max_commands == 64);
  assert(!parse_example("R0=7 R0=8 => X=15", example));
  assert(!parse_example("RF=1 => X=2", example));
  assert(!parse_example("R0=nan => X=2", example));
  assert(parse_example("X=-3 Y=4 => X=?", example) && !example.has_expected);
  Disk disk;
  Session s{};
  s.id = 17;
  assert(set_task(s, "X = R0 + R1.", false));
  assert(parse_example("R0=7 R1=5 => X=12", example));
  assert(set_example(s, 0, example));
  const unsigned char code[] = {0x60, 0x61, 0x10, 0x50};
  assert(accept_program(disk.store(), s, code, 4) && s.program.version == 1);
  Session restored{};
  assert(load_session(disk.store(), 17, restored));
  assert(!std::strcmp(restored.task, s.task));
  assert(restored.program.size == 4 &&
         !std::memcmp(restored.program.bytes, code, 4));
  std::uint8_t wire[8192];
  unsigned n = encode_session(s, wire, sizeof(wire));
  assert(n && n < sizeof(wire));
  Session sentinel{};
  sentinel.id = 999;
  wire[n - 1] ^= 1;
  assert(!decode_session(wire, n, sentinel) && sentinel.id == 999);
  wire[n - 1] ^= 1;
  assert(!decode_session(wire, n - 1, sentinel));
  // Commit failure leaves the current program intact; an orphan is never
  // reused.
  disk.writes = 1;
  const unsigned char other[] = {9, 0x50};
  assert(!accept_program(disk.store(), s, other, 2));
  assert(s.program.version == 1);
  disk.writes = -1;
  assert(accept_program(disk.store(), s, other, 2) && s.program.version == 3);
  assert(select_program(disk.store(), s, 1) && s.program.bytes[0] == 0x60);
  core_61::set_expanded_program_mode(false);
  core_61::enable();
  MK61Emu_SetAngleUnit(GRADE);
  assert(mk61_ref::write({mk61_ref::Kind::R, 0}, 42.5));
  assert(mk61_ref::write({mk61_ref::Kind::X, 0}, -3.25));
  assert(core_61::write_absolute_program(0, 7) &&
         core_61::write_absolute_program(1, 0x50));
  Service service;
  assert(core_61::save_context(service.original));
  Trace trace[16];
  unsigned count = 0;
  Result result = execute(s.program, s.tests[0], s.task_revision, Service::tick,
                          &service, trace, &count);
  if (result.status != Execution::STOPPED || result.x != 12 || !result.passed ||
      count != 4 || !service.calls)
    std::fprintf(stderr,
                 "run status=%u X=%.16g passed=%u commands=%lu trace=%u "
                 "callbacks=%u code=%02X %02X %02X %02X\n",
                 unsigned(result.status), result.x, result.passed,
                 (unsigned long)result.commands, count, service.calls,
                 s.program.bytes[0], s.program.bytes[1], s.program.bytes[2],
                 s.program.bytes[3]);
  assert(result.status == Execution::STOPPED && result.x == 12 &&
         result.passed && count == 4 && service.calls > 0);
  core_61::ContextBuffer after{};
  assert(core_61::save_context(after));
  assert(
      !std::memcmp(after.bytes, service.original.bytes, sizeof(after.bytes)));
  s.results[0] = result;
  assert(all_passed(s));
  assert(save_session(disk.store(), s));
  assert(select_program(disk.store(), s, 3));
  assert(!all_passed(s));
  assert(select_program(disk.store(), s, 1));
  assert(all_passed(s));
  service.cancel = true;
  result =
      execute(s.program, s.tests[0], s.task_revision, Service::tick, &service);
  assert(result.status == Execution::CANCELLED && !result.passed);
  assert(core_61::save_context(after));
  assert(
      !std::memcmp(after.bytes, service.original.bytes, sizeof(after.bytes)));
  Program loop{};
  loop.size = 2;
  loop.bytes[0] = 0x51;
  loop.bytes[1] = 0;
  Example bounded{};
  bounded.max_commands = 8;
  result = execute(loop, bounded, s.task_revision);
  assert(result.status == Execution::LIMIT && result.commands == 8);
  service.cancel = false;
  service.calls = 0;
  service.cancel_at = 2;
  bounded.max_commands = 4096;
  result = execute(loop, bounded, s.task_revision, Service::tick, &service);
  assert(result.status == Execution::CANCELLED && service.calls == 2 &&
         result.commands > 0);
  assert(core_61::save_context(after));
  assert(
      !std::memcmp(after.bytes, service.original.bytes, sizeof(after.bytes)));
  Example observe = s.tests[0];
  observe.has_expected = false;
  observe.expected_mask = 0;
  result = execute(s.program, observe, s.task_revision);
  assert(result.status == Execution::STOPPED && !result.passed);
  Example rich;
  assert(parse_example("R0=7 R1=5 => X=12 R0=7 R1=5 PRESERVE=R0,R1", rich));
  result = execute(s.program, rich, s.task_revision);
  assert(result.passed && result.actual[0] == 7 && result.actual[1] == 5);
  char formatted[1537];
  assert(format_example(rich, formatted, sizeof(formatted)));
  Example roundtrip;
  assert(parse_example(formatted, roundtrip) && roundtrip.preserve == 3 &&
         expectation_mask(roundtrip) == (3 | X_MASK));
  Program clobber;
  clobber.size = 4;
  clobber.bytes[0] = 9;
  clobber.bytes[1] = 0x40;
  clobber.bytes[2] = 0x60;
  clobber.bytes[3] = 0x50;
  assert(parse_example("R0=7 => X=9 PRESERVE=R0", rich));
  result = execute(clobber, rich, s.task_revision);
  assert(!result.passed && (result.mismatch & 1) && result.actual[0] == 9);
  Program game;
  const unsigned char increment[] = {0x60, 1, 0x10, 0x40, 0x50, 0x51, 0};
  game.size = sizeof(increment);
  std::memcpy(game.bytes, increment, sizeof(increment));
  assert(parse_example(
      "R0=5 => X=6 R0=6 | => R0=7 | R0=10 => X=11 | KEY=29 => R0=12", rich));
  service.cancel_at = 0;
  result = execute(game, rich, s.task_revision, Service::tick, &service);
  if (!result.passed)
    std::fprintf(
        stderr,
        "scenario status=%u X=%g stages=%u fail=%u mismatch=%lx commands=%lu\n",
        unsigned(result.status), result.x, unsigned(result.completed_stages),
        unsigned(result.failed_stage), (unsigned long)result.mismatch,
        (unsigned long)result.commands);
  assert(result.passed && result.completed_stages == 3 &&
         result.stage_values[0] == 7 && result.stage_values[1] == 11 &&
         result.stage_values[2] == 12);
  assert(format_example(rich, formatted, sizeof(formatted)) &&
         parse_example(formatted, roundtrip) && roundtrip.scenario_count == 3);
  Program keyboard;
  keyboard.size = 1;
  keyboard.bytes[0] = 0x50;
  Example keys;
  assert(parse_example("=> X=0 | KEY=41 => X=2 | KEY=51 => X=23", keys));
  const auto key_result = execute(keyboard, keys, s.task_revision);
  assert(key_result.passed && key_result.completed_stages == 2 &&
         key_result.stage_values[1] == 23);
  assert(!parse_example("=> X=0 | KEY=C1 => X=2", keys));
  assert(!parse_example("X=2 => X=2 | X=3 X=4 => X=5", rich));
  service.cancel_at = 0;
  assert(set_task(s, "Сохрани регистры.", true) && !all_passed(s));
  assert(apply_program(s.program));
  double value;
  assert(mk61_ref::read({mk61_ref::Kind::R, 0}, value) && value == 42.5);
  assert(mk61_ref::read({mk61_ref::Kind::X, 0}, value) && value == -3.25);
  assert(load_example_inputs(s.tests[0]) && MK61Emu_GetAngleUnit() == RADIAN);
  std::uint32_t id = 999;
  assert(reserve_session_id(disk.store(), 17, id) && id == 18);
  assert(reserve_session_id(disk.store(), 0, id) &&
         id == 19); // New boot; uptime is irrelevant.
  disk.writes = 0;
  assert(!reserve_session_id(disk.store(), 0, id) && id == 19);
  disk.writes = -1;
  assert(reserve_session_id(disk.store(), 0, id) && id == 20);
  assert(set_example(s, 1, roundtrip));
  s.results[1] = result;
  assert(save_session(disk.store(), s) &&
         load_session(disk.store(), 17, restored));
  assert(restored.tests[1].scenario_count == 3 &&
         restored.results[1].stage_values[2] == 12);
  if (argc == 2) {
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<std::uint8_t> legacy((std::istreambuf_iterator<char>(file)),
                                     {});
    Session old;
    assert(!legacy.empty() &&
           decode_session(legacy.data(), unsigned(legacy.size()), old) &&
           old.id == 61 && all_passed(old) && old.planning &&
           old.results[0].actual[15] == 12);
    assert(encode_session(old, wire, sizeof(wire)) && wire[6] == '2');
  }
  std::puts("MK61 AI harness: parser, cases, durable versions, commit failure, "
            "isolation, pause and limits PASS");
}
