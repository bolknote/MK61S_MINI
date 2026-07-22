#ifndef RUNNER_UTILS_H_
#define RUNNER_UTILS_H_

#include <string>
#include <vector>

// Создаёт консоль процесса и перенаправляет в неё stdout и stderr как
// исполнителя, так и библиотеки Flutter.
void CreateAndAttachConsole();

// Принимает завершённую нулём строку wchar_t* в UTF-16 и возвращает std::string
// в UTF-8. При ошибке возвращает пустую std::string.
std::string Utf8FromUtf16(const wchar_t* utf16_string);

// Возвращает переданные аргументы командной строки как std::vector<std::string>
// в UTF-8. При ошибке возвращает пустой std::vector<std::string>.
std::vector<std::string> GetCommandLineArguments();

#endif  // RUNNER_UTILS_H_
