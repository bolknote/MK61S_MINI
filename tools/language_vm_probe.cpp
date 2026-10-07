#include <stdio.h>
#include <string.h>

#include <vector>

#include "language_bytecode.hpp"
#include "zx0.hpp"

static unsigned compressed(const uint8_t* bytes, size_t length, size_t workspace) {
  std::vector<uint8_t> temporary(workspace);
  zx0::Prepared prepared = {};
  return zx0::prepare(bytes, (uint32_t)length, temporary.data(), temporary.size(),
                      prepared)
             ? prepared.output_size
             : 0;
}
int main(int argc, char** argv) {
  if ((argc != 4 && argc != 5) || (strcmp(argv[1], "basic") && strcmp(argv[1], "focal"))) return 2;
  FILE* input = fopen(argv[2], "rb");
  if (!input) return 2;
  std::vector<uint8_t> source(3585);
  const size_t n = fread(source.data(), 1, source.size(), input);
  const bool error = ferror(input) || fgetc(input) != EOF;
  fclose(input);
  if (error || n >= source.size()) return 2;
  source[n] = 0;
  std::vector<uint8_t> image(language_vm::MAX_IMAGE);
  const auto language = strcmp(argv[1], "basic") == 0 ? language_vm::Language::BASIC
                                                      : language_vm::Language::FOCAL;
  const language_vm::ResourceSource resources = {42,1};
  const bool external = argc == 5 && strcmp(argv[4], "--source-resources") == 0;
  if(argc == 5 && !external) return 2;
  const auto result =
      language_vm::compile(language, (const char*)source.data(), (uint16_t)n,
                           image.data(), (uint16_t)image.size(), true, external ? &resources : nullptr);
  if (result.error != language_vm::Error::NONE) {
    fprintf(stderr, "%s:%u: %s\n", argv[2], result.source_offset,
            language_vm::error_name(result.error));
    return 1;
  }
  language_vm::View view;
  if (language_vm::inspect(image.data(), result.size, view) != language_vm::Error::NONE)
    return 1;
  FILE* output = fopen(argv[3], "wb");
  if (!output) return 2;
  const size_t written = fwrite(image.data(), 1, result.size, output);
  const int closed = fclose(output);
  if (written != result.size || closed) return 2;
  unsigned count = 0;
  for(uint16_t at=view.end; at<view.size; at += (uint16_t)(3+image[at+2]*3)) ++count;
  printf(
      "{\"source_bytes\":%zu,\"bytecode_bytes\":%u,\"lines\":%u,\"stack_values\":%u,"
      "\"code_bytes\":%u,\"resource_recipe_bytes\":%u,\"resource_count\":%u,"
      "\"source_zx0_bounded\":%u,\"bytecode_zx0_bounded\":%u,"
      "\"source_zx0_scratch\":%u,\"bytecode_zx0_scratch\":%u}\n",
      n, result.size, view.lines, view.stack, view.end, view.size-view.end, count, compressed(source.data(), n, 4 * (n + 1)),
      compressed(image.data(), result.size, 4 * (result.size + 1)),
      compressed(source.data(), n, 1600), compressed(image.data(), result.size, 1600));
}
