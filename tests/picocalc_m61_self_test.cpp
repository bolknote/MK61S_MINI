#include "mk61emu_core.h"

#include "crc32.hpp"
#include "m61_text.hpp"
#include "mk61_ref.hpp"
#include "mk8_literal.hpp"
#include "program_load.hpp"
#include "screen.hpp"
#include "script.hpp"
#include "clock.hpp"
#include "services.hpp"
#include "terminal_catalog.hpp"
#include "terminal_mnemonics.hpp"
#include "terminal_script.hpp"
#include "zx0.hpp"
#include <cassert>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

namespace {
using namespace picocalc;
void source(const char *path, const char *text) {
  assert(files::write_text(path, text, (unsigned)std::strlen(text)));
}
void asset(const char *from, const char *to) {
  std::ifstream input(from, std::ios::binary);
  assert(input.good());
  const std::string bytes((std::istreambuf_iterator<char>(input)), {});
  assert(files::write(to, (const u8 *)bytes.data(), (unsigned)bytes.size()));
}
void tick(Calculator &calc) {
  m61_text::service();
  if (!m61_text::calculator_suspended())
    calc.tick();
  m61_text::service();
}
double reg(unsigned index) {
  double value = 0;
  assert(mk61_ref::read({mk61_ref::Kind::R, (u8)index}, value));
  return value;
}
double x() {
  double value = 0;
  assert(mk61_ref::read({mk61_ref::Kind::X, 0}, value));
  return value;
}
template <typename Predicate> void until(Calculator &calc, Predicate done) {
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!done() && std::chrono::steady_clock::now() < deadline) {
    tick(calc);
    if (m61_text::calculator_suspended())
      std::this_thread::sleep_for(std::chrono::microseconds(100));
  }
  m61_text::Error error{};
  if (m61_text::last_error(error))
    std::fprintf(stderr, "M61 test %s:%u %s\n", error.script, error.line,
                 error.message);
  if (!done())
    std::fprintf(
        stderr,
        "M61 timeout: active=%d suspended=%d RUN=%d IP=%u X=%g R3=%g R4=%g\n",
        m61_text::active(), m61_text::calculator_suspended(), core_61::is_RUN(),
        core_61::get_IP(), x(), reg(3), reg(4));
  assert(done() && !m61_text::last_error(error));
}
void reset(Calculator &calc, Services &services) {
  m61_text::cancel();
  calc.init();
  script::attach(calc, services);
  script::memory_mode(2);
  services.open(Action::DEVELOPMENT, false, calc);
  services.input(0x1B);
  services.set_pump(nullptr, nullptr);
}
} // namespace
void picocalc_m61_test() {
  using namespace picocalc;
  Calculator calc;
  static Services services;
  assert(files::mkdir("/M61 Tests") && files::mkdir("/M61 Tests/lib"));
  for (unsigned id = 0; id < 256; ++id)
    assert(terminal_command_allowed_in_script((u8)id) ==
           terminal_script::command_supported((u8)id));
  assert(terminal_script::execute("date 2026-10-17 18:00:00").kind==terminal_protocol::ResultKind::OK);
  assert(picocalc::clock::configured());
  assert(terminal_script::execute("alarm a in 10").kind==terminal_protocol::ResultKind::OK);
  assert(terminal_script::execute("date 2026-10-17 18:00:00",true).kind==terminal_protocol::ResultKind::ERROR);
  assert(terminal_script::execute("alarm a off").kind==terminal_protocol::ResultKind::OK);

  reset(calc, services);
  source("/M61 Tests/lib/child.m61", "R0= 8\nret\n");
  source("/M61 Tests/lib/a.tbi", "10 A=7\n20 @(3)=11\n30 END\n");
  source("/M61 Tests/lib/b.tbi", "10 .R1=A+@(3)\n20 END\n");
  source("/M61 Tests/lib/f1.foc", "1.10 SET A=3; EXIT\n");
  source("/M61 Tests/lib/f2.foc", "1.10 SET .R2=A+1; EXIT\n");
  source("/M61 Tests/main.m61",
         "R0= 6\nopen lib/child.m61\nopen lib/a.tbi\nopen lib/f1.foc\nopen "
         "lib/b.tbi\nopen lib/f2.foc\nif r1==18 run :ok\nR3= -1\nret\n:ok\nR3= "
         "42\nret\n");
  services.open(Action::EXPLORER, false, calc);
  assert(services.input('/'));
  for (const char *p = "M61 Tests/main.m61"; *p; ++p)
    assert(services.input((u8)*p));
  assert(services.input('\n') &&
         std::strcmp(services.page_name(), "EDITOR") == 0 &&
         std::strcmp(services.path(), "/M61 Tests/main.m61") == 0);
  services.input(0x1B);
  services.input(0x1B);
  assert(script::start("/M61 Tests/main.m61"));
  until(calc, [] { return !m61_text::active(); });
  assert(reg(0) == 8 && reg(1) == 18 && reg(2) == 4 && reg(3) == 42);

  // A helper replaces the source buffer while it runs. Unsaved root text
  // must return to its editor with the cursor/dirty state intact.
  const char *unsaved = "open \"M61 Tests/lib/a.tbi\"\nR8= 43\nret\n";
  services.new_document(Document::MK61);
  for (const char *p = unsaved; *p; ++p)
    assert(services.input((u8)*p));
  assert(services.input(0x83));
  services.tick();
  assert(!m61_text::active() && services.dirty() &&
         std::strcmp(services.page_name(), "EDITOR") == 0 &&
         !services.path()[0] &&
         services.source_size() == std::strlen(unsaved) && reg(8) == 43);
  char restored[Services::COLS + 1];
  services.row(0, restored);
  assert(std::strstr(restored, "M61 Tests/lib/a.tbi"));

  reset(calc, services);
  source("/M61 Tests/run.m61", "hin 0000 010E021050\nrun\nR4= 17\nret\n");
  assert(script::start("/M61 Tests/run.m61"));
  until(calc, [] { return !m61_text::active(); });
  assert(x() == 3 && reg(4) == 17);

  reset(calc, services);
  source(
      "/M61 Tests/trap.m61",
      "hin 0000 010E021050\ntrap 2 run :frame\nrun\nR3= 41\nret\n:frame\nprint "
      "off\nprint \"TRAP {X}\"\nwait 5\nprint on\nret\n");
  assert(script::start("/M61 Tests/trap.m61"));
  until(calc, [] {
    return m61_text::calculator_suspended() && m61_text::display_owned();
  });
  assert(core_61::owned_context_buffer(core_61::ContextBufferOwner::M61_TRAP));
  assert(script::input('a') && MK61Emu_GetAngleUnit() == RADIAN);
  until(calc, [] { return reg(3) == 41 && !core_61::is_RUN(); });
  assert(x() == 3 && MK61Emu_GetAngleUnit() == RADIAN && m61_text::active());
  assert(!core_61::owned_context_buffer(core_61::ContextBufferOwner::M61_TRAP));

  reset(calc, services);
  source("/M61 Tests/bind.m61", "bind 01 run :one\nret\n:one\nR0= 9\nret\n");
  assert(script::start("/M61 Tests/bind.m61") && m61_text::active());
  assert(calc.input('1'));
  until(calc, [] { return reg(0) == 9; });
  assert(x() == 0 && m61_text::active());

  reset(calc, services);
  source("/M61 Tests/manual.md", "# Manual\n\nUse **OK**.\n");
  source("/M61 Tests/ok.m61",
         "bind OK run :help\nret\n:help\nopen? manual.md\nret\n");
  unsigned viewer_keys = 0;
  services.set_pump(
      [](void *raw, u8 &key) {
        ++*(unsigned *)raw;
        key = 0x1B;
        return true;
      },
      &viewer_keys);
  assert(script::start("/M61 Tests/ok.m61") && script::input('\n'));
  until(calc, [&] { return viewer_keys && !m61_text::calculator_suspended(); });
  assert(m61_text::active());
  assert(script::input(0x1B) && !m61_text::active());

  reset(calc, services);
  asset("programs/games/Turochamp/Turochamp.FMK", "/M61 Tests/Turochamp.FMK");
  source("/M61 Tests/lib/font.tbi",
         "10 .R6=COLS\n20 .R7=ROWS\n30 PRINT \"FONT\"\n40 END\n");
  source("/M61 Tests/font.m61", "loadfont Turochamp\nopen lib/font.tbi\nbind "
                                "OK run :key\nret\n:key\nret\n");
  assert(script::start("/M61 Tests/font.m61"));
  until(calc, [] { return reg(6) > 0; });
  assert(reg(6) == 27 && reg(7) == 9 && script::font_active());
  char row[65];
  script::text_row(0, row, sizeof(row));
  assert(std::strstr(row, "FONT"));
  // A completed BASIC part retains the full M61 display between parts.
  // Zero bits must erase the calculator header as well as its separator.
  assert(!services.active() && m61_text::display_owned());
  Ui display_ui;
  display_ui.init(Settings{});
  Screen retained;
  retained.render(calc.snapshot(), true, &display_ui, &services);
  const u8 *expected_native = script::native_frame();
  assert(expected_native);
  for (unsigned y = 0; y < 320; ++y)
    for (unsigned x = 0; x < 320; ++x)
      assert(retained.pixel(x, y) ==
             bool(expected_native[y / 8 * 320 + x] & (1U << (y % 8))));
  // Exercise every tile, orientation and zero overwrite with unrelated
  // canvases, rather than accepting only one text-shaped bitmap.
  std::vector<u8> noise(Screen::BYTES);
  u32 word=0x713519B3U;
  for(unsigned pass=0;pass<4;++pass) {
    for(auto& byte:noise) {
      word^=word<<13;word^=word>>17;word^=word<<5;
      byte=pass==0?0:pass==1?255:(u8)word;
    }
    script::show_native_frame(noise.data());
    retained.render(calc.snapshot(),true,&display_ui,&services);
    for(unsigned y=0;y<320;++y) for(unsigned x=0;x<320;++x)
      assert(retained.pixel(x,y)==bool(noise[y/8*320+x]&(1U<<(y%8))));
  }
  assert(script::input(0x1B) && !script::font_active());

  reset(calc, services);
  // Embedded text exceeds the module budget; SOURCE recipes must still
  // support both PRINT and INPUT against the immutable editor snapshot.
  std::string large;
  for (unsigned line = 1; line <= 100; ++line)
    large +=
        std::to_string(line) + " PRINT \"" + std::string(120, 'A') + "\"\n";
  large += "101 INPUT \"VALUE\",A\n102 .R5=A\n103 END\n";
  std::vector<u8> image(language_vm::MAX_MODULE);
  const language_vm::ResourceSource embedded{
      0, 0, language_vm::ResourceMode::EMBEDDED};
  assert(language_vm::compile(language_vm::Language::BASIC, large.data(),
                              (u16)large.size(), image.data(),
                              (u16)image.size(), true, &embedded)
             .error == language_vm::Error::FULL);
  source("/M61 Tests/large.tbi", large.c_str());
  source("/M61 Tests/resources.m61", "open large.tbi\nret\n");
  const char *answer = "42\n";
  services.set_pump(
      [](void *raw, u8 &key) {
        auto &next = *(const char **)raw;
        if (!*next)
          return false;
        key = (u8)*next++;
        return true;
      },
      &answer);
  assert(script::start("/M61 Tests/resources.m61"));
  until(calc, [] { return !m61_text::active(); });
  assert(reg(5) == 42);

  reset(calc, services);
  assert(files::mkdir("/M61 Tests/Turochamp"));
  for (const auto &file :
       std::filesystem::directory_iterator("programs/games/Turochamp"))
    if (file.is_regular_file())
      asset(
          file.path().c_str(),
          ("/M61 Tests/Turochamp/" + file.path().filename().string()).c_str());
  struct Game {
    Services *services;
    bool menu = false, board = false;
    std::chrono::steady_clock::time_point deadline =
        std::chrono::steady_clock::now() + std::chrono::seconds(10);
  } game{&services};
  services.set_pump(
      [](void *raw, u8 &key) {
        auto &game = *(Game *)raw;
        assert(std::chrono::steady_clock::now() < game.deadline);
        char row[Services::COLS + 1];
        char heading[Services::COLS + 1];
        game.services->row(0, heading);
        for (unsigned i = 0; i < 9; ++i) {
          game.services->row(i, row);
          if (!game.menu && std::strstr(game.services->path(), "menu.tbi") &&
              std::strstr(row, M8("ОК - НАЧАТЬ"))) {
            game.menu = true;
            key = '\n';
            return true;
          }
          if (game.menu && std::strstr(heading, "abcdefgh") &&
              std::strstr(game.services->path(), "board.tbi") &&
              std::strstr(row, M8("ОК "))) {
            game.board = true;
            const u8 *frame = game.services->graphics();
            assert(frame);
            unsigned ink = 0;
            for (unsigned i = 0; i < 1536; ++i)
              ink += frame[i] != 0;
            assert(ink > 300);
            key = 0x1B;
            return true;
          }
        }
        return false;
      },
      &game);
  assert(script::start("/M61 Tests/Turochamp/autoexec.m61"));
  until(calc, [] { return !m61_text::active(); });
  assert(game.menu && game.board && !script::font_active());

  reset(calc, services);
  // A real CRC32+ZX0 image crosses bank zero, using the production decoder.
  std::vector<u8> plain = {1, 2, 3, 4, 5, 0x50};
  u32 crc = mk61_crc32::calculate(plain.data(), plain.size());
  std::vector<u8> packed = {(u8)crc, (u8)(crc >> 8), (u8)(crc >> 16),
                            (u8)(crc >> 24)},
                  work(4 * (plain.size() + 1));
  zx0::EncodeResult encoded;
  assert(zx0::encode(plain.data(), plain.size(), work.data(), work.size(),
                     {&packed,
                      [](void *p, u8 byte) {
                        ((std::vector<u8> *)p)->push_back(byte);
                        return true;
                      }},
                     encoded));
  assert(files::write("/M61 Tests/program.bin", packed.data(), packed.size()));
  source("/M61 Tests/binary.m61", "load 0110 program.bin\nret\n");
  assert(script::start("/M61 Tests/binary.m61"));
  until(calc, [] { return !m61_text::active(); });
  for (unsigned i = 0; i < plain.size(); ++i) {
    u8 byte = 0;
    assert(core_61::read_absolute_program(110 + i, byte) && byte == plain[i]);
  }

  reset(calc, services);
  program_load::reset();
  using Kind = terminal_protocol::ResultKind;
  assert(terminal_script::execute("hin 0000 0102").kind == Kind::OK);
  assert(terminal_script::execute("hin 0000 054Z").kind == Kind::ERROR);
  u8 opcode = 0;
  assert(core_61::read_absolute_program(0, opcode) && opcode == 1);
  assert(terminal_script::execute("if 0==1 unknown command").kind == Kind::OK);
  assert(terminal_script::execute("if 1==1 unknown command").kind ==
         Kind::ERROR);
  for (const char *denied :
       {"R0= 7", "poke X 7", "hin 0000 05", "open main.m61", "reinit", "run"})
    assert(terminal_script::execute(denied, true).kind == Kind::ERROR);
  const char *nested = "if r0==0 if 1<2 run :same-source";
  const auto result = terminal_script::execute(nested);
  assert(result.kind == Kind::GOTO_LABEL &&
         result.args == std::strstr(nested, "same-source"));
  assert(terminal_script::execute("R0= random").kind == Kind::OK &&
         reg(0) > 0 && reg(0) < 1);
  assert(terminal_script::execute("asm 0000 1 push 2 add hlt").kind ==
         Kind::OK);
  assert(terminal_script::execute("cmd 09").kind == Kind::OK);
  assert(terminal_script::execute("hin 0000 51050050").kind == Kind::OK);
  assert(terminal_script::execute("ins 0 01").kind == Kind::OK);
  assert(core_61::read_absolute_program(2, opcode) && opcode == 6);
  m61_text::cancel();
  script::reset_files();
  std::puts("PicoCalc shared M61: nested files, persistent languages, run, "
            "trap/context, bind/OK, font, binary, permissions PASS");
}
