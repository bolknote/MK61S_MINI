#include "language_vm_abi.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

using namespace language_vm;
namespace {
unsigned maximum;
void check_expression(const std::string& text) {
  if (text.empty() || text.size() > 64) return;
  uint8_t image[INPUT_IMAGE_CAPACITY+16]; memset(image, 0xA5, sizeof(image));
  uint8_t large[MAX_IMAGE];
  const auto unlimited = compile_expression(Language::BASIC, text.c_str(),
      (uint16_t)text.size(), large, sizeof(large));
  if (unlimited.error != Error::NONE) return;
  const auto limited = compile_expression(Language::BASIC, text.c_str(),
      (uint16_t)text.size(), image+8, INPUT_IMAGE_CAPACITY);
  assert(limited.error == Error::NONE && limited.size == unlimited.size);
  assert(!memcmp(large, image+8, limited.size));
  for (unsigned i=0;i<8;++i) assert(image[i]==0xA5 && image[INPUT_IMAGE_CAPACITY+8+i]==0xA5);
  View view; assert(inspect(image+8, limited.size, view) == Error::NONE);
  assert(view.stack <= 32); // <=64 source bytes cannot contain more leaves.
  ExecutionState state = {}; state.language = Language::BASIC;
  state.control.pc = 47; state.control.sp = 1;
  state.control.call_count = 2; state.control.loop_count = 3;
  memset(state.control.calls, 0xA5, sizeof(state.control.calls));
  memset(state.control.loops, 0x5A, sizeof(state.control.loops));
  memset(state.output, 0x3C, sizeof(state.output));
  state.stack[0] = 123; state.input_value = 7;
  const Continuation saved = state.control;
  uint8_t* const borrowed = input_image_storage(state);
  memset(borrowed, 0xA5, INPUT_IMAGE_CAPACITY);
  memcpy(borrowed, image+8, limited.size);
  uint8_t saved_image[INPUT_IMAGE_CAPACITY]; memcpy(saved_image, borrowed, sizeof(saved_image));
  assert(inspect(borrowed, limited.size, view) == Error::NONE);
  Value variables[26] = {}, array[385] = {};
  const Bindings bindings = {variables, array, 385, state.stack, MAX_STACK};
  const auto result = evaluate_input(view, state, bindings, {});
  assert(result.error != Error::STACK && result.error != Error::INVALID_IMAGE);
  assert(!memcmp(&saved, &state.control, sizeof(saved)) && state.stack[0] == 123);
  assert(!memcmp(saved_image, borrowed, sizeof(saved_image)));
  for (char byte : state.output) assert(byte == 0x3C);
  if (limited.size > maximum) maximum = limited.size;
}
void test_capacity() {
  const char* atoms[] = {".1", ".9", "A", "16", "127", "128", "65536", "1e999",
                         "PI", "RND", "@(A)", ".RF", "MAX(A,B)", "SQRT(.1)"};
  const char* operators[] = {"+", "-", "*", "/", "^", "=", "<>", " AND ", " OR "};
  for (const char* atom : atoms)
    for (const char* op : operators) {
      std::string expression = atom;
      while (expression.size() <= 64) {
        check_expression(expression);
        check_expression("-"+expression);
        check_expression("--"+expression);
        check_expression("("+expression+")");
        expression += std::string(op)+atom;
      }
    }
  for (unsigned n=1;n<=30;++n) {
    check_expression(std::string(n, '(')+".1"+std::string(n, ')'));
    check_expression(std::string(n, '-')+".1");
    std::string nested = ".1";
    for (unsigned i=0;i<n;++i) nested = ".1+("+nested+")";
    check_expression(nested);
  }
  std::string deepest = "1";
  for (unsigned i=1; i<16; ++i) deepest = "1+("+deepest+")";
  check_expression(deepest); // 61 source bytes keep 16 leaves live
  uint8_t deepest_image[INPUT_IMAGE_CAPACITY];
  const auto deepest_result = compile_expression(Language::BASIC, deepest.c_str(),
      (uint16_t)deepest.size(), deepest_image, sizeof(deepest_image));
  assert(deepest_result.error == Error::NONE && deepest_result.stack == 16);
  uint32_t random=0x61C04;
  for (unsigned i=0;i<10000;++i) {
    std::string text=atoms[i%14];
    for (unsigned n=0;n<20;++n) {
      random=random*1664525U+1013904223U;
      const std::string next=std::string(operators[(random>>16)%9])+atoms[random%14];
      if (text.size()+next.size()>64) break;
      text+=next;
    }
    check_expression(text);
  }
  assert(maximum <= INPUT_IMAGE_CAPACITY);
#if defined(LANGUAGE_VM_TEST_NO_DECIMAL_RECIPE)
  assert(maximum >= 243); // no assumption that any backend can use DEC recipes
#endif
}
void test_borrowed_stack() {
  ExecutionState state = {}; state.language = Language::BASIC;
  uint8_t* const image = input_image_storage(state);
  state.control.pc = 47; state.control.sp = 1;
  state.control.call_count = 2; state.control.loop_count = 3;
  memset(state.control.calls, 0xA5, sizeof(state.control.calls));
  memset(state.control.loops, 0x5A, sizeof(state.control.loops));
  state.stack[0] = 123; state.input_value = 7;
  const Continuation saved = state.control;
  Value variables[26] = {}; variables[0] = 5;
  Value array[385] = {}; array[2] = 8;
  const Bindings bindings = {variables, array, 385, state.stack, MAX_STACK};
  for (const char* text : {"A+@(2)", "1/0"}) {
    const auto compiled = compile_expression(Language::BASIC, text, (uint16_t)strlen(text), image, INPUT_IMAGE_CAPACITY);
    assert(compiled.error == Error::NONE);
    View view; assert(inspect(image, compiled.size, view) == Error::NONE);
    const auto result = evaluate_input(view, state, bindings, {});
    assert(result.error == (text[0] == 'A' ? Error::NONE : Error::DIV_ZERO));
    assert(!memcmp(&saved, &state.control, sizeof(saved)));
    assert(state.stack[0] == 123 && variables[0] == 5 && array[2] == 8);
    assert(state.input_value == 13);
  }
  const auto compiled=compile_expression(Language::BASIC,"A",1,image,INPUT_IMAGE_CAPACITY);
  View view; assert(inspect(image,compiled.size,view)==Error::NONE);
  uint8_t saved_state[sizeof(state)];
  for (uint8_t sp : {INPUT_STACK_CAPACITY, MAX_STACK}) {
    state.control.sp = sp; memcpy(saved_state, &state, sizeof(state));
    const auto result=evaluate_input(view,state,bindings,{});
    assert(result.error==Error::INVALID_IMAGE && !memcmp(saved_state,&state,sizeof(state)));
  }
  state.control.sp=INPUT_STACK_CAPACITY-1;
  View oversized=view; oversized.stack=2;
  memcpy(saved_state,&state,sizeof(state));
  assert(evaluate_input(oversized,state,bindings,{}).error==Error::INVALID_IMAGE);
  assert(!memcmp(saved_state,&state,sizeof(state)));
  // The last lower slot is usable, and neither decoding nor a runtime stack
  // overflow may touch the adjacent immutable image.
  uint8_t saved_image[INPUT_IMAGE_CAPACITY]; memcpy(saved_image,image,sizeof(saved_image));
  assert(evaluate_input(view,state,bindings,{}).error==Error::NONE);
  assert(state.input_value==5 && state.control.sp==INPUT_STACK_CAPACITY-1);
  assert(!memcmp(saved_image,image,sizeof(saved_image)));
  const auto deep=compile_expression(Language::BASIC,"1+(1+1)",7,image,INPUT_IMAGE_CAPACITY);
  assert(deep.error==Error::NONE && inspect(image,deep.size,view)==Error::NONE);
  view.stack=1; // corrupt/understated metadata still meets run-time push bounds
  memcpy(saved_image,image,sizeof(saved_image));
  const Continuation before_overflow=state.control;
  assert(evaluate_input(view,state,bindings,{}).error==Error::STACK);
  assert(!memcmp(&before_overflow,&state.control,sizeof(before_overflow)));
  assert(state.input_value==5 && !memcmp(saved_image,image,sizeof(saved_image)));
}
void test_expression_whitelist() {
  const Op forbidden[] = {Op::STORE, Op::STORE_REF, Op::STORE_ARRAY, Op::JUMP,
      Op::JUMP_FALSE, Op::GOTO, Op::GOSUB, Op::RETURN, Op::FOR_BASIC,
      Op::NEXT_BASIC, Op::DO_FOCAL, Op::FOR_FOCAL, Op::NEXT_FOCAL, Op::BRANCH,
      Op::LINE, Op::READ_INPUT, Op::WAIT, Op::CLEAR, Op::PRINT_BEGIN,
      Op::PRINT_TEXT, Op::PRINT_NUMBER, Op::PRINT_FORMAT, Op::PRINT_SEPARATOR,
      Op::PRINT_FLUSH, Op::PRINT_END, Op::TARGET_ARRAY, Op::TARGET_REF};
  for (Op op : forbidden) {
    uint8_t image[128] = {};
    const auto c=compile_expression(Language::BASIC,".1+.2+.3",8,image,sizeof(image));
    assert(c.error==Error::NONE);
    image[HEADER_SIZE]=(uint8_t)op;
    const uint32_t crc=checksum(image+HEADER_SIZE,c.size-HEADER_SIZE);
    for(unsigned i=0;i<4;++i) image[20+i]=(uint8_t)(crc>>(8*i));
    View view; assert(inspect(image,c.size,view)==Error::INVALID_IMAGE);
  }
}
void test_program_stack_unchanged() {
  std::string expression = "1";
  for (unsigned i=0;i<INPUT_STACK_CAPACITY;++i) expression = "1+("+expression+")";
  const std::string source = "10 A="+expression+"\n";
  uint8_t image[MAX_IMAGE];
  const auto compiled=compile_basic(source.c_str(),(uint16_t)source.size(),image,sizeof(image),true);
  assert(compiled.error==Error::NONE && compiled.stack==INPUT_STACK_CAPACITY+1);
  View view; assert(inspect(image,compiled.size,view)==Error::NONE);
  Value variables[26]={}, stack[MAX_STACK]={};
  State state={}; state.variables=variables; state.stack=stack; state.stack_capacity=MAX_STACK;
  assert(run(view,state,{}).error==Error::NONE && variables[0]==INPUT_STACK_CAPACITY+1);
}
void test_cold_certificate() {
  uint8_t image[MAX_IMAGE];
  const char* source="10 A=1\n";
  const auto compiled=compile_basic(source,(uint16_t)strlen(source),image,sizeof(image),true);
  Value vars[26]={};
  ExecuteRequest execution={}; execution.size=sizeof(execution); execution.version=REQUEST_VERSION;
  execution.image=image; execution.image_size=compiled.size; execution.variables=vars; execution.mode=1;
  ExecutionState state={}; state.language=Language::BASIC;
  ValidatedImage metadata={};
  OverlayRequest request={sizeof(request),REQUEST_VERSION,&execution,&state,&metadata,
                           OverlayAction::START,{0,0,0}};
  assert(validate_execution(&request)==1 && execution.result.error==Error::NONE);
  View view; assert(validated_view(request,view) && view.size==compiled.size);
  metadata.magic=0; assert(!validated_view(request,view));
  assert(validate_execution(&request)==1);
  image[compiled.size-1]^=1;
  assert(validate_execution(&request)==1 && execution.result.error==Error::INVALID_IMAGE && !metadata.magic);
}
}
int main() {
  test_capacity(); test_borrowed_stack(); test_expression_whitelist(); test_cold_certificate();
  test_program_stack_unchanged();
  printf("language_vm_input: bound=%u maximum=%u, whitelist, borrowed stack, validation PASS\n",
         INPUT_IMAGE_CAPACITY, maximum);
}
