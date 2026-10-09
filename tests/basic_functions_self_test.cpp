#include "tinybasic.hpp"
#include "language_bytecode.hpp"
#include "keyboard_layout.hpp"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>

extern "C" void TinyBasicTestReset();
extern "C" TinyBasicRunStatus TinyBasicTestRunSource(const char*);
extern "C" double TinyBasicTestNumber(const char*);
extern "C" unsigned TinyBasicTestErrorDetail();
extern "C" const char* TinyBasicTestLcdLine(int);
extern "C" void TinyBasicTestSetInputs(const double*, int);
extern "C" bool TinyBasicTestCompile(const char*);
extern "C" void TinyBasicTestEditSequence(const int*, int, char*, int);

static unsigned checks, failures;
static void check(bool ok, const char* what) {
  ++checks;
  if (!ok) { ++failures; std::fprintf(stderr, "FAIL %s\n", what); }
}
static void value(const char* source, double expected, const double* inputs = nullptr,
                  int count = 0) {
  TinyBasicTestReset();
  TinyBasicTestSetInputs(inputs, count);
  check(TinyBasicTestRunSource(source) == TinyBasicRunStatus::COMPLETED, source);
  check(std::fabs(TinyBasicTestNumber("A") - expected) < 1e-12, "function result");
}
static void error(const char* source, language_vm::Error detail) {
  TinyBasicTestReset();
  check(TinyBasicTestRunSource(source) == TinyBasicRunStatus::RUNTIME_ERROR, source);
  check(TinyBasicTestErrorDetail() == (unsigned)detail, "runtime error detail");
}
int main() {
  value("10 A=3+CALL(100,7,9)*2;END\n100 RETURN ARG(1)+ARG(2)\n", 35);
  value("10 GOSUB 100,7,9;A=A+1;END\n100 A=ARG(1)+ARG(2);RETURN\n", 17);
  value("10 A=CAL.(100);END\n100 RET. 7\n", 7);
  value("10 A=CALL(100,5);END\n100 IF ARG(1)<=1 THEN RETURN 1 ELSE RETURN ARG(1)*CALL(100,ARG(1)-1)\n", 120);
  value("10 A=CALL(100,10);END\n100 RETURN CALL(200,3)+ARG(1)\n200 RETURN AR.(1)^2\n", 19);
  value("10 A=0;FOR I=1 TO 2;A=A+CALL(100,I);NEXT I;END\n100 FOR J=1 TO 3\n110 RETURN ARG(1)\n120 NEXT J\n", 3);
  value("10 A=CALL(100,10);END\n100 GOSUB 200\n110 RETURN ARG(1)+B\n200 B=7;RETURN\n", 17);
  value("10 A=3+CALL(100,10);END\n100 GOSUB 200\n110 RETURN ARG(1)+B\n200 B=7\n210 B=B+2\n220 RETURN\n", 22);
  value("10 GOSUB 100,2,3,4,5;END\n100 A=ARG(1)+ARG(2)+ARG(3)+ARG(4);RETURN 99\n", 14);
  value("10 L=100;GOSUB L;END\n100 A=7;RETURN\n", 7);
  value("10 A=9;A=CALL(100);A=88;END\n100 END\n", 9);
  check(!std::strstr(TinyBasicTestLcdLine(0), "HOW?"), "END in function has no error screen");
  value("10 GOSUB 100,7;A=99;END\n100 A=ARG(1)\n", 7);
  const double input[] = {5};
  value("10 PRINT \"Head\";CALL(100,4);END\n100 INPUT N\n110 RETURN ARG(1)*N\n", 0, input, 1);
  check(!std::strncmp(TinyBasicTestLcdLine(0), "Head20", 6), "PRINT/input preserves caller expression");
  value("10 INPUT @(CALL(100,3));A=@(4);END\n100 RETURN ARG(1)+1\n", 5, input, 1);

  error("10 A=CALL(999);END\n", language_vm::Error::MISSING_LINE);
  error("10 A=ARG(1);END\n", language_vm::Error::VARIABLE);
  error("10 A=CALL(100,7);END\n100 RETURN ARG(0)\n", language_vm::Error::VARIABLE);
  error("10 A=CALL(100,7);END\n100 RETURN ARG(2)\n", language_vm::Error::VARIABLE);
  error("10 A=CALL(100);END\n100 A=7\n", language_vm::Error::RETURN);
  error("10 A=CALL(100);END\n100 RETURN\n", language_vm::Error::RETURN);
  error("10 GOSUB 100;END\n100 RETURN 7\n", language_vm::Error::RETURN);
  error("10 A=CALL(100);END\n100 RETURN CALL(100)\n", language_vm::Error::CALL_STACK);
  error("10 A=CALL(100,3);END\n100 GOSUB 200\n110 RETURN ARG(1)\n200 A=ARG(1);RETURN\n", language_vm::Error::VARIABLE);

  TinyBasicTestReset();
  check(TinyBasicTestRunSource("10 PRINT #8:3,PI;END\n") == TinyBasicRunStatus::COMPLETED, "PRINT significant digits");
  check(!std::strncmp(TinyBasicTestLcdLine(0), "    3.14", 8), "PRINT width and precision");
  TinyBasicTestReset();
  check(TinyBasicTestRunSource("10 PRINT #0:3,PI\n20 PRINT PI\n") == TinyBasicRunStatus::COMPLETED, "PRINT precision reset");
  check(!std::strncmp(TinyBasicTestLcdLine(0), "3.14", 4), "selected precision");
  check(!std::strncmp(TinyBasicTestLcdLine(1), "3.141592654", 11), "old default precision");
  value("10 PRINT #8:3,CALL(100);END\n100 PRINT \"x\"\n110 RETURN PI\n", 0);
  check(!std::strncmp(TinyBasicTestLcdLine(1), "    3.14", 8), "nested PRINT preserves literal caller format");
  value("10 W=14;PRINT #W,CALL(100);END\n100 PRINT #0:3,\"x\"\n110 RETURN PI\n", 0);
  check(!std::strncmp(TinyBasicTestLcdLine(1), "   3.141592654", 14), "nested PRINT preserves dynamic caller format");
  value("10 PRINT #8:A=3;END\n", 3);
  for(const char* invalid : {
      "10 A=CALL(100,1,2,3,4,5)\n100 RETURN 1\n",
      "10 GOSUB 100,1,2,3,4,5\n100 RETURN\n",
      "10 A=CALL(100+1,7)\n101 RETURN 1\n",
      "10 GOSUB 50+50,7\n100 RETURN\n",
      "10 A=ARG(1,2)\n", "10 GOSUB 100,\n100 RETURN\n",
      "10 PRINT #8:0,PI\n", "10 PRINT #8:16,PI\n",
      "10 PRINT #64:3,PI\n", "10 PRINT #999999999999999999:3,PI\n"}) {
    TinyBasicTestReset();
    check(!TinyBasicTestCompile(invalid), invalid);
  }
  const auto& k = keyboard_layout::active();
  // Actual SMS input, explicit letter commits, K punctuation and F symbols.
  const int call_keys[] = {k.k,k.digit[8],k.digit[8],k.digit[8],k.digit[0],
      k.k,k.digit[8],k.digit[0],k.k,k.digit[5],k.digit[5],k.digit[5],k.digit[0],
      k.k,k.digit[5],k.digit[5],k.digit[5],k.digit[0],k.k,k.left,
      k.digit[1],k.digit[0],k.digit[0],k.k,k.right};
  char edited[64];
  TinyBasicTestEditSequence(call_keys, sizeof(call_keys)/sizeof(*call_keys), edited, sizeof(edited));
  check(!std::strcmp(edited, "CALL(100)"), "CALL keyboard input");
  const int arg_keys[] = {k.k,k.digit[8],k.digit[0],k.k,k.digit[1],k.digit[1],
      k.digit[1],k.digit[0],k.k,k.digit[4],k.digit[0],k.k,k.left,k.digit[1],k.k,k.right};
  TinyBasicTestEditSequence(arg_keys, sizeof(arg_keys)/sizeof(*arg_keys), edited, sizeof(edited));
  check(!std::strcmp(edited, "ARG(1)"), "ARG keyboard input");
  const int format_keys[] = {k.alpha,k.digit[2],k.digit[8],k.k,k.ok,k.digit[3]};
  TinyBasicTestEditSequence(format_keys, sizeof(format_keys)/sizeof(*format_keys), edited, sizeof(edited));
  check(!std::strcmp(edited, "#8:3"), "precision keyboard input");

  // The new instructions remain unavailable in INPUT's isolated evaluator.
  uint8_t bytes[language_vm::MAX_IMAGE];
  for (const char* expression : {"CALL(100)", "ARG(1)"}) {
    const auto compiled = language_vm::compile_expression(language_vm::Language::BASIC,
        expression, (uint16_t)std::strlen(expression), bytes, sizeof(bytes));
    check(compiled.error != language_vm::Error::NONE, "INPUT expression rejects program calls");
  }
  std::printf("BASIC functions: %u checks, %u failures\n", checks, failures);
  return failures ? 1 : 0;
}
