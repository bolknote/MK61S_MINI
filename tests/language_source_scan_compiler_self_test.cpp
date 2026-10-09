#include "language_bytecode.hpp"
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <string>
#include <vector>

using namespace language_vm;
static std::vector<uint8_t> image(Language language, const std::string& source,
                                  const ResourceSource* resources) {
  std::vector<uint8_t> output(MAX_MODULE);
  const auto size = compile(language, source.c_str(), (uint16_t)source.size(),
                            nullptr, (uint16_t)output.size(), true, resources);
  assert(size.error == Error::NONE);
  const auto emitted = compile(language, source.c_str(), (uint16_t)source.size(),
                               output.data(), (uint16_t)output.size(), true, resources);
  assert(emitted.error == Error::NONE && emitted.size == size.size);
  View view;
  assert(inspect(output.data(), emitted.size, view) == Error::NONE);
  assert(view.source_size == source.size());
  assert(checksum((const uint8_t*)source.data(), (uint16_t)source.size()) ==
         (uint32_t)(output[16] | (uint32_t)output[17] << 8 |
                    (uint32_t)output[18] << 16 | (uint32_t)output[19] << 24));
  output.resize(emitted.size);
  // Source length/CRC necessarily differ when only the physical separators
  // change. Code, line tables, diagnostic columns and owned resources do not.
  memset(output.data() + 14, 0, 6);
  return output;
}
static std::string endings(const char* input, const char* delimiter) {
  std::string result;
  for(const char* p = input; *p; ++p)
    if(*p == '\n') result += delimiter; else result += *p;
  return result;
}
int main() {
  ResourceSource owned = {42, 1}; owned.mode = ResourceMode::EMBEDDED;
  for(Language language : {Language::BASIC, Language::FOCAL}) {
    const char* valid = language == Language::BASIC
        ? "10 DATA 1,2\n20 READ B,C\n30 PRINT \"M8 \x80\xFF\";A=B+C\n40 END\n"
        : "1.10 S A=1\n1.20 P \"M8 \x80\xFF\"\n1.30 E\n";
    std::vector<const char*> programs = {valid};
    if(language == Language::FOCAL) {
      // Exercise the rewritten compiler rather than just the legacy subset:
      // arrays, a result-bearing call, parameters, statement lists, formats
      // and an M8 literal containing a statement separator.
      programs.push_back("1.10 S A(1,2)=7; S X=CALL(2,A(1,2)); P \"M8; \x80\xFF\",!,%8.3,X; E\n"
                         "2.10 R ARG(1)+MIN(3,5)\n");
    }
    for(const char* program : programs) {
      for(const ResourceSource* resources : {static_cast<const ResourceSource*>(nullptr),
                                           static_cast<const ResourceSource*>(&owned)}) {
        const auto expected = image(language, program, resources);
        for(const char* delimiter : {"\n", "\r", "\r\n", "\n\r"}) {
          std::string source = endings(program, delimiter);
          assert(image(language, source, resources) == expected);
          // Repeated/empty lines and a final line without CR/LF preserve the
          // former skip-delimiters and physical-column semantics.
          assert(image(language, std::string(delimiter) + delimiter + source + delimiter,
                       resources) == expected);
          source.resize(source.size() - strlen(delimiter));
          assert(image(language, source, resources) == expected);
        }
      }
    }
    uint8_t output[MAX_MODULE];
    const auto empty = compile(language, "\r\n\r\n", 4, output, sizeof(output));
    assert(empty.error == Error::LINE);
    std::string nul(valid); nul[nul.size() / 2] = 0;
    assert(compile(language, nul.data(), (uint16_t)nul.size(), output, sizeof(output)).error == Error::SYNTAX);
    for(const char* delimiter : {"\n", "\r", "\r\n", "\n\r"}) {
      const char* invalid = language == Language::BASIC ? "10 A=1\n20 A=?\n" : "1.10 S A=1\n1.20 S A=?\n";
      const std::string source = endings(invalid, delimiter);
      const auto error = compile(language, source.c_str(), (uint16_t)source.size(), output, sizeof(output));
      assert(error.error == Error::SYNTAX);
      // Preserve the two existing parser cursor conventions: BASIC consumes
      // the bad token, FOCAL leaves the cursor at it.
      assert(error.source_offset == source.find('?') + (language == Language::BASIC));
    }
  }
  for(const char* delimiter : {"\n", "\r", "\r\n", "\n\r"}) {
    const std::string source = std::string(delimiter) + endings(
        "1.10 S X=1\n1.20   S A(-1)=7\n", delimiter);
    uint8_t output[MAX_IMAGE];
    const auto compiled = compile(Language::FOCAL, source.data(),
                                  (uint16_t)source.size(), output, sizeof(output));
    assert(compiled.error == Error::NONE);
    View view;
    assert(inspect(output, compiled.size, view) == Error::NONE);
    State state = {};
    Value variables[26] = {}, array[64] = {}, stack[MAX_STACK] = {};
    state.variables = variables; state.array = array; state.array_count = 64;
    state.stack = stack; state.stack_capacity = MAX_STACK;
    const auto result = run(view, state, Services{}, 256);
    assert(result.error == Error::ARRAY_RANGE && result.line == 1020);
    assert(source_column(view, result.pc) == 8);
  }
  puts("BASIC/FOCAL CR/LF: sizing/EMIT, bytecode, resources, blank/final lines and diagnostics PASS");
}
