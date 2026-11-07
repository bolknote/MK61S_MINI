#include "mk61_ai_agent.hpp"
#include "mk61emu_core.h"
#include <cassert>
#include <cstdlib>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <vector>
namespace {
using namespace mk61ai;
struct Disk {
  std::map<std::string, std::vector<std::uint8_t>> files;
  static bool read(void *p, const char *path, void *out, unsigned cap,
                   unsigned &n) {
    auto &d = *static_cast<Disk *>(p);
    auto at = d.files.find(path);
    if (at == d.files.end() || at->second.size() > cap)
      return false;
    n = unsigned(at->second.size());
    std::memcpy(out, at->second.data(), n);
    return true;
  }
  static bool write(void *p, const char *path, const void *bytes, unsigned n) {
    auto *b = static_cast<const std::uint8_t *>(bytes);
    static_cast<Disk *>(p)->files[path] = {b, b + n};
    return true;
  }
  static bool exists(void *p, const char *path) {
    return static_cast<Disk *>(p)->files.count(path);
  }
  Store store() { return {this, read, write, exists}; }
};
bool read_memory(void *p, std::uint32_t at, void *out, unsigned n) {
  auto &b = *static_cast<std::vector<std::uint8_t> *>(p);
  if (at > b.size() || n > b.size() - at)
    return false;
  std::memcpy(out, b.data() + at, n);
  return true;
}
bool write_memory(void *p, std::uint32_t at, const void *in, unsigned n) {
  auto &b = *static_cast<std::vector<std::uint8_t> *>(p);
  if (at > b.size() || n > b.size() - at)
    return false;
  std::memcpy(b.data() + at, in, n);
  return true;
}
std::string escaped(const char *s) {
  std::string out = "\"";
  for (; *s; ++s) {
    const auto c = static_cast<unsigned char>(*s);
    if (c == '\n')
      out += "\\n";
    else if (c == '\r')
      out += "\\r";
    else if (c == '\t')
      out += "\\t";
    else {
      if (c == '"' || c == '\\')
        out += '\\';
      if (c >= 32)
        out += *s;
    }
  }
  return out + '"';
}
std::uint32_t micros(void *) {
  return std::uint32_t(std::chrono::duration_cast<std::chrono::microseconds>(
                           std::chrono::steady_clock::now().time_since_epoch())
                           .count());
}
} // namespace
int main(int argc, char **argv) {
  if (argc < 3 || argc > 8) {
    std::cerr << "MODEL.MKA cases.tsv [prefix.txt] [--no-plan] [--arithmetic=lut-int8] [--linear=sram] [--filter-head]\n";
    return 2;
  }
  std::ifstream file(argv[1], std::ios::binary), tasks(argv[2]);
  if (!file || !tasks)
    return 2;
  std::vector<std::uint8_t> package((std::istreambuf_iterator<char>(file)), {}),
      cache;
  Model model;
  if (model.open({&package, unsigned(package.size()), read_memory, nullptr}) !=
      ModelStatus::OK)
    return 3;
  cache.resize(model.cache_bytes());
  std::vector<std::uint64_t> work((model.workspace_bytes() + 7) / 8);
  if (model.bind(work.data(), work.size() * 8,
                 {&cache, unsigned(cache.size()), read_memory, write_memory}) !=
      ModelStatus::OK)
    return 3;
  std::string prefix;
  bool planning = true, custom_prefix = false;
  Arithmetic arithmetic = Arithmetic::LUT_FLOAT32;
  const char *arithmetic_name = "lut-fp32";
  ComputeExecution execution{};
  for (int i = 3; i < argc; ++i) {
    if (std::string(argv[i]) == "--no-plan")
      planning = false;
    else if (std::string(argv[i]) == "--filter-head")
      execution.filter_head = true;
    else if (std::strncmp(argv[i], "--linear=", 9) == 0) {
      const char *name=argv[i]+9;
      if(!std::strcmp(name,"reference")) execution.kernel=LinearKernel::REFERENCE;
      else if(!std::strcmp(name,"flash")) execution.kernel=LinearKernel::FLASH;
      else if(!std::strcmp(name,"sram")) execution.kernel=LinearKernel::SRAM;
      else return 2;
    }
    else if (std::strncmp(argv[i], "--arithmetic=", 13) == 0) {
      arithmetic_name = argv[i] + 13;
      if (!std::strcmp(arithmetic_name, "lut-int8")) arithmetic = Arithmetic::LUT_INT8;
      else if (!std::strcmp(arithmetic_name, "int8")) arithmetic = Arithmetic::INT8;
      else if (!std::strcmp(arithmetic_name, "fp32")) arithmetic = Arithmetic::FLOAT32;
      else if (!std::strcmp(arithmetic_name, "lut-fp32")) arithmetic = Arithmetic::LUT_FLOAT32;
      else return 2;
    }
    else {
      std::ifstream p(argv[i]);
      if (!p || custom_prefix)
        return 2;
      prefix.assign(std::istreambuf_iterator<char>(p), {});
      custom_prefix = true;
    }
  }
  model.execution(execution);
  core_61::set_expanded_program_mode(false);
  core_61::enable();
  std::string line;
  unsigned number = 0;
  while (std::getline(tasks, line)) {
    if (line.empty())
      continue;
    std::vector<std::string> columns;
    unsigned from = 0;
    for (unsigned i = 0; i <= line.size(); ++i)
      if (i == line.size() || line[i] == '\t') {
        columns.push_back(line.substr(from, i - from));
        from = i + 1;
      }
    if (columns.size() < 4 || columns.size() > 11)
      return 2;
    Session s;
    s.id = ++number;
    s.planning = planning;
    Disk disk;
    if (!set_task(s, columns[1].c_str(), false))
      return 2;
    if (!columns[2].empty()) {
      Reply parsed;
      const auto message = "<write>" + columns[2] + "</write><run/>";
      if (!parse_reply(message.c_str(), parsed) ||
          !accept_program(disk.store(), s, parsed.program, parsed.size))
        return 2;
      s.intent = Intent::FIX;
    }
    for (unsigned i = 3; i < columns.size(); ++i) {
      Example e;
      if (!parse_example(columns[i].c_str(), e) || !set_example(s, i - 3, e))
        return 2;
    }
    Agent agent(s, disk.store(), model);
    agent.arithmetic(arithmetic);
    agent.clock(micros, nullptr);
    const auto started = micros(nullptr);
    if (std::getenv("MK61_QUALITY_ORACLE")) { agent.run_tests(); }
    else
    agent.start(custom_prefix ? prefix.c_str() : nullptr);
    unsigned ticks = 0;
    while (agent.active() && ticks++ < 12000)
      agent.tick();
    if (agent.active()) {
      std::cerr << "Unbounded controller: " << columns[0] << '\n';
      return 4;
    }
    unsigned valid = 0, total = 0;
    for (const auto &item : disk.files) {
      const auto &bytes = item.second;
      const std::string text(bytes.begin(), bytes.end());
      if (text.rfind("MODEL\n", 0) != 0)
        continue;
      ++total;
      const auto body = text.find('\n', 6);
      Reply parsed;
      if (body != std::string::npos &&
          parse_reply(text.c_str() + body + 1, parsed) &&
          (parsed.write || parsed.patch || parsed.run || parsed.trace ||
           parsed.done || parsed.question[0]))
        ++valid;
    }
    std::string code;
    char byte[3];
    for (unsigned i = 0; i < s.program.size; ++i) {
      std::snprintf(byte, sizeof(byte), "%02X", s.program.bytes[i]);
      code += byte;
    }
    const auto &m = agent.metrics();
    std::cout << "{\"id\":" << escaped(columns[0].c_str())
              << ",\"passed\":" << (all_passed(s) ? "true" : "false")
              << ",\"state\":" << unsigned(s.state)
              << ",\"arithmetic\":" << escaped(arithmetic_name)
              << ",\"attempts\":" << s.attempts
              << ",\"passed_tests\":" << passed_examples(s)
              << ",\"tests\":" << unsigned(s.test_count)
              << ",\"valid_replies\":" << valid << ",\"replies\":" << total
              << ",\"prompt_tokens\":" << agent.prompt_size()
              << ",\"generation_limit\":" << agent.generation_limit()
              << ",\"prefill_tokens\":" << m.prefill_tokens
              << ",\"decode_tokens\":" << m.decode_tokens
              << ",\"reused_tokens\":" << m.reused_tokens
              << ",\"elapsed_us\":" << micros(nullptr) - started
              << ",\"code\":" << escaped(code.c_str())
              << ",\"feedback\":" << escaped(s.feedback)
              << ",\"reply\":" << escaped(s.reply) << "}\n"
              << std::flush;
    std::cerr << columns[0] << ": " << passed_examples(s) << '/'
              << unsigned(s.test_count) << " attempts=" << s.attempts << "\n";
  }
}
