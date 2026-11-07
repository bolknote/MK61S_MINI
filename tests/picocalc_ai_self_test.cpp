#include "canvas.hpp"
#include "ai_chat.hpp"
#include "input.hpp"
#include "loadable_ai_service.h"
#include "screen.hpp"
#include "mk61_ai_harness.hpp"
#include "mk61_ref.hpp"
#include "script.hpp"
#include "services.hpp"
#include "shared_memory_buffer.hpp"
#include "psram.hpp"
#include "buffers.hpp"
extern "C" {
#include "ff.h"
}
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <iterator>
#include <vector>
#include <map>
#include <array>

namespace {
using namespace picocalc;
using namespace mk61ai;
bool read(void *, const char *path, void *out, unsigned cap, unsigned &n) {
  return files::read(path, static_cast<u8 *>(out), cap, n);
}
bool write(void *, const char *path, const void *data, unsigned n) {
  return files::write(path, static_cast<const u8 *>(data), n);
}
bool exists(void *, const char *path) { return files::exists(path); }
Store store() { return {nullptr, read, write, exists}; }
std::array<u16,320*320> color_pixels{};
unsigned color_frames=0;
u32 color_sink(void *,u32 operation,const void *payload) {
  if(operation==MK61_COLOR_AVAILABLE || operation==MK61_COLOR_END) return 1;
  if(operation!=MK61_COLOR_PRESENT || !payload) return 0;
  const auto &f=*static_cast<const mk61_service_color_frame*>(payload);
  assert((f.format&~MK61_COLOR_PRESERVE_OUTSIDE)==MK61_COLOR_INDEX4 && f.x+f.width<=320 && f.y+f.height<=320);
  const unsigned stride=(f.width+1)/2;
  assert(f.pixel_bytes==stride*f.height);
  for(unsigned y=0;y<f.height;++y)for(unsigned x=0;x<f.width;++x){const u8 byte=f.pixels[y*stride+x/2];color_pixels[(f.y+y)*320+f.x+x]=f.palette[x&1?byte&15:byte>>4];}
  ++color_frames;
  return 1;
}
void snapshot(const char *name) {
  const char *directory = std::getenv("MK61_AI_UI_PREVIEW_DIR");
  if (!directory)
    return;
  std::ofstream out(std::string(directory) + "/" + name + ".pbm",
                    std::ios::binary);
  assert(out);
  out << "P4\n320 320\n";
  for (unsigned y = 0; y < 320; ++y)
    for (unsigned x = 0; x < 320; x += 8) {
      unsigned byte = 0;
      for (unsigned b = 0; b < 8; ++b)
        if (canvas::frame()[y / 8 * 320 + x + b] & (1U << (y % 8)))
          byte |= 0x80U >> b;
      out.put(char(byte));
    }
  if(color_frames) {
    std::ofstream rgb(std::string(directory)+"/"+name+".ppm",std::ios::binary);
    rgb<<"P6\n320 320\n255\n";
    for(const auto p:color_pixels){rgb.put(char(((p>>11)&31)*255/31));rgb.put(char(((p>>5)&63)*255/63));rgb.put(char((p&31)*255/31));}
  }
}
struct Input {
  unsigned stage = 0, at = 0, calls = 0;
  u32 id = 0;
  core_61::ContextBuffer original{};
  std::string keys = "\r\r\x88"
                     "X = R0 + R1.\r\t\xB6\rR0=7 R1=5 => X=12 ANGLE=DEG "
                     "STEPS=73 FRAMES=900\r\x83" "60 61 10 50\r";
  bool current(Session &s) {
    if (!id) {
      files::Entry entry[1];
      unsigned n = 0;
      bool more = false;
      if (!files::list("/AI/SESSIONS", 0, entry, 1, n, more, ".AIS") || !n)
        return false;
      id = u32(std::strtoul(entry[0].name, nullptr, 10));
    }
    return id && load_session(store(), id, s);
  }
  void next(const std::string &value) {
    keys = value;
    at = 0;
    ++stage;
  }
  static bool pump(void *raw, u8 &key) {
    auto &p = *static_cast<Input *>(raw);
    if (++p.calls == 10000) {
      Session s;
      p.current(s);
      std::fprintf(stderr,
                   "AI UI stalled: stage=%u at=%u/%zu id=%lu version=%lu "
                   "tests=%u state=%u form=%u task=%s\n",
                   p.stage, p.at, p.keys.size(), (unsigned long)p.id,
                   (unsigned long)s.program.version, unsigned(s.test_count),
                   unsigned(s.state), unsigned(s.form_kind), s.task);
      snapshot("stalled");
      std::abort();
    }
    if (p.at == p.keys.size()) {
      Session s;
      if (p.stage == 0) {
        if (!p.current(s) || s.program.version != 1 || s.test_count != 1)
          return false;
        assert(!std::strcmp(s.task, "X = R0 + R1."));
        p.next("\t\xB6\xB6\r");
      } else if (p.stage == 1) {
        if (!p.current(s) || s.state != RunState::FINISHED || !all_passed(s))
          return false;
        core_61::ContextBuffer now;
        assert(core_61::save_context(now));
        assert(!std::memcmp(now.bytes, p.original.bytes, sizeof(now.bytes)));
        snapshot("tests");
        p.next(std::string("\t")+std::string(15,char(0xb6))+"\r\r\r");
      } else if (p.stage == 2) {
        if (!p.current(s) || s.tests[0].revision < 2)
          return false;
        assert(!all_passed(s) && s.tests[0].angle == 0 &&
               s.tests[0].max_commands == 73 && s.tests[0].max_frames == 900);
        p.next(std::string("\t") + std::string(7, char(0xB6)) + "\r");
      } else if (p.stage == 3) {
        double value = 0;
        assert(mk61_ref::read({mk61_ref::Kind::R, 0}, value) && value == 7);
        assert(MK61Emu_GetAngleUnit() == DEGREE);
        p.next(std::string("\x82\t") + std::string(6, char(0xB6)) + "\r\r");
      } else if (p.stage == 4) {
        double value = 0;
        assert(mk61_ref::read({mk61_ref::Kind::R, 9}, value) &&
               value == 123.25);
        assert(mk61_ref::read({mk61_ref::Kind::X, 0}, value) && value == -3.25);
        u8 byte = 0;
        assert(core_61::read_absolute_program(0, byte) && byte == 0x60);
        files::Entry entries[8];
        unsigned n = 0;
        bool more = false;
        assert(files::list("/AI/SESSIONS", 0, entries, 8, n, more, ".bin") &&
               n == 1);
        char path[256];
        std::snprintf(path, sizeof(path), "/AI/SESSIONS/%s", entries[0].name);
        u8 previous[105];
        unsigned used = 0;
        assert(files::read(path, previous, sizeof(previous), used) &&
               used == 105 && previous[0] == 9);
        snapshot("code");
        p.next("\x1B\x1B");
      } else
        return false;
    }
    key = u8(p.keys[p.at++]);
    controls::event({1, key});
    controls::event({3, key});
    return false;
  }
};
struct PauseInput {
  std::string keys = "\xB6\xB6\xB6\xB6\r\t\xB6\xB6\r";
  unsigned at = 0, stage = 0, calls = 0;
  static bool pump(void *raw, u8 &key) {
    auto &p = *static_cast<PauseInput *>(raw);
    assert(++p.calls < 12000);
    if (p.at == p.keys.size()) {
      Session saved;
      if (!load_session(store(), 100, saved))
        return false;
      if (p.stage == 0) {
        if (saved.state != RunState::PAUSED)
          return false;
        p.keys = std::string("\x1B\t") + std::string(9, char(0xB6)) +
                 "\r\x1B\t" + std::string(10, char(0xB6)) + "\r\x1B\x85";
        p.at = 0;
        p.stage = 1;
      } else if (p.stage == 1) {
        if (!all_passed(saved))
          return false;
        p.keys = "\x1B\x1B";
        p.at = 0;
        p.stage = 2;
      } else
        return false;
    }
    key = u8(p.keys[p.at++]);
    controls::event({1, key});
    controls::event({3, key});
    return false;
  }
};
struct SineInput {
  std::string keys = std::string(4, char(0xb6)) + "\r\t\xB6\xB6\r";
  unsigned at = 0, stage = 0, calls = 0, ready = 0;
  std::array<u16,320*320> collapsed{};
  static bool pump(void *raw, u8 &key) {
    auto &p = *static_cast<SineInput *>(raw);
    assert(++p.calls < 12000);
    if (p.at == p.keys.size()) {
      if (p.stage == 0) {
        Session saved;
        picocalc::ai::chat::History history;
        if (!load_session(store(), 150, saved) ||
            saved.state == RunState::RUNNING || !history.sync(store(), saved) ||
            !history.count() || !history[history.count()-1].has_result) return false;
        const auto &t = history[history.count()-1];
        assert(t.result.status == Execution::STOPPED && t.result.commands == 4 &&
               t.result.x == 0.3746066 && t.angle == 0 &&
               t.telemetry.measured && t.telemetry.output == 0);
        if (++p.ready < 2) return false; // Let the production UI present the result.
        snapshot("sine"); p.collapsed = color_pixels;
        p.keys = "\x87";
      } else if (p.stage == 1) {
        if (color_pixels == p.collapsed) return false;
        snapshot("sine-metrics");
        p.collapsed = color_pixels;
        p.keys = "\x87\x81";
      } else if (p.stage == 2) {
        if (color_pixels == p.collapsed) return false;
        snapshot("sine-code"); p.keys = "\x1b\x1b";
      } else return false;
      ++p.stage; p.at = 0;
    }
    key = u8(p.keys[p.at++]);
    controls::event({1,key}); controls::event({3,key});
    return false;
  }
};
void launch(void *, const mk61_app_api &api, const mk61_app_services &common) {
  assert(api.query_service(MK61_APP_SERVICE_COMMON,
                           MK61_APP_SERVICES_VERSION) == &common);
  assert(!api.query_service(MK61_APP_SERVICE_AI, 0));
  const auto *ai = static_cast<const mk61_ai_service *>(
      api.query_service(MK61_APP_SERVICE_AI, MK61_AI_SERVICE_VERSION));
  assert(ai && ai->magic == MK61_AI_SERVICE_MAGIC &&
         ai->struct_size == sizeof(*ai) && ai->run);
  const auto *diagnostic = static_cast<const mk61_ai_diagnostic_service *>(
      api.query_service(MK61_APP_SERVICE_AI, MK61_AI_DIAGNOSTIC_VERSION));
  assert(diagnostic && diagnostic->magic == MK61_AI_SERVICE_MAGIC &&
         diagnostic->version == MK61_AI_DIAGNOSTIC_VERSION &&
         diagnostic->struct_size == sizeof(*diagnostic) && diagnostic->benchmark);
  assert(diagnostic->benchmark(nullptr) == 1 &&
         diagnostic->benchmark("/AI/../other") == 1 &&
         diagnostic->benchmark("/AI/") == 1);
  assert(ai->run(MK61_SERVICE_INVALID_ID) == 0);
}
void launch_benchmark(void *, const mk61_app_api &api, const mk61_app_services &) {
  const auto *diagnostic = static_cast<const mk61_ai_diagnostic_service *>(
      api.query_service(MK61_APP_SERVICE_AI, MK61_AI_DIAGNOSTIC_VERSION));
  assert(diagnostic && diagnostic->benchmark("/AI/HOSTBENCH") == 0);
}
void launch_cancelled_benchmark(void *,const mk61_app_api &api,const mk61_app_services &) {
  const auto *s=static_cast<const mk61_ai_diagnostic_service*>(api.query_service(MK61_APP_SERVICE_AI,MK61_AI_DIAGNOSTIC_VERSION));
  assert(s && s->benchmark("/AI/HOSTBENCH")==3);
}
struct FrozenInput {
  Services *services;Calculator *calculator;Screen screen;
  FrozenInput(Services& s,Calculator& c):services(&s),calculator(&c) {}
  std::string keys;unsigned at=0,stage=0,frozen_calls=0,calls=0;
  bool benchmark=false;
  bool metrics_toggled=false;
  static bool pump(void *raw,u8 &key) {
    auto &p=*static_cast<FrozenInput*>(raw);assert(++p.calls<40000);
    auto emit=[&](u8 code) { key=code;controls::event({1,code});controls::event({3,code}); };
    if(p.at<p.keys.size()) { emit(u8(p.keys[p.at++]));return false; }
    const bool held=p.services->display_deferred();
    if(held) {
      const auto renders=p.screen.renders();
      assert(!p.screen.render(p.calculator->snapshot(),true,nullptr,p.services) && p.screen.renders()==renders);
    }
    if(p.benchmark) {
      if(p.stage==0 && held && ++p.frozen_calls>=20) { p.stage=1;emit(0x1b); }
      return false;
    }
    if(p.stage==0 && held && !p.metrics_toggled) {
      p.metrics_toggled=true;emit(0x87);return false;
    }
    if((p.stage==0 || p.stage==2) && held && ++p.frozen_calls>=20) {
      emit(p.stage==0?0x85:0x1b);++p.stage;p.frozen_calls=0;return false;
    }
    if((p.stage==1 || p.stage==3) && !held) {
      Session saved;
      if(!load_session(store(),200,saved) || saved.state!=RunState::PAUSED) return false;
      if(p.stage==1) { ++p.stage;emit(0x85); }
      else { ++p.stage;p.keys="\x1b\x1b";p.at=0; }
    }
    return false;
  }
};
} // namespace
void picocalc_ai_test() {
  using namespace picocalc;
  extern void picocalc_ai_chat_test();
  picocalc_ai_chat_test();
  controls::clear();
  Calculator calc;
  calc.init(true);
  core_61::set_expanded_program_mode(false);
  assert(core_61::write_absolute_program(0, 9) &&
         core_61::write_absolute_program(1, 0x50));
  assert(mk61_ref::write({mk61_ref::Kind::R, 9}, 123.25));
  assert(mk61_ref::write({mk61_ref::Kind::X, 0}, -3.25));
  MK61Emu_SetAngleUnit(GRADE);
  Services services;
  services.set_color_display(color_sink,nullptr);
  script::attach(calc, services);
  Input input;
  assert(core_61::save_context(input.original));
  const auto buffers = shared_memory::buffer_statistics().active;
  services.set_pump(Input::pump, &input);
  services.test_native_contract(launch, nullptr, true);
  assert(input.stage == 5 && input.at == input.keys.size());
  assert(shared_memory::buffer_statistics().active == buffers);
  // A second real APP host opens the saved session from its home screen.
  const char *keys = "\xB6\xB6\xB6\xB6\r\x82\x1B\x1B\x1B";
  services.set_pump(
      [](void *raw, u8 &key) {
        auto &p = *static_cast<const char **>(raw);
        if (!*p)
          return false;
        key = u8(*p++);
        controls::event({1, key});
        controls::event({3, key});
        return false;
      },
      &keys);
  services.test_native_contract(launch, nullptr, true);
  assert(!*keys);
  services.set_pump(nullptr, nullptr);
  Session saved;
  assert(load_session(store(), input.id, saved) && saved.program.version == 1 &&
         saved.tests[0].revision == 2);
  // Manual tools can pause and resume without a model file. Opening both
  // log and settings must preserve the paused test continuation.
  Session paused;
  paused.id = 100;
  assert(set_task(paused, "Проверить сложение.", false));
  Example e;
  assert(parse_example("R0=7 R1=5 => X=12", e) && set_example(paused, 0, e));
  const u8 sum[] = {0x60, 0x61, 0x10, 0x50};
  assert(accept_program(store(), paused, sum, 4));
  PauseInput pause;
  services.set_pump(PauseInput::pump, &pause);
  services.test_native_contract(launch, nullptr, true);
  services.set_pump(nullptr, nullptr);
  assert(pause.stage == 2 && pause.at == pause.keys.size() &&
         load_session(store(), 100, paused) && all_passed(paused));
  // Exercise the actual single-window UI with a manual program: the displayed
  // sine is obtained through Agent -> local_executor -> the production MK-61 ROM.
  Session sine; sine.id = 150;
  const u8 sine_code[] = {0x02,0x02,0x1c,0x50};
  assert(set_task(sine, "Посчитай синус 22.", false) &&
         append_event(store(),sine,"USER",sine.task) &&
         accept_program(store(),sine,sine_code,4) && save_session(store(),sine));
  const auto previous_angle = MK61Emu_GetAngleUnit();
  MK61Emu_SetAngleUnit(DEGREE);
  core_61::ContextBuffer before_sine{}, after_sine{};
  assert(core_61::save_context(before_sine));
  SineInput sine_input;
  services.set_pump(SineInput::pump,&sine_input);
  services.test_native_contract(launch,nullptr,true);
  services.set_pump(nullptr,nullptr);
  assert(sine_input.stage == 3 && sine_input.at == sine_input.keys.size());
  assert(core_61::save_context(after_sine) &&
         !std::memcmp(before_sine.bytes,after_sine.bytes,sizeof(before_sine.bytes)));
  MK61Emu_SetAngleUnit(previous_angle);
  std::puts("Native dark chat: journal paging, real core sine, zero fabricated model tokens, F1/F7 expansion and calculator isolation PASS");
  if (const char *package_path = std::getenv("MK61_AI_UI_MODEL_PACKAGE")) {
    // Host-only RAM/FatFs fixture seeding, not a product write path: the
    // device installer uses an ordinary SD/USB copy for this 2-MB asset.
    std::ifstream file(package_path, std::ios::binary);
    std::vector<u8> package((std::istreambuf_iterator<char>(file)), {});
    assert(!package.empty());
    FIL raw;
    UINT written = 0;
    assert(f_open(&raw, "/AI/MODEL.MKA", FA_WRITE | FA_CREATE_ALWAYS) == FR_OK &&
           f_write(&raw, package.data(), unsigned(package.size()), &written) == FR_OK &&
           written == package.size() && f_close(&raw) == FR_OK);
    static std::vector<u8> psram_fixture(8U * 1024 * 1024);
    psram::test_memory(psram_fixture.data(), unsigned(psram_fixture.size()));
    assert(psram::init() && buffers::init());
    services.test_native_contract(launch_benchmark, nullptr, true);
    char report[1536];unsigned n = 0;
    assert(files::read_text("/AI/HOSTBENCH/BENCH.JSON", report, sizeof(report)-1, n));
    report[n] = 0;
    assert(std::strstr(report, "\"max_session_roundtrip\":true") &&
           std::strstr(report, "\"matching_greedy_tokens\":true") &&
           std::strstr(report, "\"valid_tool_prefix\":true") &&
           std::strstr(report, "\"model_load_us\":") &&
           !files::exists("/AI/HOSTBENCH/BENCH.STATE"));
    std::puts("Native diagnostic service: real model, all36 steps, worst-session transaction/codec and cleanup PASS (host, not device speed)");
    for(unsigned variant=0;variant<3;++variant) {
      const bool filtered=variant==1,prefetch=variant==2;
      char config[256];
      const int size=std::snprintf(config,sizeof(config),"AIPERF%u\nkernel=2\narithmetic=3\ncores=2\nfreeze=1\nfilter=%u\nmhz=125\nprefill=2\ndecode=2\nrepeat=2\nstress_ms=20\ncontrol=%u\nconstrained=%u\n%s",prefetch?2:1,filtered?1:0,prefetch?1:0,filtered?1:0,prefetch?"prefetch=1\n":"");
      assert(size>0 && unsigned(size)<sizeof(config) && files::write_text("/AI/HOSTBENCH/PERF.CFG",config,unsigned(size)));
      services.test_native_contract(launch_benchmark,nullptr,true);
      char result[8192];unsigned used=0;
      assert(files::read_text("/AI/HOSTBENCH/PERF.JSON",result,sizeof(result)-1,used));result[used]=0;
      assert(std::strstr(result,"\"schema\":3") && std::strstr(result,"\"ok\":true") &&
             std::strstr(result,"\"matching_checksums\":true") && std::strstr(result,"\"matching_tokens\":true") &&
             std::strstr(result,"\"clocks_restored\":true") && std::strstr(result,"\"freeze_violations\":0") &&
             std::strstr(result,prefetch?"\"freeze_count\":13":"\"freeze_count\":9") &&
             std::strstr(result,prefetch?"\"thaw_count\":13":"\"thaw_count\":9"));
      if(prefetch) {
        assert(std::strstr(result,"\"prefetch\":1"));
        const char *at=result;
        for(unsigned pass=0;pass<3;++pass) {
          at=std::strstr(at,"\"prefetches\":");assert(at);at+=13;
          assert(pass?std::strtoul(at,nullptr,10)>0:std::strtoul(at,nullptr,10)==0);
        }
      }
    }
    assert(files::remove("/AI/HOSTBENCH/PERF.CFG"));
    std::puts("Native performance service: frame freeze/thaw, full-model checksums, constrained sparse head, owned PSRAM stress and clock guard PASS (host only)");
    const char cancel_config[]="AIPERF1\nkernel=2\narithmetic=3\ncores=2\nfreeze=1\nfilter=0\nmhz=125\nprefill=2\ndecode=2\nrepeat=1\nstress_ms=0\ncontrol=0\nconstrained=0\n";
    assert(files::write_text("/AI/HOSTBENCH/PERF.CFG",cancel_config,sizeof(cancel_config)-1));
    FrozenInput cancellation{services,calc};cancellation.benchmark=true;
    services.set_pump(FrozenInput::pump,&cancellation);
    services.test_native_contract(launch_cancelled_benchmark,nullptr,true);
    services.set_pump(nullptr,nullptr);
    char cancelled[8192];unsigned cancelled_size=0;
    assert(cancellation.stage==1 && !services.display_deferred() &&
           files::read_text("/AI/HOSTBENCH/PERF.JSON",cancelled,sizeof(cancelled)-1,cancelled_size));
    cancelled[cancelled_size]=0;
    assert(std::strstr(cancelled,"\"cancelled\":true") && std::strstr(cancelled,"\"model_status\":6") &&
           std::strstr(cancelled,"\"freeze_violations\":0"));
    assert(files::remove("/AI/HOSTBENCH/PERF.CFG"));
    Session task;task.id=200;Example example;
    assert(set_task(task,"X = R0 + R1.",false) && parse_example("R0=7 R1=5 => X=12",example) &&
           set_example(task,0,example) && save_session(store(),task));
    FrozenInput pause_resume{services,calc};pause_resume.keys=std::string(4,char(0xb6))+"\r\x85";
    services.set_pump(FrozenInput::pump,&pause_resume);
    services.test_native_contract(launch,nullptr,true);
    services.set_pump(nullptr,nullptr);
    assert(pause_resume.stage==4 && !services.display_deferred());
    std::puts("Native frozen display: global raster held, Esc interrupts forward, F5 pauses/resumes real model, exit thaws PASS (host)");
  }
  std::puts("PicoCalc native AI UI: real APP service, keyboard/forms, emulator "
            "tests, case edit invalidation, input angle, apply backup and "
            "session resume PASS");
}
