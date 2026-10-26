#ifndef MK61_TERMINAL_FRONT_CODING_HPP
#define MK61_TERMINAL_FRONT_CODING_HPP

#include "rust_types.h"

// Front coding for ordered, comma-separated mnemonic tables. Each record
// stores one control byte with the prefix length shared with the preceding
// mnemonic, followed by printable suffix bytes. 0x1F terminates the stream.
// This is deliberately simpler than a general compressor and permits the
// canonical CSV to remain the compile-time source of truth.
namespace terminal_front_coding {

static constexpr u8 END = 0x1FU;

template<usize N>
constexpr bool source_valid(const char (&table)[N]) {
  for(usize index = 0; index + 1U < N; index++) {
    const u8 value = (u8) table[index];
    if(value != ',' && value < 0x20U) return false;
  }
  return N != 0 && table[N - 1U] == 0;
}

template<usize N>
constexpr usize encoded_size(const char (&table)[N]) {
  usize result = 1; // END
  usize previous_begin = 0;
  usize previous_length = 0;
  usize current_begin = 0;
  bool have_previous = false;
  for(usize end = 0; end < N; end++) {
    if(table[end] != ',' && table[end] != 0) continue;
    const usize current_length = end - current_begin;
    usize prefix = 0;
    if(have_previous) {
      while(prefix < previous_length && prefix < current_length &&
            table[previous_begin + prefix] == table[current_begin + prefix]) {
        prefix++;
      }
    }
    result += 1U + current_length - prefix;
    previous_begin = current_begin;
    previous_length = current_length;
    have_previous = true;
    if(table[end] == 0) break;
    current_begin = end + 1U;
  }
  return result;
}

template<usize EncodedSize>
struct Table {
  u8 bytes[EncodedSize];
};

template<usize EncodedSize, usize N>
constexpr Table<EncodedSize> encode(const char (&table)[N]) {
  Table<EncodedSize> result = {};
  usize output = 0;
  usize previous_begin = 0;
  usize previous_length = 0;
  usize current_begin = 0;
  bool have_previous = false;
  for(usize end = 0; end < N; end++) {
    if(table[end] != ',' && table[end] != 0) continue;
    const usize current_length = end - current_begin;
    usize prefix = 0;
    if(have_previous) {
      while(prefix < previous_length && prefix < current_length &&
            table[previous_begin + prefix] == table[current_begin + prefix]) {
        prefix++;
      }
    }
    result.bytes[output++] = (u8) prefix;
    for(usize index = prefix; index < current_length; index++) {
      result.bytes[output++] = (u8) table[current_begin + index];
    }
    previous_begin = current_begin;
    previous_length = current_length;
    have_previous = true;
    if(table[end] == 0) break;
    current_begin = end + 1U;
  }
  result.bytes[output] = END;
  return result;
}

inline bool decode(const u8* input, usize input_size,
                   char* output, usize output_size) {
  if(input == nullptr || output == nullptr || output_size == 0) return false;
  usize source = 0;
  usize used = 0;
  usize previous_begin = 0;
  usize previous_length = 0;
  bool first = true;
  while(source < input_size) {
    const u8 prefix = input[source++];
    if(prefix == END) {
      if(used + 1U != output_size) return false;
      output[used] = 0;
      return true;
    }
    if(prefix >= END || prefix > previous_length) return false;
    if(!first) {
      if(used + 1U >= output_size) return false;
      output[used++] = ',';
    }
    const usize current_begin = used;
    for(usize index = 0; index < prefix; index++) {
      if(used + 1U >= output_size) return false;
      output[used++] = output[previous_begin + index];
    }
    while(source < input_size && input[source] >= 0x20U) {
      if(used + 1U >= output_size) return false;
      output[used++] = (char) input[source++];
    }
    previous_begin = current_begin;
    previous_length = used - current_begin;
    first = false;
  }
  return false;
}

} // namespace terminal_front_coding

#endif
