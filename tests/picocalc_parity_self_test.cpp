#include "../ports/picocalc/terminal.hpp"
#include "m61_platform.hpp"
#include "markdown.hpp"
#include "mk61_ref.hpp"
#include "mk8_literal.hpp"
#include "script.hpp"
#include "terminal_file_transfer.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
namespace {
using namespace picocalc;
void write_text(const char *path, const char *text) {
  assert(files::write_text(path, text, (unsigned)std::strlen(text)));
}
void command(Terminal &terminal, const char *text) {
  for (; *text; ++text) {
    assert(terminal.receive((u8)*text) < 0);
    if (terminal.pending())
      terminal.tick();
  }
  if (!terminal.pending()) {
    terminal.receive('\r');
    terminal.tick();
  }
}
} // namespace
void picocalc_parity_test() {
  using namespace picocalc;
  Calculator calculator;
  calculator.init();
  Ui ui;
  ui.init();
  static Services services;
  services.set_ui(ui);
  services.open(Action::DEVELOPMENT, false, calculator);
  services.input(0x1B);
  script::attach(calculator, services);
  assert(files::mkdir("/Parity") && files::mkdir("/Parity/docs"));
  write_text("/Parity/docs/main.md",
             M8("# Начало\n\n[Далее](второй.md)\n\n[Нет](missing.md)\n"));
  write_text("/Parity/docs/второй.md", M8("# Второй\n\n[Назад](./main.md)\n"));
  MarkdownView view;
  assert(view.open("/Parity/docs/main.md") && view.links() == 2);
  char line[MarkdownView::COLS + 1], target[files::PATH_SIZE];
  view.row(0, line);
  assert(std::strstr(line, M8("Начало")) && !std::strchr(line, '#'));
  view.select(1);
  assert(view.selection == 0 && view.target(target) &&
         std::strcmp(target, "/Parity/docs/второй.md") == 0);
  bool highlighted = false;
  for (unsigned row = 0; row < 14; ++row)
    for (unsigned col = 0; col < 38; ++col)
      highlighted |= view.selected(row, col);
  assert(highlighted);
  view.select(1);
  assert(!view.target(target));
  view.select(-1);
  assert(view.target(target));
  const std::string long_line(120, 'x');
  write_text("/Parity/docs/long.md",
             (long_line + "\n[tail](main.md)\n").c_str());
  assert(view.open("/Parity/docs/long.md"));
  view.row(1, line);
  assert(std::strlen(line) == 38);
  view.row(3, line);
  assert(std::strncmp(line, "xxxxxx", 6) == 0 && std::strstr(line, "tail"));
  view.select(1);
  assert(view.target(target));
  // Exercise the real blocking viewer, not a separate navigation model.
  struct Nav {
    Services *s;
    unsigned step = 0;
  } nav{&services};
  services.set_pump(
      [](void *raw, u8 &key) {
        auto &n = *(Nav *)raw;
        assert(n.step < 8);
        static const u8 keys[] = {0xB7, '\r', 0xB7, '\r', 0x1B, 0x1B, 0x1B};
        if (n.step == 2)
          assert(std::strcmp(n.s->path(), "/Parity/docs/второй.md") == 0);
        if (n.step == 4)
          assert(std::strcmp(n.s->path(), "/Parity/docs/main.md") == 0);
        key = keys[n.step++];
        return true;
      },
      &nav);
  assert(services.view_markdown("/Parity/docs/main.md") == 0 && nav.step == 7);
  services.set_pump(nullptr, nullptr);
  assert(services.load_document("/Parity/docs/main.md", true));
  services.row(0, line);
  assert(line[0] == '#');
  services.input(0x1B);
  services.input(0x1B);
  std::string output;
  Terminal terminal(calculator, services, ui);
  terminal.init({&output,
                 [](void *raw, const char *text, unsigned n) {
                   ((std::string *)raw)->append(text, n);
                 },
                 nullptr, nullptr});
  assert(!terminal.raw());
  command(terminal, "mkdir -p /Parity/a/b");
  assert(files::exists("/Parity/a/b"));
  command(terminal, "cd /Parity/a/./b/..");
  assert(std::strcmp(terminal.directory(), "/Parity/a") == 0);
  command(terminal, M8("mkdir папка"));
  assert(files::exists("/Parity/a/папка"));
  command(terminal, "cd /");
  command(terminal, "ls /Parity");
  assert(output.find("docs/") != std::string::npos);
  const u8 data[] = {0, 255, 61, 42, 13, 10};
  const u32 crc = terminal_file_transfer::checksum(data, sizeof(data));
  char request[240];
  std::snprintf(request, sizeof(request), "fsput begin /Parity/data.bin %u %lu",
                (unsigned)sizeof(data), (unsigned long)crc);
  assert(terminal.execute(request));
  assert(terminal.execute("fsput data 0 00FF3D2A0D0A"));
  assert(terminal.execute("fsput end"));
  u8 copied[16];
  unsigned size = 0;
  assert(files::read("/Parity/data.bin", copied, sizeof(copied), size) &&
         size == sizeof(data) && !std::memcmp(data, copied, size));
  assert(terminal.execute("fsget /Parity/data.bin") &&
         output.find("@MKC:DATA 0 00FF3D2A0D0A") != std::string::npos);
  assert(terminal.execute("fsput begin /Parity/data.bin 1 0") &&
         terminal.execute("fsput data 0 11") && !terminal.execute("fsput end"));
  assert(files::read("/Parity/data.bin", copied, sizeof(copied), size) &&
         size == sizeof(data) && !std::memcmp(data, copied, size));
  assert(terminal.execute("fsput begin /Parity/interrupted.bin 1 0"));
  write_text("/Parity/change.txt", "changed");
  assert(!terminal.execute("fsput data 0 11") &&
         !files::exists("/Parity/interrupted.bin"));
  assert(terminal.execute("mv /Parity/data.bin /Parity/moved.bin"));
  assert(!files::exists("/Parity/data.bin") &&
         files::exists("/Parity/moved.bin"));
  assert(!terminal.execute("rm -r /"));
  assert(!terminal.execute("rmdir /Parity/docs"));
  assert(terminal.execute("rm -r /Parity/a") && !files::exists("/Parity/a"));
  command(terminal, "mkdir /Parity/history");
  command(terminal, "pwd");
  terminal.receive(0x1B);
  terminal.receive('[');
  terminal.receive('A');
  terminal.receive('\r');
  terminal.tick();
  assert(output.find("/\r\n") != std::string::npos);
  // Overlong input is rejected as a whole, including a valid-looking prefix.
  const std::string overflow = "mkdir /Parity/overflow" + std::string(250, 'x');
  command(terminal, overflow.c_str());
  assert(!files::exists("/Parity/overflow"));
  terminal.receive(0x1E);
  assert(terminal.raw() && terminal.receive('7') == '7');
  terminal.receive(0x1F);
  assert(!terminal.raw());
  command(terminal, "help");
  assert(output.find("fsput") != std::string::npos &&
         output.find("uscreen") != std::string::npos);
  command(terminal, "cd /Parity");
  assert(terminal.execute("save named") && files::exists("/Parity/named.m61"));
  assert(!terminal.execute("save named.txt"));
  assert(terminal.execute("save 73") && files::exists("/73.m61"));
  assert(services.load_document("/Parity/named.m61", true));
  assert(terminal.execute("load 73") && !services.active());
  for (unsigned i = 0; i < 1000 && m61_text::active(); ++i) {
    m61_text::service();
    calculator.tick();
  }
  assert(!m61_text::active());
  assert(services.load_document("/Parity/named.m61", true));
  services.input(' ');
  assert(services.dirty() && !terminal.execute("load named.m61") &&
         services.active());
  assert(services.save_document("/Parity/named.m61"));
  assert(terminal.execute("open named.m61") && !services.active());
  for (unsigned i = 0; i < 1000 && m61_text::active(); ++i) {
    m61_text::service();
    calculator.tick();
  }
  assert(!m61_text::active() && files::remove("/73.m61"));
  command(terminal, "cd /");
  // Cancellation/CRC errors never modify the old destination. USB ownership
  // invalidates in-flight uploads even if no local writer ran.
  assert(terminal.execute("fsput begin /Parity/exported.bin 1 0"));
  assert(files::begin_usb());
  files::usb_eject();
  assert(files::end_usb());
  assert(!terminal.execute("fsput data 0 11") &&
         !files::exists("/Parity/exported.bin"));
  // Nested text-font owners restore the previous FMK and geometry exactly.
  std::ifstream input("programs/games/Turochamp/Turochamp.FMK",
                      std::ios::binary);
  assert(input.good());
  const std::vector<u8> font((std::istreambuf_iterator<char>(input)), {});
  assert(files::write("/Parity/face.FMK", font.data(), font.size()));
  assert(program_store_text_font_begin() == 1 &&
         program_store_text_font_load_from("/Parity/face.FMK",
                                           program_store::ROOT_ID) == 1);
  const unsigned cols = script::columns(), rows = script::rows();
  assert(script::font_active());
  assert(program_store_text_font_begin() == 1 &&
         script::text_profile({8, 5, 8, 0}) && !script::font_active());
  assert(program_store_text_font_end() == 1 && script::font_active() &&
         script::columns() == cols && script::rows() == rows);
  assert(program_store_text_font_end() == 1 && !script::font_active());
  Settings settings;
  settings.text_rows = 10;
  settings.text_width = 3;
  settings.text_height = 5;
  u8 page[256];
  encode_settings(settings, 42, page);
  Settings decoded;
  u32 sequence = 0;
  assert(decode_settings(page, decoded, sequence) && sequence == 42 &&
         decoded.text_width == 3 && decoded.text_rows == 10);
  assert(script::text_profile({10, 3, 5, 0}) && script::columns() == 48 &&
         script::rows() == 10);
  assert(script::flow_text("word word word", 14, 0, 2) == 1);
  assert(script::text_profile({8, 5, 8, 0}));
  std::puts("PicoCalc parity: linked Markdown/history, "
            "terminal/editor/history/CP1251/files/CRC/slots/script launch, "
            "nested fonts/settings PASS");
}
