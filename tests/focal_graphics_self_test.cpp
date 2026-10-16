#include "../code/focal.cpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>
static void prepare(unsigned w = 192, unsigned h = 64) {
  FocalNextReset();
  host_wait_esc = false;
  host_key_count = host_key_index = 0;
  if (w) FocalNextGraphics(w, h);
}
static void run(const char *source, int status = 0) {
  const int actual = FocalNextRun(source);
  if (actual != status) fprintf(stderr, "status %d, expected %d: %s\n", actual, status, source);
  assert(actual == status);
  assert(!basic_graphics::active());
}
static void reject(const char *source) {
  prepare();
  if (FocalNextCompile(source)) fprintf(stderr, "unexpected acceptance: %s\n", source);
  assert(!FocalNextCompile(source));
}
static void geometry(unsigned w, unsigned h) {
  prepare(w, h);
  run("1.10 S A=GW; S B=GH; CLS; PSET 1,1; S C=POINT(1,1); PSET 1,1,2; S D=POINT(1,1)\n"
      "1.20 LINE 0,GH-1,GW-1,GH-1; BOX 3,3,7,7,1,1; CIRCLE 20,8,3; SHOW; EXIT");
  assert(FocalNextVar(0) == w && FocalNextVar(1) == h);
  assert(FocalNextVar(2) == 1 && FocalNextVar(3) == 0);
  assert(!FocalNextPixel(1,1) && FocalNextPixel(4,4));
  assert(FocalNextPixel(20,5) && FocalNextPixel(w-1,h-1));

  prepare(w,h);
  run("1.10 CLS; PRINT AT 2,0,'A',!,'B'; EXIT");
  assert(FocalNextPixel(2,0) && FocalNextPixel(2,8));
  assert(!FocalNextPixel(8,0));

  prepare(w,h);
  run("1.10 CLS; PRINT AT 2,0,%5.3,CALL(2),9; EXIT\n"
      "2.10 PRINT AT 50,8,'N'; RETURN 7");
  // Three padding blanks, 7, a separator blank, then 9. Nested PRINT cannot
  // consume the outer position, output buffer or FOCAL numeric format.
  assert(!FocalNextPixel(2,0) && FocalNextPixel(26,0) && FocalNextPixel(62,0));
  assert(FocalNextPixel(50,8));

  prepare(w,h);
  run("1.10 CLS; PRINT AT 2,0,%5.3,12345; PRINT AT 2,0,%5.3,1; EXIT");
  assert(!FocalNextPixel(2,0) && !FocalNextPixel(20,0) && FocalNextPixel(26,0));

  prepare(w,h);
  run("1.10 S X=42; CLS; GRAPH X+0+0+0,-1,1,-1,1; S A=X; EXIT");
  assert(FocalNextVar(0) == 42 && FocalNextVar('X'-'A') == 42);
  assert(FocalNextPixel(0,h-1) && FocalNextPixel(w-1,0));
  prepare(w,h);
  run("1.10 S X=77; CLS; GRAPH 1/0,-1,1,-1,1; S A=X; EXIT");
  assert(FocalNextVar(0) == 77);
  prepare(w,h);
  run("1.10 S X=91; GRAPH ARG(1),-1,1,-1,1; EXIT", 3);
  assert(FocalNextVar('X'-'A') == 91);
  prepare(w,h);
  run("1.10 S X=11; CLS; DO 2,0; S A=X; EXIT\n2.10 GRAPH X+ARG(1),-1,1,-1,1; RETURN");
  assert(FocalNextVar(0) == 11 && FocalNextPixel(w-1,0));

  prepare(w,h);
  double input[] = {7}; FocalNextInputs(input,1);
  run("1.10 CLS; PSET GW-1,GH-1; ASK N; S A=N+POINT(GW-1,GH-1); EXIT");
  assert(FocalNextVar(0) == 8 && FocalNextPixel(w-1,h-1));
  prepare(w,h);
  host_wait_esc = true;
  run("1.10 CLS; PSET 1,1; ASK; PSET 2,2; EXIT",1);
  assert(FocalNextPixel(1,1) && !FocalNextPixel(2,2) && FocalNextPresents());

  prepare(w,h);
  run("1.10 CLS; BOX 0,0,GW-1,GH-1,1,1; PRINT 'A'; EXIT");
  assert(FocalNextPixel(w-1,h-1));
  assert(!FocalNextPixel(5,0));
  prepare(w,h);
  run("1.10 PSET 0,0,3; EXIT",3);
  prepare(w,h);
  run("1.10 CIRCLE 1,1,-1; EXIT",3);
  prepare(w,h);
  run("1.10 GRAPH X,1,1,-1,1; EXIT",3);
}
static void graphical_input_expression() {
  using namespace language_vm;
  prepare(80,16);
  basic_graphics::RunScope scope;
  basic_graphics::Request point = {}; point.operation=basic_graphics::Operation::PSET;
  point.count=2; point.args[0]=point.args[1]=1;
  assert(basic_graphics::dispatch(point) == basic_graphics::Result::OK);
  const char *source="POINT(1,1)+GW+GH";
  uint8_t image[256];
  const auto compiled=compile_expression(Language::FOCAL,source,uint16_t(strlen(source)),image,sizeof(image));
  assert(compiled.error == Error::NONE);
  View view; assert(inspect(image,compiled.size,view) == Error::NONE);
  Value values[MAX_STACK],variables[26]={};
  State state={};state.variables=variables;state.stack=values;state.stack_capacity=MAX_STACK;
  Services services={nullptr,nullptr,next_math,next_random,next_dynamic,next_reference,next_graphics};
  assert(language_vm::run(view,state,services).error == Error::NONE && values[0]==97);
}
static void graph_interrupts() {
  using namespace language_vm;
  const char *source = "1.10 S X=99; GRAPH X,-1,1,-1,1; EXIT";
  uint8_t image[MAX_IMAGE];
  const auto compiled = compile(Language::FOCAL, source, uint16_t(strlen(source)), image, sizeof(image));
  assert(compiled.error == Error::NONE);
  View view; assert(inspect(image,compiled.size,view) == Error::NONE);
  Value variables[26] = {}, array[64] = {}, stack[MAX_STACK];
  State state = {}; state.variables=variables; state.array=array; state.array_count=64;
  state.stack=stack; state.stack_capacity=MAX_STACK;
  struct Context { State *state; bool stop; } context{&state,true};
  Services services = {&context,
      [](void *p) { const auto &c=*(Context*)p; return !(c.stop && c.state->graph.active); },
      nullptr,nullptr,
      [](void *, Function f) { return f==Function::GW ? 192.0 : 64.0; },
      nullptr,[](void *, Event, const char *, uint16_t, double &) { return true; }};
  auto result = language_vm::run(view,state,services);
  assert(result.error == Error::STOPPED && variables['X'-'A'] == 99 && !state.graph.active);
  context.stop=false;
  result = language_vm::run(view,state,services,10);
  assert(result.error == Error::LIMIT && variables['X'-'A'] == 99 && !state.graph.active);
  // A previous compiler/executor must reject the new source-language contract.
  image[4]=VERSION-1;
  assert(inspect(image,compiled.size,view) == Error::INVALID_IMAGE);
}
int main() {
  prepare(0,0);
  run("1.10 S A=GW+GH; PRINT 'TEXT'; EXIT");
  assert(FocalNextVar(0) == 0);
  prepare(0,0); run("1.10 PSET 0,0; EXIT",3);
  geometry(80,16); geometry(192,64); graph_interrupts(); graphical_input_expression();
  for (const char *source : {
      "1.10 PSET 1", "1.10 PSET 1,2,1,0", "1.10 LINE 1,2,3", "1.10 BOX 1,2,3,4,1,1,1",
      "1.10 SHOW 1", "1.10 SHOW,", "1.10 PSET 1,2,", "1.10 PRINT AT 1,2,",
      "1.10 PRINT AT 1,2; PRINT 7", "1.10 GRAPH RND(),-1,1,-1,1",
      "1.10 GRAPH CALL(2),-1,1,-1,1\n2.10 RETURN 1", "1.10 SET GW=1", "1.10 SET A=GW()",
      "1.10 GRAPH X,-1,1,-1,1,1", "1.10 GRAPH X,-1,1,-1", "1.10 EXEC POINT(1)",
      "1.10 EXEC POINT(1,2,3)"}) reject(source);
  assert(focal_next::command_name(focal_next::Command::PRINT)[0]=='P');
  puts("FOCAL graphics: 80x16/192x64, PRINT AT, formatting/nested CALL, ASK, GRAPH cleanup and errors PASS");
}
