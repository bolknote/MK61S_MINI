#ifndef MK61_TINYBASIC_DIAGNOSTIC_HPP
#define MK61_TINYBASIC_DIAGNOSTIC_HPP
#include "language_bytecode.hpp"
#include "mk8_literal.hpp"
namespace tinybasic_diagnostic {
using language_vm::Error;
struct Location {
  uint16_t line, column, offset;
};
inline Location locate(const char* source, uint16_t offset) {
  const char* p = source + offset;
  while (p > source && p[-1] != '\n' && p[-1] != '\r') --p;
  const char* begin = p;
  while (*p == ' ' || *p == '\t') ++p;
  uint16_t number = 0;
  while (*p >= '0' && *p <= '9') {
    number = (uint16_t)(number * 10 + *p - '0');
    ++p;
  }
  return {number, (uint16_t)(source + offset - begin + 1), offset};
}
inline const char* reason(Error error, bool russian = false) {
  switch (error) {
    case Error::DIV_ZERO:
      return russian ? M8("ДЕЛЕНИЕ НА НОЛЬ") : "DIV BY ZERO";
    case Error::ARRAY_RANGE:
      return russian ? M8("ИНДЕКС МАССИВА") : "ARRAY INDEX";
    case Error::DATA_END:
      return russian ? M8("КОНЕЦ DATA") : "OUT OF DATA";
    case Error::ON_INDEX:
      return russian ? M8("ИНДЕКС ON") : "BAD ON INDEX";
    case Error::MISSING_LINE:
      return russian ? M8("НЕТ СТРОКИ") : "NO SUCH LINE";
    case Error::LINE_NUMBER:
    case Error::LINE:
      return russian ? M8("НОМЕР СТРОКИ") : "LINE NUMBER";
    case Error::RETURN:
      return russian ? M8("RETURN БЕЗ GOSUB") : "RETURN NO GOSUB";
    case Error::NEXT_WITHOUT_FOR:
    case Error::FOR:
      return russian ? M8("НЕТ ПАРЫ FOR/NEXT") : "FOR/NEXT PAIR";
    case Error::CALL_STACK:
      return russian ? M8("СТЕК GOSUB ПОЛОН") : "GOSUB STACK FULL";
    case Error::LOOP_STACK:
      return russian ? M8("СТЕК FOR ПОЛОН") : "FOR STACK FULL";
    case Error::STACK:
      return russian ? M8("СТЕК ПОЛОН") : "STACK FULL";
    case Error::MATH:
      return russian ? M8("ОШИБКА МАТЕМАТИКИ") : "MATH DOMAIN";
    case Error::REGISTER:
      return russian ? M8("НЕДОСТУПЕН РЕГИСТР") : "BAD REGISTER";
    case Error::FORMAT:
      return russian ? M8("ШИРИНА PRINT") : "PRINT WIDTH";
    case Error::UNKNOWN_COMMAND:
      return russian ? M8("НЕИЗВЕСТНАЯ КОМАНДА") : "UNKNOWN COMMAND";
    case Error::FUNCTION:
      return russian ? M8("ОШИБКА ФУНКЦИИ") : "BAD FUNCTION";
    case Error::UNTERMINATED_STRING:
      return russian ? M8("НЕ ЗАКРЫТЫ КАВЫЧКИ") : "UNCLOSED STRING";
    case Error::EXPECTED_PAREN:
      return russian ? M8("НУЖНА СКОБКА )") : "EXPECTED )";
    case Error::STOPPED:
      return russian ? M8("ОСТАНОВЛЕНО") : "STOPPED";
    case Error::IO:
      return russian ? M8("ВВОД/ВЫВОД") : "INPUT/OUTPUT";
    case Error::VARIABLE:
      return russian ? M8("ОШИБКА ПЕРЕМЕННОЙ") : "BAD VARIABLE";
    case Error::INVALID_IMAGE:
      return russian ? M8("ОШИБКА ПРОГРАММЫ") : "BAD PROGRAM";
    case Error::FULL:
      return russian ? M8("НЕТ МЕСТА") : "NO MEMORY";
    default:
      return russian ? M8("ОШИБКА СИНТАКСИСА") : "SYNTAX";
  }
}
}  // namespace tinybasic_diagnostic
#endif
