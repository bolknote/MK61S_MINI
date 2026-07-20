#ifndef STORAGE_PATH_HPP
#define STORAGE_PATH_HPP

#include "program_store.hpp"
#include "rust_types.h"

namespace storage_path {

// Видимое имя FAT состоит из 31-байтового базового имени C5, самого длинного
// создаваемого расширения (".state.txt") и завершающего нуля.
static constexpr usize VISIBLE_NAME_SIZE = program_store::NAME_SIZE + 16;

enum class Status : u8 {
  OK = 0,
  EMPTY,
  INVALID,
  TOO_LONG,
  NOT_FOUND,
  NOT_DIRECTORY,
  NOT_FILE,
  WRONG_TYPE,
  AMBIGUOUS,
  EXISTS,
  IO_ERROR,
  ROOT
};

struct FileTarget {
  u16 parent_id;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
};

const char* status_text(Status status);

// Создаёт видимое в FAT имя конечного компонента (базовое имя и расширение типа
// для файла). Результат также является канонической записью объекта в терминале.
bool visible_name(const program_store::Entry& entry, char* out, usize capacity);

// Пути допускают '/' и '\\', абсолютную или относительную запись, повторяющиеся
// разделители, '.' и '..'. Весь путь можно заключить в согласованные одинарные
// или двойные кавычки. При сравнении применяется простое, не зависящее от локали
// приведение регистра Unicode в стиле FAT для распространённых письменностей
// с регистром, включая кириллицу.
Status resolve_directory(u16 cwd, const char* path, u16& out_directory);
Status resolve_entry(u16 cwd, const char* path, program_store::Entry& out);
Status resolve_file(u16 cwd, const char* path, program_store::Entry& out);
Status resolve_file(u16 cwd, const char* path,
                    program_store::ProgramType required_type,
                    program_store::Entry& out);

// Разрешает часть пути с каталогом и проверяет конечное имя файла для создания
// или перезаписи. Если суффикс пропущен, используется default_type.
Status file_target(u16 cwd, const char* path,
                   program_store::ProgramType default_type,
                   FileTarget& out);

// Создаёт конечный каталог. При parents=true отсутствующие промежуточные
// компоненты создаются, как при `mkdir -p`.
Status create_directory(u16 cwd, const char* path, bool parents,
                        u16& out_directory);

// Реализует правила назначения mv в стиле командной оболочки: существующий
// каталог сохраняет исходное имя, иначе последний компонент становится
// новым именем.
Status move_target(u16 cwd, const program_store::Entry& source,
                   const char* destination, u16& out_parent,
                   char* out_name, usize name_capacity);

Status format_directory(u16 directory_id, char* out, usize capacity);
Status format_entry(const program_store::Entry& entry, char* out,
                    usize capacity);

// Возвращает true для самого каталога и всех вложенных в него каталогов.
bool directory_within(u16 directory_id, u16 ancestor_id);

} // пространство имён storage_path

#endif
