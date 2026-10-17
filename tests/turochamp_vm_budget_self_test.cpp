// Compile the actual UTF-8 package with the shipping bounded VM compiler.
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
#include "language_bytecode.hpp"
#include "mk8_codec.hpp"

int main(int argc, char** argv) {
  static_assert(language_vm::MAX_IMAGE == 6144, "chess must not raise the VM code budget");
  static_assert(language_vm::MAX_STACK == 96 && language_vm::MAX_CALLS == 16 &&
                language_vm::MAX_LOOPS == 16, "chess must not raise VM stack budgets");
  assert(argc > 1);
  unsigned largest = 0;
  for(int index = 1; index < argc; ++index) {
    std::ifstream file(argv[index], std::ios::binary);
    assert(file);
    const std::string utf8(std::istreambuf_iterator<char>(file), {});
    std::vector<uint8_t> source(utf8.size()+1);
    usize length = 0;
    assert(mk8::from_utf8((const uint8_t*)utf8.data(), utf8.size(),
                         source.data(), source.size()-1, length));
    assert(length > 0 && length <= language_vm::source::MAX_SIZE);
    source[length] = 0;
    uint8_t image[language_vm::MAX_IMAGE];
    const auto compiled = language_vm::compile(language_vm::Language::BASIC,
        (const char*)source.data(), (uint16_t)length, image, sizeof(image));
    if(compiled.error != language_vm::Error::NONE) {
      std::cerr << argv[index] << ':' << compiled.source_offset << ' '
                << language_vm::error_name(compiled.error) << '\n';
      return 1;
    }
    language_vm::View view;
    assert(language_vm::inspect(image, compiled.size, view) == language_vm::Error::NONE);
    assert(view.lines <= 192 && view.stack <= language_vm::MAX_STACK);
    struct Input {
      const std::vector<uint8_t>& source;
      unsigned calls=0;
      static bool read(void* raw,uint16_t at,uint8_t* output,uint16_t count) {
        auto& input=*static_cast<Input*>(raw);++input.calls;
        assert(count<=3784 && at+unsigned(count)<input.source.size());
        memcpy(output,input.source.data()+at,count);return true;
      }
    } input{source};
    uint8_t loan[3786];memset(loan,0x5A,sizeof(loan));
    language_vm::source::Reader reader({&input,Input::read,uint16_t(length)},loan+1,3784);
    uint8_t window_image[language_vm::MAX_IMAGE];
    const auto windowed=language_vm::compile_source(language_vm::Language::BASIC,reader,
        window_image,sizeof(window_image));
    assert(windowed.error==language_vm::Error::NONE && windowed.size==compiled.size);
    assert(!memcmp(image,window_image,compiled.size) && loan[0]==0x5A && loan[3785]==0x5A);
    if(length>3784)
      std::cout << "Turochamp source window: " << argv[index] << " M8=" << length
                << " reads=" << input.calls << " byte-exact PASS\n";
    if(compiled.size > largest) largest = compiled.size;
  }
  std::cout << "Turochamp VM budget: " << argc-1 << " files, largest " << largest
            << "/6144 bytes, byte-exact borrowed-window compilation, source/line/stack limits unchanged PASS\n";
}
