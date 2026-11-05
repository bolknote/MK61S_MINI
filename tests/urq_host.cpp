#include "../code/urq/engine.hpp"
#include "../code/mk8_codec.hpp"
#include "../code/ecma_number.hpp"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <map>
#include <string>
#include <vector>

namespace {
struct Files {
  std::string directory;
  std::map<unsigned, std::vector<uint8_t>> files;
  const std::vector<uint8_t>& get(unsigned id) {
    auto found = files.find(id);
    if(found != files.end()) return found->second;
    char name[32]; std::snprintf(name, sizeof(name), "p%04u.uqd", id ? id - 1 : 0);
    std::ifstream file(directory + "/" + (id ? name : "game.urq"), std::ios::binary);
    return files[id] = std::vector<uint8_t>(std::istreambuf_iterator<char>(file), {});
  }
  static bool read(void* p, uint16_t id, uint32_t offset, uint8_t* out, uint32_t n) {
    const auto& file = static_cast<Files*>(p)->get(id);
    if(offset > file.size() || n > file.size() - offset) return false;
    std::memcpy(out, file.data() + offset, n); return true;
  }
  static uint32_t size(void* p, uint16_t id) { return uint32_t(static_cast<Files*>(p)->get(id).size()); }
};
std::string json(const char* text) {
  std::string out = "\"";
  while(*text) {
    const unsigned c = uint8_t(*text++);
    if(c == '"' || c == '\\') { out += '\\'; out += char(c); }
    else if(c < 32 || c >= 128) {
      const unsigned cp = mk8::codepoint(uint8_t(c));
      char buffer[8]; std::snprintf(buffer, sizeof(buffer), "\\u%04x", cp); out += buffer;
    } else out += char(c);
  }
  return out + "\"";
}
std::string m8(const char* utf8) {
  std::string result;
  while(*utf8) {
    unsigned cp = uint8_t(*utf8++);
    if(cp >= 0xC0) {
      const unsigned first = cp; cp &= first < 0xE0 ? 31U : 15U;
      const unsigned count = first < 0xE0 ? 1U : 2U;
      for(unsigned i = 0; i < count && *utf8; ++i) cp = (cp << 6) | (uint8_t(*utf8++) & 63U);
    }
    uint8_t byte = 0;
    if(!mk8::from_codepoint(cp, byte)) throw std::runtime_error("Input is not M8");
    result += char(byte);
  }
  return result;
}
void print(void*, const char* text, bool newline) {
  std::cout << "{\"event\":\"text\",\"text\":" << json(text)
            << ",\"newline\":" << (newline ? "true" : "false") << "}\n";
}
void clear(void*, bool text, bool actions) {
  std::cout << "{\"event\":\"clear\",\"text\":" << (text ? "true" : "false")
            << ",\"actions\":" << (actions ? "true" : "false") << "}\n";
}
void number(void*, double value, bool fixed, char* out, uint16_t capacity) {
  if(fixed) ecma_number::fractional(value,out,capacity);else ecma_number::format(value,out,capacity);
}
bool save(void*) { return true; }
void dump(urq::Engine& engine) {
  const auto& s = engine.state();
  std::cout << "{\"event\":\"state\",\"status\":" << unsigned(s.status)
            << ",\"error\":" << unsigned(s.error) << ",\"pc\":" << s.pc << ",\"vars\":{";
  bool first = true;
  for(unsigned i = 0; i < s.variables; ++i) if(s.names[i]) {
    if(!first) std::cout << ',';
    first = false;
    std::cout << json(engine.text(s.names[i])) << ':';
    if(s.types[i] == 1) std::cout << json(engine.text(s.strings[i]));
    else if(s.types[i] == 2) std::cout << (s.numbers[i] ? "true" : "false");
    else if(std::isfinite(s.numbers[i])) std::cout << s.numbers[i];
    else std::cout << "null";
  }
  std::cout << "},\"items\":{"; first = true;
  for(unsigned i = 0; i < urq::ITEMS; ++i) if(s.items[i]) {
    if(!first) std::cout << ',';
    first = false;
    std::cout << json(engine.text(s.items[i])) << ':' << s.quantities[i];
  }
  std::cout << "},\"actions\":["; first = true;
  for(unsigned i = 0; i < s.action_count; ++i) if(s.actions[i].live) {
    if(!first) std::cout << ',';
    first = false; const auto& a = s.actions[i];
    std::cout << "{\"id\":" << a.id << ",\"command\":" << json(engine.text(a.command))
              << ",\"caption\":" << json(engine.text(a.caption)) << "}";
  }
  std::cout << "]}\n" << std::flush;
}
}
int main(int argc, char** argv) {
  std::cout << std::setprecision(17);
  if(argc < 2) return 2;
  Files files{argv[1], {}}; urq::Pack pack; uint8_t cache[urq::PAGE_BYTES];
  if(!pack.open({&files, Files::read, Files::size, cache})) {
    std::cout << "{\"event\":\"pack_error\",\"error\":" << unsigned(pack.error()) << "}\n"; return 3;
  }
  urq::State state{}; urq::Engine engine;
  urq::Host host; host.print = print; host.clear = clear; host.save = save;
  struct Resources { urq::Engine* engine;urq::Pack* pack; } resources{&engine,&pack};
  host.context=&resources;
  host.deferred_save=std::getenv("URQ_HOST_DEFER_SAVE")!=nullptr;
  host.resource=[](void* raw,bool url,const char* path) {
    auto& r=*(Resources*)raw;char content[urq::LINE_BYTES];
    return r.pack->resource(path,content,sizeof(content),url) && r.engine->set(url?"file_url":"file_content",{0,content,1});
  };
  host.number = number; host.clock = [](void*, bool days) { return days ? 20000U : 43210U; };
  host.parse = [](void*, const char* text, double& value) {
    return ecma_number::parse(text,value);
  };
  host.power = [](void*, double a, double b) { return std::pow(a, b); };
  engine.attach(pack, state, host);
  if(!engine.start()) { dump(engine); return 4; }
  auto run = [&]() {
    unsigned budget = 100;
    while(engine.run() == urq::Status::RUNNING && --budget) {}
    dump(engine);
  };
  run();
  auto execute = [&](const std::string& argument) {
    bool ok = true;
    if(argument.rfind("c:", 0) == 0) ok = engine.choose(uint16_t(std::stoul(argument.substr(2))));
    else if(argument.rfind("i:", 0) == 0) ok = engine.submit(m8(argument.c_str() + 2).c_str());
    else if(argument.rfind("k:", 0) == 0) ok = engine.resume(uint32_t(std::stoul(argument.substr(2))));
    else if(argument.rfind("t:", 0) == 0) engine.tick(uint32_t(std::stoul(argument.substr(2))));
    else if(argument.rfind("u:", 0) == 0) ok = engine.use(m8(argument.c_str() + 2).c_str());
    else if(argument.rfind("f:",0)==0) engine.finish_save(argument.substr(2)=="1");
    else if(argument.rfind("s:", 0) == 0) {
      std::ofstream file(argument.substr(2), std::ios::binary);
      ok = engine.snapshot({&file, [](void* p, const uint8_t* data, uint32_t n) {
        auto& f = *static_cast<std::ofstream*>(p);
        f.write(reinterpret_cast<const char*>(data), n); return bool(f);
      }});
    } else if(argument.rfind("l:", 0) == 0) {
      std::ifstream file(argument.substr(2), std::ios::binary);
      std::vector<uint8_t> bytes(std::istreambuf_iterator<char>(file), {});
      ok = engine.restore({&bytes, [](void* p, uint32_t offset, uint8_t* out, uint32_t n) {
        const auto& v = *static_cast<std::vector<uint8_t>*>(p);
        if(offset > v.size() || n > v.size() - offset) return false;
        std::memcpy(out, v.data() + offset, n); return true;
      }, uint32_t(bytes.size())});
    } else return false;
    if(!ok) std::cout << "{\"event\":\"command_failed\"}\n";
    run();
    return true;
  };
  for(int i = 2; i < argc; ++i) {
    if(std::strcmp(argv[i], "-") == 0) {
      std::string argument;
      while(std::getline(std::cin, argument)) if(!execute(argument)) return 2;
    } else if(!execute(argv[i])) return 2;
  }
  return state.status == urq::Status::ERROR ? 5 : 0;
}
