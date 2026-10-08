// Frozen reference scripts come from 4ffe156a; no Git history is needed to run this test.
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include "language_bytecode.hpp"
#include "mk_math.hpp"
using namespace language_vm;
struct Program {
  std::vector<uint8_t> image;
  std::vector<uint8_t> owned_image;
  View view{};
  View owned_view{};
  explicit Program(const char* path) : image(MAX_IMAGE) {
    std::ifstream file(path, std::ios::binary);
    assert(file);
    const std::string source{std::istreambuf_iterator<char>(file), {}};
    const auto result = compile(Language::BASIC, source.data(), (uint16_t)source.size(),
                                image.data(), (uint16_t)image.size());
    if (result.error != Error::NONE)
      std::fprintf(stderr, "%s: %s at %u\n", path, error_name(result.error), result.source_offset);
    assert(result.error == Error::NONE);
    image.resize(result.size);
    assert(inspect(image.data(), result.size, view) == Error::NONE);
    const ResourceSource resources={0xFFFF,0,ResourceMode::EMBEDDED};
    owned_image.resize(MAX_MODULE);
    const auto owned=compile(Language::BASIC,source.data(),(uint16_t)source.size(),
                            owned_image.data(),MAX_MODULE,true,&resources);
    assert(owned.error==Error::NONE);
    owned_image.resize(owned.size);
    assert(inspect(owned_image.data(),owned.size,owned_view)==Error::NONE);
  }
};
struct Case {
  std::array<double, 16> registers{};
  std::vector<double> input;
  uint32_t seed = 1;
  unsigned cancel_wait = 0;
  double cols = 47;
};
struct Outcome {
  Error error;
  std::array<double, 16> registers;
  std::string transcript;
  uint32_t rng;
  unsigned waits, inputs;
  bool operator==(const Outcome& b) const {
    return error == b.error && registers == b.registers && transcript == b.transcript &&
           rng == b.rng && waits == b.waits && inputs == b.inputs;
  }
};
struct Model {
  Case scenario;
  Value variables[26]{}, array[385]{}, stack[MAX_STACK]{};
  double calculator_stack[4]{};
  std::string transcript;
  uint32_t rng;
  unsigned waits = 0, inputs = 0;
  explicit Model(const Case& c) : scenario(c), rng(c.seed) {}
  static double random(void* p) {
    auto& m = *static_cast<Model*>(p);
    m.rng = m.rng * 1664525U + 1013904223U;
    return (double)(m.rng >> 8) / 16777216.0;
  }
  static double value(void* p, Function f) {
    return f == Function::COLS   ? static_cast<Model*>(p)->scenario.cols
           : f == Function::ROWS ? 8
                                 : 768;
  }
  static double math(void*, Function f, double a, double b) {
    return (uint8_t)f == 255 ? mk_math::pow(a, b) : __builtin_nan("");
  }
  static bool reference(void* p, bool write, uint8_t ref, double& value) {
    auto& m = *static_cast<Model*>(p);
    if (ref >= 20) return false;
    double& target = ref < 4 ? m.calculator_stack[ref] : m.scenario.registers[ref - 4];
    if (write)
      target = value;
    else
      value = target;
    return true;
  }
  static bool event(void* p, Event e, const char* text, uint16_t length, double& value) {
    auto& m = *static_cast<Model*>(p);
    // Compare rendering inputs: text, numbers, separators, empty lines,
    // clears, prompts and pauses. IEEE bytes avoid host locale/formatting.
    m.transcript.push_back((char)e);
    m.transcript.push_back((char)length);
    m.transcript.push_back((char)(length >> 8));
    if ((e == Event::TEXT || e == Event::READ_INPUT) && text) m.transcript.append(text, length);
    if (e == Event::NUMBER || e == Event::FORMAT)
      m.transcript.append(reinterpret_cast<const char*>(&value), sizeof(value));
    if (e == Event::READ_INPUT) {
      if (m.inputs == m.scenario.input.size()) return false;
      value = m.scenario.input[m.inputs++];
    }
    if (e == Event::WAIT) return ++m.waits != m.scenario.cancel_wait;
    return true;
  }
  Outcome run(const Program& p, bool owned=false) {
    State state{};
    state.variables = variables;
    state.array = array;
    state.array_count = 385;
    state.stack = stack;
    state.stack_capacity = MAX_STACK;
    const Services services{this, nullptr, math, random, value, reference, event};
    const auto result = language_vm::run(owned?p.owned_view:p.view, state, services, 10000);
    return {result.error, scenario.registers, transcript, rng, waits, inputs};
  }
};
static unsigned cases = 0;
static void compare(const Program& before, const Program& after, const Case& scenario,
                    const char* name) {
  for (unsigned cancelled : {0U, 1U}) {
    Case c = scenario;
    c.cancel_wait = cancelled;
    const auto a = Model(c).run(before), b = Model(c).run(after);
    assert(a==Model(c).run(before,true) && b==Model(c).run(after,true));
    ++cases;
    if (!(a == b)) {
      std::fprintf(stderr, "%s: seed=%u X=%.0f C=%.0f P=%.0f T=%.0f B=%.0f RE=%.0f cancel=%u\n",
                   name, c.seed, c.registers[0], c.registers[2], c.registers[3], c.registers[4],
                   c.registers[1], c.registers[14], cancelled);
      std::fprintf(stderr, "error %u/%u waits %u/%u inputs %u/%u rng %u/%u trace %zu/%zu\n",
                   (unsigned)a.error, (unsigned)b.error, a.waits, b.waits, a.inputs, b.inputs,
                   a.rng, b.rng, a.transcript.size(), b.transcript.size());
      assert(false);
    }
    assert(a.error == Error::NONE || a.error == Error::IO);
  }
}
int main(int argc, char** argv) {
  assert(argc == 5);
  Program old_player(argv[1]), player(argv[2]), old_bart(argv[3]), bart(argv[4]);
  const std::array<double, 6> distances{0, 1, 9, 10, 20, 100};
  for (double x : distances)
    for (double c : std::array<double, 6>{0, 1, 2, 3, 4, 5})
      for (double p : std::array<double, 8>{0, 1, 2, 3, 4, 5, 6, 7}) {
        Case scenario;
        scenario.registers[0] = x;
        scenario.registers[2] = c;
        scenario.registers[3] = p;
        scenario.registers[14] = 1;
        for (unsigned seed = 1; seed <= 8; ++seed) {
          scenario.seed = seed * 0x9E3779B9U;
          scenario.input = {3};
          compare(old_player, player, scenario, "player shot");
          for (double b : {1., 4.})
            for (double prior : {2., 3.}) {
              scenario.registers[1] = b;
              scenario.registers[14] = prior;
              scenario.input.clear();
              compare(old_bart, bart, scenario, "bart turn");
            }
        }
      }
  for (double x : distances)
    for (double p : {0., 1., 2., 3., 4., 5.}) {
      Case c;
      c.registers[0] = x;
      c.registers[3] = p;
      c.registers[14] = 1;
      for (const std::vector<double>& input : {std::vector<double>{},
                                               {1},
                                               {5},
                                               {6},
                                               {1, 0},
                                               {1, 10},
                                               {1, -1, 11, 2.5, 3},
                                               {0, 7, 2.5, 2},
                                               {2},
                                               {5, 0},
                                               {5, 1},
                                               {6, 0},
                                               {6, 49},
                                               {6, 50},
                                               {6, 2.5, 50}}) {
        c.input = input;
        compare(old_player, player, c, "player action");
      }
      for (double troughs : {0., 1., 2., 3., 4.}) {
        c.registers[4] = troughs;
        c.input = {4};
        compare(old_player, player, c, "player trough");
      }
      c.cols = 39;
      c.input.clear();
      compare(old_player, player, c, "player small screen");
      compare(old_bart, bart, c, "bart small screen");
    }
  std::printf(
      "high_noon_equivalence: %u cases; text, pauses, registers, RNG and cancellation PASS\n",
      cases);
}
