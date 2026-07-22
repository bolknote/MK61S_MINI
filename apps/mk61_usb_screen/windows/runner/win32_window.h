#ifndef RUNNER_WIN32_WINDOW_H_
#define RUNNER_WIN32_WINDOW_H_

#include <windows.h>

#include <functional>
#include <memory>
#include <string>

// Абстракция окна Win32 с поддержкой высокого DPI. Предназначена для наследования
// классами, которым нужны особая отрисовка и обработка ввода.
class Win32Window {
 public:
  struct Point {
    unsigned int x;
    unsigned int y;
    Point(unsigned int x, unsigned int y) : x(x), y(y) {}
  };

  struct Size {
    unsigned int width;
    unsigned int height;
    Size(unsigned int width, unsigned int height)
        : width(width), height(height) {}
  };

  Win32Window();
  virtual ~Win32Window();

  // Создаёт окно Win32 с заголовком |title|, положением |origin| и размером
  // |size|. Новые окна создаются на мониторе по умолчанию. ОС получает размеры
  // в физических пикселях, поэтому для постоянного размера функция масштабирует
  // переданные ширину и высоту под монитор по умолчанию. Окно невидимо до вызова
  // |Show|. При успешном создании возвращает true.
  bool Create(const std::wstring& title, const Point& origin, const Size& size);

  // Показывает текущее окно. При успешном показе возвращает true.
  bool Show();

  // Освобождает связанные с окном ресурсы ОС.
  void Destroy();

  // Вставляет |content| в дерево окна.
  void SetChildContent(HWND content);

  // Возвращает базовый дескриптор окна, чтобы клиенты могли задать значок и
  // другие свойства. Если окно уничтожено, возвращает nullptr.
  HWND GetHandle();

  // При true закрытие этого окна завершает приложение.
  void SetQuitOnClose(bool quit_on_close);

  // Возвращает RECT с границами текущей клиентской области.
  RECT GetClientArea();

 protected:
  // Обрабатывает и направляет важные сообщения окна для мыши, изменения размера
  // и DPI. Передаёт их перегруженным методам, доступным классам-наследникам.
  virtual LRESULT MessageHandler(HWND window,
                                 UINT const message,
                                 WPARAM const wparam,
                                 LPARAM const lparam) noexcept;

  // Вызывается из CreateAndShow и позволяет подклассу настроить окно.
  // При ошибке настройки подкласс должен вернуть false.
  virtual bool OnCreate();

  // Вызывается из Destroy.
  virtual void OnDestroy();

 private:
  friend class WindowClassRegistrar;

  // Обратный вызов ОС из цикла сообщений. Обрабатывает WM_NCCREATE, передаваемое
  // при создании неклиентской области, и включает её автоматическое масштабирование
  // DPI, чтобы область реагировала на изменение DPI. Все остальные сообщения
  // обрабатывает MessageHandler.
  static LRESULT CALLBACK WndProc(HWND const window,
                                  UINT const message,
                                  WPARAM const wparam,
                                  LPARAM const lparam) noexcept;

  // Получает указатель на экземпляр класса для |window|.
  static Win32Window* GetThisFromHandle(HWND const window) noexcept;

  // Обновляет тему рамки окна в соответствии с системной темой.
  static void UpdateTheme(HWND const window);

  bool quit_on_close_ = false;

  // Дескриптор окна верхнего уровня.
  HWND window_handle_ = nullptr;

  // Дескриптор окна размещённого содержимого.
  HWND child_content_ = nullptr;
};

#endif  // RUNNER_WIN32_WINDOW_H_
