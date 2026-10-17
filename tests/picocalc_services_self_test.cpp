#include "services.hpp"
#include "screen.hpp"
#include "mk61_ref.hpp"
#include "mk8_literal.hpp"
#include "sd_crc.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

void picocalc_host_fail_write(int);
bool picocalc_host_make_exfat();
namespace {
using namespace picocalc;
void type(Services& s, const char* text) { while(*text) assert(s.input((u8)*text++)); }
std::string console(const Services& s) {
    std::string result;
    for(unsigned row = 0; row < Services::ROWS; ++row) { char line[Services::COLS + 1]; s.row(row, line); result += line; result += '\n'; }
    return result;
}
void run(Services& s, Document kind, const char* source) {
    s.new_document(kind); type(s, source); s.input(0x83); s.tick();
    if(s.last_error() != language_vm::Error::NONE) std::fprintf(stderr, "Pico services: %s\n", s.status());
    assert(s.last_error() == language_vm::Error::NONE);
}
}
void picocalc_services_test(const char* preview) {
    using namespace picocalc;
    assert(!files::mount()); // An unformatted card is never formatted on mount.
    assert(sd::crc16((const u8*)"123456789", 9) == 0x31C3);
    u8 blocks[4096], recovered[4096];
    for(unsigned i = 0; i < sizeof(blocks); ++i) blocks[i] = (u8)(i * 17 + i / 255);
    // Compare the fast CRC with an independent bitwise implementation on
    // every prefix, including empty, unaligned and multi-sector lengths.
    u16 crc_reference = 0;
    for(unsigned i = 0; i <= sizeof(blocks); ++i) {
        assert(sd::crc16(blocks, i) == crc_reference);
        if(i == sizeof(blocks)) break;
        crc_reference ^= (u16)blocks[i] << 8;
        for(unsigned bit = 0; bit < 8; ++bit)
            crc_reference = (u16)((crc_reference << 1) ^ ((crc_reference & 0x8000) ? 0x1021 : 0));
    }
    assert(sd::write_bytes(10, 0, blocks, sizeof(blocks)));
    assert(sd::read_bytes(10, 0, recovered, sizeof(recovered)) && std::memcmp(blocks, recovered, sizeof(blocks)) == 0);
    assert(sd::write_bytes(10, 123, blocks, 1500));
    assert(sd::read_bytes(10, 123, recovered, 1500) && std::memcmp(blocks, recovered, 1500) == 0);
    assert(!sd::read_bytes(sd::sectors() - 1, 510, recovered, 4));
    assert(!sd::write_bytes(sd::sectors(), 0, blocks, 1));
    assert(files::format());
    assert(files::mkdir("/Sources"));
    const char* original = "10 PRINT 1\n20 END\n";
    assert(files::write_text("/Sources/test.bas", original, (unsigned)std::strlen(original)));
    const char* replacement = "10 PRINT 2+3\n20 END\n";
    assert(files::write_text("/Sources/test.bas", replacement, (unsigned)std::strlen(replacement)));
    char text[256]; unsigned size;
    assert(files::read_text("/Sources/test.bas", text, sizeof(text), size) && std::strcmp(text, replacement) == 0);
    const char* russian = M8("10 PRINT \"Привет, ёж!\"\n");
    assert(files::write_text("/Sources/пример.bas", russian, (unsigned)std::strlen(russian)));
    assert(files::read_text("/Sources/пример.bas", text, sizeof(text), size) && std::strcmp(text, russian) == 0);
    const char* crlf = "\xEF\xBB\xBF" "A\r\nB\rC\n";
    assert(files::write("/Sources/crlf.txt", (const u8*)crlf, (unsigned)std::strlen(crlf)));
    assert(files::read_text("/Sources/crlf.txt", text, sizeof(text), size) && std::strcmp(text, "A\nB\nC\n") == 0);
    const u8 invalid[] = {0xC0, 0xAF};
    assert(files::write("/Sources/invalid.txt", invalid, sizeof(invalid)));
    assert(!files::read_text("/Sources/invalid.txt", text, sizeof(text), size));
    picocalc_host_fail_write(0);
    assert(!files::write_text("/Sources/test.bas", "replacement", 11));
    assert(files::mount());
    assert(files::read_text("/Sources/test.bas", text, sizeof(text), size) && std::strcmp(text, replacement) == 0);
    files::Entry entries[2]; unsigned used; bool more;
    assert(files::list("/Sources", 0, entries, 2, used, more) && used == 2 && more);
    assert(files::list("/Sources", 2, entries, 2, used, more) && used == 2 && !more);
    assert(files::begin_usb() && files::usb_active());
    assert(!files::read_text("/Sources/test.bas", text, sizeof(text), size));
    assert(!files::write_text("/forbidden.txt", "X", 1) && !files::format());
    assert(!files::end_usb() && files::usb_active());
    files::usb_eject(); assert(files::end_usb() && files::ready());
    assert(files::rename("/Sources/crlf.txt", "/Sources/renamed.txt"));
    assert(files::remove("/Sources/renamed.txt") && !files::exists("/Sources/renamed.txt"));

    Calculator calc; calc.init();
    static Services s;
    s.open(Action::DEVELOPMENT, true, calc);
    assert(std::strcmp(s.page_name(), "DEVELOPMENT") == 0);
    s.new_document(Document::BASIC);
    type(s, "10 PRINT 2+3\n20 END\n");
    assert(s.dirty() && s.source_size() == std::strlen(replacement));
    assert(s.save_document("/Sources/editor.bas") && !s.dirty());
    s.input(0x83); s.tick();
    assert(s.last_error() == language_vm::Error::NONE && console(s).find("5") != std::string::npos);
    s.input(0x1B); s.input('x'); s.input(0x1B);
    assert(std::strcmp(s.page_name(), "CONFIRM") == 0);
    s.input(0x1B); assert(s.dirty());
    assert(s.load_document("/Sources/editor.bas"));
    assert(!s.dirty() && s.source_size() == std::strlen(replacement));
    const unsigned before = s.source_size();
    assert(!s.load_document("/Sources/invalid.txt") && s.source_size() == before);
    assert(files::write_text("/existing.bas", "ORIGINAL", 8));
    s.new_document(Document::BASIC); type(s, replacement); s.input(0x81);
    for(unsigned i = 0; i < 100; ++i) s.input(8);
    type(s, "existing.bas\n");
    assert(std::strcmp(s.page_name(), "CONFIRM") == 0);
    assert(files::read_text("/existing.bas", text, sizeof(text), size) && std::strcmp(text, "ORIGINAL") == 0);
    s.input(0x1B); assert(std::strcmp(s.page_name(), "PROMPT") == 0);
    s.input('\n'); s.input('\n');
    assert(!s.dirty() && files::read_text("/existing.bas", text, sizeof(text), size) && std::strcmp(text, replacement) == 0);

    run(s, Document::FOCAL, "1.10 SET A=2+3; PRINT A,!\n1.20 EXIT\n");
    assert(console(s).find('5') != std::string::npos);
    run(s, Document::BASIC, "10 .X=SQRT(9)+SIN(90)\n20 .R0=42\n30 END\n");
    double number = 0;
    assert(mk61_ref::read({mk61_ref::Kind::X, 0}, number) && number == 4);
    assert(mk61_ref::read({mk61_ref::Kind::R, 0}, number) && number == 42);
    run(s, Document::BASIC, "10 PSET 10,20\n20 PRINT POINT(10,20)\n30 GRAPH X,-1,1,-1,1\n40 END\n");
    assert(s.graphics());
    {
        Screen screen; Ui ui; screen.render(calc.snapshot(), true, &ui, &s);
        unsigned pixels = 0;
        for(unsigned y = 157; y < 270; ++y) for(unsigned x = 0; x < 320; ++x) pixels += screen.pixel(x, y);
        assert(pixels > 100); // Console text, independently of the graphics canvas/header/footer.
    }
    if(preview) {
        Screen screen; Ui ui; screen.render(calc.snapshot(), true, &ui, &s);
        char path[512]; std::snprintf(path, sizeof(path), "%s.services.pbm", preview);
        FILE* file = std::fopen(path, "wb"); assert(file);
        std::fprintf(file, "P4\n320 320\n"); std::fwrite(screen.data(), 1, Screen::BYTES, file); std::fclose(file);
    }
    struct Keys { const char* input; unsigned calls; } keys{"bad\n12\n", 0};
    s.set_pump([](void* raw, u8& key) {
        auto& keys = *(Keys*)raw; ++keys.calls;
        if(*keys.input) { key = (u8)*keys.input++; return true; }
        return false;
    }, &keys);
    run(s, Document::BASIC, "10 INPUT A\n20 .R0=A*2\n30 END\n");
    assert(mk61_ref::read({mk61_ref::Kind::R, 0}, number) && number == 24);
    keys = {"\x1B", 0};
    s.new_document(Document::BASIC); type(s, "10 GOTO 10\n"); s.input(0x83); s.tick();
    assert(s.last_error() == language_vm::Error::STOPPED && keys.calls < 10);
    s.set_pump(nullptr, nullptr);
    run(s, Document::MK61, "hin 0000 0102020A50\n");
    assert(core_61::get_code(core_61::get_ring_address(0)) == 1);
    s.new_document(Document::MK61); type(s, "hin 0000 02ZZ\n"); s.input(0x83); s.tick();
    assert(s.last_error() != language_vm::Error::NONE && core_61::get_code(core_61::get_ring_address(0)) == 0);
    // Exercise exFAT too; this formats only the RAM-backed fixture above.
    assert(picocalc_host_make_exfat() && files::mount());
    assert(files::mkdir("/Исходники"));
    assert(files::write_text("/Исходники/пример.bas", russian, (unsigned)std::strlen(russian)));
    assert(files::read_text("/Исходники/пример.bas", text, sizeof(text), size) && std::strcmp(text, russian) == 0);
    std::puts("PicoCalc FAT/UTF8/USB ownership/editor/BASIC/FOCAL/graphics/INPUT/M61 tests passed");
}
