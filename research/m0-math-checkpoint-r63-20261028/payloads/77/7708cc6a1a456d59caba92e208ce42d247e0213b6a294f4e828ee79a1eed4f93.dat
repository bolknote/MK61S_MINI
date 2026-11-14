#ifndef BOUNDED_STRING_HPP
#define BOUNDED_STRING_HPP

#include "rust_types.h"

#include <string.h>

namespace bounded_string {

// Копирует строку с гарантированным завершающим нулём. В отличие от strncpy,
// не заполняет нулями весь остаток буфера и корректно обрабатывает перекрытие.
// Возвращает число записанных байтов без завершающего нуля.
inline usize copy(char* destination, usize capacity, const char* source) {
  if(destination == NULL || capacity == 0) return 0;
  if(source == NULL) {
    destination[0] = 0;
    return 0;
  }

  const usize limit = capacity - 1;
  usize length = 0;
  while(length < limit && source[length] != 0) length++;
  if(length != 0) memmove(destination, source, length);
  destination[length] = 0;
  return length;
}

template<usize N>
inline usize copy(char (&destination)[N], const char* source) {
  return copy(destination, N, source);
}

} // пространство имён bounded_string

#endif
