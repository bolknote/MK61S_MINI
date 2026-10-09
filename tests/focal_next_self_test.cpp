#include "focal.hpp"
#include "keyboard_layout.hpp"
#include "language_bytecode.hpp"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <string>
extern "C" {
void FocalNextReset();
int FocalNextRun(const char *);
bool FocalNextCompile(const char *);
double FocalNextVar(int);
double FocalNextArray(int, int, int);
void FocalNextInputs(const double *, unsigned);
const char *FocalNextPrompt();
const char *FocalNextScreen(int);
unsigned FocalNextRuntimeSize();
void FocalNextAngleMode(int);
void FocalNextEdit(const int *, int, char *, int);
}
static void run(const char *source) {
  FocalNextReset();
  int result = FocalNextRun(source);
  if (result != 0)
    fprintf(stderr, "run status %d for:\n%s\n", result, source);
  assert(result == 0);
}
static double var(char c) { return FocalNextVar(c - 'A'); }
static void eq(double a, double b) {
  if (fabs(a - b) > 1e-9)
    fprintf(stderr, "%g != %g\n", a, b);
  assert(fabs(a - b) < 1e-9);
}
static void rejected(const char *text) {
  FocalNextReset();
  bool ok = FocalNextCompile(text);
  if (ok)
    fprintf(stderr, "unexpected acceptance: %s\n", text);
  assert(!ok);
}
static void edit(const char *before, const int *keys, unsigned n,
                 const char *expected) {
  char buffer[256];
  strcpy(buffer, before);
  FocalNextEdit(keys, int(n), buffer, sizeof(buffer));
  if (strcmp(buffer, expected))
    fprintf(stderr, "editor '%s' expected '%s'\n", buffer, expected);
  assert(!strcmp(buffer, expected));
}
int main() {
  run("1.10 SET X=2+3*4; SET Y=X^2; EXIT");
  eq(var('X'), 14);
  eq(var('Y'), 196);
  run("1.10 S A=0; FOR I=1,2,9; S A=A+I; S B=B+1\n1.20 EXIT");
  eq(var('A'), 25);
  eq(var('B'), 5);
  run("1.10 FOR I=5,-2,1; SET A=A+I\n1.20 EXIT");
  eq(var('A'), 9);
  run("1.10 FOR I=3,1; SET A=99\n1.20 EXIT");
  eq(var('A'), 0);
  run("1.10 FOR I=1,3; FOR J=1,2; SET A=A+1\n1.20 EXIT");
  eq(var('A'), 6);
  run("1.10 S A(1)=7; S B(1)=9; S A(1,2)=11; S X=A(1)+B(1)+A(1,2)\n1.20 E");
  eq(var('X'), 27);
  eq(FocalNextArray(0, 1, 0), 7);
  eq(FocalNextArray(0, 1, 2), 11);
  run("1.10 F I=0,31; S A(I)=I\n1.20 S X=A(31); E");
  eq(var('X'), 31);
  FocalNextReset();
  assert(FocalNextRun("1.10 F I=0,32; S A(I)=I\n1.20 E") == 3);
  FocalNextReset();
  assert(FocalNextRun("1.10 S A(-1)=1; E") == 3);
  run("1.10 SET X=A(321,456); EXIT");
  eq(var('X'), 0);
  run("1.10 DO 2; SET X=A; EXIT\n2.10 SET A=7\n2.20 SET A=A+1");
  eq(var('X'), 8);
  run("1.10 DO 2.10; SET X=A; EXIT\n2.10 SET A=7\n2.20 SET A=99");
  eq(var('X'), 7);
  run("1.10 DO 2,7,9; EXIT\n2.10 SET A=ARG(1)+ARG(2); RETURN");
  eq(var('A'), 16);
  run("1.10 SET X=3+CALL(2,7,9)*2; EXIT\n2.10 RETURN ARG(1)+ARG(2)");
  eq(var('X'), 35);
  run("1.10 SET X=CALL(2,5); EXIT\n2.10 IF(ARG(1)-1) 2.30,2.30; RETURN "
      "ARG(1)*CALL(2,ARG(1)-1)\n2.30 RETURN 1");
  eq(var('X'), 120);
  run("1.10 DO 2,10; EXIT\n2.10 SET A=CALL(3,2)+ARG(1); RETURN\n3.10 RETURN "
      "ARG(1)^2");
  eq(var('A'), 14);
  FocalNextReset();
  assert(FocalNextRun("1.10 SET X=CALL(2); EXIT\n2.10 SET A=7") == 3);
  FocalNextReset();
  assert(FocalNextRun("1.10 RETURN") == 3);
  FocalNextReset();
  assert(FocalNextRun("1.10 SET A=ARG(1); EXIT") == 3);
  FocalNextReset();
  assert(FocalNextRun("1.10 DO 1,1\n1.20 EXIT") == 3);
  run("1.10 SET X=-2; IF(X) 1.30,,; SET A=99; EXIT\n1.30 SET A=7; EXIT");
  eq(var('A'), 7);
  run("1.10 SET X=0; IF(X) 1.30,,1.30; SET A=7; EXIT\n1.30 SET A=99; EXIT");
  eq(var('A'), 7);
  run("1.10 SET X=2; B(X) ,,1.30; SET A=99; EXIT\n1.30 SET A=7; EXIT");
  eq(var('A'), 7);
  run("1.10 FOR I=1,5; IF(I-3) ,,1.30; SET A=A+1\n1.30 EXIT");
  eq(var('A'), 3);
  FocalNextReset();
  double inputs[] = {4, 9};
  FocalNextInputs(inputs, 2);
  assert(FocalNextRun("1.10 ASK \"A=\",A,\"B=\",B; SET X=A+B; EXIT") == 0);
  eq(var('X'), 13);
  assert(!strcmp(FocalNextPrompt(), "B="));
  FocalNextReset();
  double array_input[] = {42};
  FocalNextInputs(array_input, 1);
  assert(FocalNextRun("1.10 ASK \"VALUE\",A(3); SET X=A(3); EXIT") == 0);
  eq(var('X'), 42);
  run("1.10 SET .X=42; SET .R0=.X+1; SET A=.R0; EXIT");
  eq(var('A'), 43);
  run("1.10 SET A=MIN(7,9)+MOD(10,3)+MAX(2,4); EXIT");
  eq(var('A'), 12);
  run("1.10 PRINT \"A;B\",!,%8.3,PI,!; EXIT");
  assert(!strncmp(FocalNextScreen(0), "A;B", 3));
  assert(!strncmp(FocalNextScreen(1), "    3.14", 8));
  run("1.10 PRINT 'first',!; PRINT 'second',!; EXIT");
  assert(!strncmp(FocalNextScreen(0), "second", 6));
  run("1.10 PRINT \"old\"; CLS; PRINT \"new\",!; EXIT");
  assert(!strncmp(FocalNextScreen(0), "new", 3));
  run("2.10 RETURN 5\n1.10 SET X=CALL(2); EXIT");
  eq(var('X'), 5);
  rejected("1.10 BRANCH(X) 1.10,1.10,1.10");
  rejected("1.10 TYPE 1");
  rejected("1.10 IF X");
  rejected("1.10 SET A0=1");
  rejected("1.10 SET A=CALL(2)\n2.10 RETURN 1,2");
  rejected("1.10 DO 2,1,2,3,4,5\n2.10 RETURN");
  rejected("1.10 SET A=RND(1)");
  rejected("1.10 GOTO 2");
  FocalNextReset();
  assert(FocalNextRun("1.10 GOTO 2.10") == 3);
  rejected("1.10 FOR I=1,2; ");
  rejected("1.10 SET A=(2+3");
  rejected("1.10 PRINT \"oops");
  rejected("1.10 PRINT %8.0 PI");
  rejected("1.10 EXIT garbage");
  rejected("1.10 SET A=1\n1.10 EXIT");
  std::string nested =
      "1.10 SET A=" + std::string(50, '(') + "1" + std::string(50, ')');
  rejected(nested.c_str());
  FocalNextReset();
  FocalNextAngleMode(11);
  assert(FocalNextRun("1.10 SET A=SIN(30); SET B=ASIN(.5); EXIT") == 0);
  eq(var('A'), .5);
  eq(var('B'), 30);
  FocalNextReset();
  FocalNextAngleMode(12);
  assert(FocalNextRun("1.10 SET A=SIN(100); EXIT") == 0);
  eq(var('A'), 1);
  const auto &k = keyboard_layout::active();
  int ask[] = {k.dot};
  edit("1.10 ", ask, 1, "1.10 ASK ");
  edit("1.10", ask, 1, "1.10 ASK ");
  int branch[] = {k.neg};
  edit("1.10 ", branch, 1, "1.10 IF ");
  edit("1.10 SET A=1; ", branch, 1, "1.10 SET A=1; IF ");
  int semicolon[] = {k.k, k.ret};
  edit("1.10 SET A=1", semicolon, 2, "1.10 SET A=1;");
  int do_key[] = {k.k, k.cx};
  edit("1.10 ", do_key, 2, "1.10 DO ");
  int backspace[] = {k.cx};
  edit("1.10 IF ", backspace, 1, "1.10 ");
  int clear[] = {k.alpha, k.cx};
  edit("1.10 SET A=1", clear, 2, "");
  int macro[] = {k.alpha, k.sub};
  edit("1.10 SET A=X+Y", macro, 2, "1.10 SET A=SQRT(X+Y)");
  int symbol[] = {k.alpha, k.digit[0]};
  edit("1.10 PRINT ", symbol, 2, "1.10 PRINT !");
  int square[] = {k.alpha, k.mul};
  edit("1.10 PRINT X", square, 2, "1.10 PRINT X^2");
  int minus[] = {k.sub};
  edit("1.10 SET A=X", minus, 1, "1.10 SET A=X-");
  int sms[] = {k.k, k.digit[8], k.digit[8], k.digit[0]};
  edit("1.10 SET ", sms, 4, "1.10 SET B");
  edit("1.10 SET A=1; PRINT X", macro, 2, "1.10 SET A=1; PRINT SQRT(X)");
  edit("1.10 SET A=SIN(X", macro, 2, "1.10 SET A=SIN(SQRT(X)");
  edit("1.10 COMMENT text; ", branch, 1, "1.10 COMMENT text; ");
  int shifted_branch[] = {k.k, k.neg};
  edit("1.10 ", shifted_branch, 2, "1.10 IF ");
  printf("focal_next_self_test: ok, adapter RAM=%u\n", FocalNextRuntimeSize());
}
