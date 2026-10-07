#include <assert.h>
#include <stdio.h>
#include <string.h>

#include <vector>

#include "language_bytecode.hpp"
#include "mk_math.hpp"

using namespace language_vm;
namespace {
double math(void*, Function f, double a, double b) {
  switch (f) {
    case Function::SIN:
      return mk_math::sin(a);
    case Function::COS:
      return mk_math::cos(a);
    case Function::TAN:
      return mk_math::tan(a);
    case Function::ASIN:
      return mk_math::asin(a);
    case Function::ACOS:
      return mk_math::acos(a);
    case Function::ATAN:
      return mk_math::atan(a);
    case Function::LN:
      return mk_math::ln(a);
    case Function::LOG10:
      return mk_math::log10(a);
    case Function::EXP:
      return mk_math::exp(a);
    case Function::SQRT:
      return mk_math::sqrt(a);
    default:
      return mk_math::pow(a, b);
  }
}
bool event(void*, Event, const char*, uint16_t, double&) { return true; }
bool service(void*) { return true; }
Services services = {nullptr, service, math, nullptr, nullptr, nullptr, event};
struct Fixture {
  uint8_t image[MAX_IMAGE];
  View view = {};
  State state = {};
  double vars[26] = {}, array[385] = {}, values[MAX_STACK] = {};
  void compile(const char* source, Language language = Language::BASIC) {
    const auto result = language_vm::compile(language, source, (uint16_t)strlen(source),
                                             image, sizeof(image));
    if (result.error != Error::NONE)
      fprintf(stderr, "compile %s at %u: %s\n", error_name(result.error),
              result.source_offset, source);
    assert(result.error == Error::NONE);
    assert(inspect(image, result.size, view) == Error::NONE);
    state.variables = vars;
    state.array = array;
    state.array_count = 385;
    state.stack = values;
    state.stack_capacity = MAX_STACK;
  }
  void crc() {
    uint32_t value = checksum(image + HEADER_SIZE, view.size - HEADER_SIZE);
    for (unsigned i = 0; i < 4; ++i) image[20 + i] = (uint8_t)(value >> (i * 8));
  }
};
void test_literals() {
  const char* literals[] = {"0.1",
                            "1.0000000",
                            ".000012345",
                            "123.045",
                            "655.35",
                            "1e-99",
                            "1e99",
                            "1e-300",
                            "1e300",
                            "9007199254740992",
                            "1.234567890123456789",
                            "-0",
                            "-0.000",
                            "2.2250738585072014e-308"};
  for (const char* literal : literals) {
    Fixture f;
    const auto result = compile_expression(
        Language::BASIC, literal, (uint16_t)strlen(literal), f.image, sizeof(f.image));
    assert(result.error == Error::NONE);
    assert(inspect(f.image, result.size, f.view) == Error::NONE);
    f.state.variables = f.vars;
    f.state.stack = f.values;
    f.state.stack_capacity = MAX_STACK;
    assert(run(f.view, f.state, services).error == Error::NONE);
    const double expected = mk_math::atof(literal);
    assert(memcmp(&expected, &f.values[0], sizeof(expected)) == 0);
  }
  Fixture f;
  const auto result =
      compile_expression(Language::BASIC, ".1", 2, f.image, sizeof(f.image));
  assert(result.size == HEADER_SIZE + 5);
  assert(f.image[HEADER_SIZE] == (uint8_t)Op::CONST_DEC8);
}
void test_sizing_and_bounds() {
  const char* source = "10 A=.1+.2\n20 @(0)=A\n30 A=@(0)\n";
  Fixture f;
  f.compile(source);
  const auto sizing = language_vm::compile(
      Language::BASIC, source, (uint16_t)strlen(source), nullptr, MAX_IMAGE);
  assert(sizing.error == Error::NONE && sizing.size == f.view.size &&
         sizing.stack == f.view.stack);
  std::vector<uint8_t> guarded(f.view.size + 16, 0xA5);
  const auto failed =
      language_vm::compile(Language::BASIC, source, (uint16_t)strlen(source),
                           guarded.data() + 8, (uint16_t)(f.view.size - 1));
  assert(failed.error == Error::FULL && !failed.size);
  for (unsigned i = 0; i < 8; ++i)
    assert(guarded[i] == 0xA5 && guarded[guarded.size() - 1 - i] == 0xA5);
  assert(run(f.view, f.state, services).error == Error::NONE);
  assert(f.vars[0] == mk_math::atof(".1") + mk_math::atof(".2"));
  f.image[6] = 1;
  assert(inspect(f.image, f.view.size, f.view) == Error::NONE);
  f.state.stack_capacity = 1;
  assert(run(f.view, f.state, services).error == Error::STACK);
}

void test_key_input_is_an_ordered_keyboard_expression() {
  struct Keys {
    unsigned reads = 0;
    bool fail = false;
    double values[4] = {15, 18, 4, 6};
  } keys;
  Services host = services;
  host.context = &keys;
  host.yield_input = true;
  host.event = [](void* raw, Event e, const char*, uint16_t, double& value) {
    auto& k = *(Keys*)raw;
    if(e == Event::READ_KEY) {
      if(k.fail) return false;
      assert(k.reads < 4);
      value = k.values[k.reads++];
    }
    return true;
  };
  Fixture f;
  f.compile("10 IF 0 A=INPUT()\n20 K=INPUT():@(0)=INP.()\n30 A=INPUT()+INPUT()\n");
  assert(keys.reads == 0);
  assert(run(f.view, f.state, host).error == Error::NONE);
  assert(keys.reads == 4 && f.vars['K'-'A'] == 15 && f.array[0] == 18 && f.vars[0] == 10);

  keys.reads = 0;
  f.compile("10 @(-1)=INPUT()\n");
  assert(run(f.view, f.state, host).error == Error::ARRAY_RANGE && keys.reads == 0);

  keys.fail = true;
  f.compile("10 A=9\n20 A=INPUT()\n");
  assert(run(f.view, f.state, host).error == Error::IO && f.vars[0] == 9);

  keys.fail = false;
  keys.reads = 0;
  f.compile("10 PRINT \"K=\";INPUT();IN.(3.8)\n");
  assert(run(f.view, f.state, host).error == Error::NONE && keys.reads == 1);

  // INPUT's expression evaluator cannot perform nested keyboard I/O.
  assert(compile_expression(Language::BASIC, "INPUT()", 7, f.image, sizeof(f.image)).error
         == Error::FUNCTION);
  const auto r = compile_expression(Language::BASIC, "RND()", 5, f.image, sizeof(f.image));
  assert(r.error == Error::NONE && inspect(f.image, r.size, f.view) == Error::NONE);
  f.image[HEADER_SIZE] = (uint8_t)Op::READ_KEY;
  f.image[HEADER_SIZE+1] = (uint8_t)Op::HALT;
  f.crc();
  View invalid;
  assert(inspect(f.image, r.size, invalid) == Error::INVALID_IMAGE);
}
void test_validation() {
  Fixture f;
  f.compile("10 IF 1 GOTO 30\n20 A=1\n30 END\n");
  const auto image = std::vector<uint8_t>(f.image, f.image + f.view.size);
  const uint16_t size = f.view.size;
  for (uint16_t n = 0; n < size; ++n) {
    View v;
    assert(inspect(f.image, n, v) != Error::NONE);
  }
  f.image[f.view.code] = 255;
  f.crc();
  View v;
  assert(inspect(f.image, size, v) == Error::INVALID_IMAGE);
  memcpy(f.image, image.data(), size);
  f.image[24] = 1;
  assert(inspect(f.image, size, v) == Error::INVALID_IMAGE);
  memcpy(f.image, image.data(), size);
  f.image[size - 1] ^= 1;
  assert(inspect(f.image, size, v) == Error::INVALID_IMAGE);
  f.compile("10 A=1+2\n");
  f.image[f.view.code + 1] = (uint8_t)Op::JUMP;
  f.image[f.view.code + 2] = (uint8_t)(f.view.code + 3);
  f.image[f.view.code + 3] = (uint8_t)((f.view.code + 3) >> 8);
  f.crc();
  assert(inspect(f.image, f.view.size, v) == Error::INVALID_IMAGE);
}
void test_controls_and_traps() {
  Fixture f;
  f.compile("10 GOSUB 100;A=A+10;END\n100 A=A+1;RETURN\n");
  assert(run(f.view, f.state, services).error == Error::NONE && f.vars[0] == 11);
  f.compile("10 IF 0 GOTO 999\n20 A=7\n");
  assert(run(f.view, f.state, services).error == Error::NONE && f.vars[0] == 7);
  f.compile("10 A=8\n20 GOTO 999\n");
  assert(run(f.view, f.state, services).error == Error::MISSING_LINE && f.vars[0] == 8);
  f.compile("10 GOTO 10\n");
  assert(run(f.view, f.state, services, 100).error == Error::LIMIT);
  f.compile("10 A=1e999=1e999\n");
  assert(run(f.view,f.state,services).error==Error::MATH);
  f.compile("1.10 D 2.10\n1.20 E\n2.10 G 9.10\n", Language::FOCAL);
  assert(run(f.view, f.state, services).error == Error::LINE);
  f.compile("1.10 F I=1,3; S S=S+I\n1.20 E\n", Language::FOCAL);
  assert(run(f.view, f.state, services).error == Error::NONE &&
         f.vars['I' - 'A'] == 3 && f.vars['S' - 'A'] == 6);
}
void test_parser_edges() {
  const char* invalid[] = {"10 A=INPUT\n", "10 A=INPUT(1)\n", "10 A=INPUT(,)\n",
                           "10 A=PI.\n",       "10 A=MAX(1)\n",   "10 PAUSE 1\n",
                           "10 GOTO 10:END\n", "10 A=BOGUS(1)\n", "10 .R00=1\n"};
  for (const char* source : invalid)
    assert(language_vm::compile(Language::BASIC, source, (uint16_t)strlen(source),
                                nullptr, MAX_IMAGE)
               .error != Error::NONE);
  const auto rf = language_vm::compile(Language::FOCAL, "1.10 S .RF=1", 12, nullptr,
                                       MAX_IMAGE, false);
  assert(rf.error == Error::REGISTER);
  // Exercise the decoder with deterministic arbitrary inputs, including
  // intact magic and CRC. This is bounded and cannot execute random loops.
  uint32_t random = 0x61B451C;
  Fixture f;
  for (unsigned n = 0; n < 2000; ++n) {
    for (unsigned i = 0; i < 128; ++i) {
      random = random * 1664525U + 1013904223U;
      f.image[i] = (uint8_t)(random >> 24);
    }
    if (n % 2 == 0) memcpy(f.image, "LBV1", 4);
    View v;
    assert(inspect(f.image, 128, v) != Error::NONE);
  }
}
void test_yield_resume() {
  Fixture f;
  f.compile("10 S=0\n20 FOR I=1 TO 3\n30 GOSUB 100\n40 NEXT I\n"
            "50 A=S;END\n100 INPUT @(I)\n110 S=S+@(I);RETURN\n");
  Services yielding = services; yielding.yield_input = true;
  Continuation saved = {};
  bool resume = false;
  unsigned inputs = 0;
  for (;;) {
    // Recreate all native bindings on every segment, as a relocated APP does.
    const Bindings fresh = {f.vars, f.array, 385, f.values, MAX_STACK};
    const auto result = run(f.view, saved, fresh, yielding, 10000, resume);
    if (result.error == Error::NONE) break;
    assert(result.error == Error::YIELDED);
    assert(f.image[result.pc] == (uint8_t)Op::READ_INPUT);
    assert(saved.loop_count == 1 && saved.call_count == 1 && saved.sp == 1);
    assert(f.values[0] == ++inputs);
    f.values[saved.sp++] = inputs * 10;
    resume = true;
  }
  assert(inputs == 3 && f.vars[0] == 60 && f.array[3] == 30);
  saved.pc = f.view.size;
  assert(run(f.view, saved, static_cast<const Bindings&>(f.state), yielding,
             100, true).error == Error::INVALID_IMAGE);
  saved.pc = f.view.code; saved.sp = MAX_STACK + 1;
  assert(run(f.view, saved, static_cast<const Bindings&>(f.state), yielding,
             100, true).error == Error::INVALID_IMAGE);
  saved.sp = 0; saved.loop_count = 1; saved.loops[0].variable = 26;
  assert(run(f.view, saved, static_cast<const Bindings&>(f.state), yielding,
             100, true).error == Error::INVALID_IMAGE);
}
void test_extension_image_validation_and_resume() {
  Fixture f;
  f.compile("10 DATA -.1,2\n20 READ A;INPUT B;READ C\n");
  Services yielding=services;
  yielding.yield_input=true;
  assert(run(f.view,f.state,yielding).error==Error::YIELDED);
  assert(f.vars[0]==-.1);
  const uint16_t data=f.state.data_pc;
  State invalid=f.state;
  invalid.data_pc++;
  assert(run(f.view,invalid,services,100,true).error==Error::INVALID_IMAGE);
  invalid=f.state;
  invalid.data_index--;
  assert(run(f.view,invalid,services,100,true).error==Error::INVALID_IMAGE);
  assert(f.vars[1]==0 && f.vars[2]==0);

  const std::vector<uint8_t> original(f.image,f.image+f.view.size);
  View checked;
  f.image[data+1]=f.image[data+2]=0;
  f.crc();
  assert(inspect(f.image,f.view.size,checked)==Error::INVALID_IMAGE);
  memcpy(f.image,original.data(),original.size());
  f.image[data+3]=(uint8_t)Op::STORE;
  f.crc();
  assert(inspect(f.image,f.view.size,checked)==Error::INVALID_IMAGE);
  memcpy(f.image,original.data(),original.size());
  f.image[f.view.code+1]=f.image[f.view.code+2]=0;
  f.crc();
  assert(inspect(f.image,f.view.size,checked)==Error::INVALID_IMAGE);

  f.compile("10 ON 0 GOSUB 20\n20 RETURN\n");
  uint16_t at=f.view.code;
  while(at<f.view.size && f.image[at]!=(uint8_t)Op::ON_GOSUB) ++at;
  assert(at+4<f.view.size);
  f.image[at+3]=f.image[at+4]=0;
  f.crc();
  assert(inspect(f.image,f.view.size,checked)==Error::INVALID_IMAGE);
}
}  // namespace
int main() {
  test_literals();
  test_sizing_and_bounds();
  test_key_input_is_an_ordered_keyboard_expression();
  test_validation();
  test_controls_and_traps();
  test_parser_edges();
  test_yield_resume();
  test_extension_image_validation_and_resume();
  puts("language_vm_self_test: ok");
}
