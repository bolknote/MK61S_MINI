#ifndef MK61_PICOCALC_TERMINAL_HPP
#define MK61_PICOCALC_TERMINAL_HPP
#include "services.hpp"
#include "terminal_core.hpp"
#include "terminal_line_editor.hpp"
namespace picocalc {
class Terminal {
public:
  struct Backend {
    void *context = nullptr;
    void (*write)(void *, const char *, unsigned) = nullptr;
    void (*service)(void *) = nullptr;
    bool (*board_command)(void *, u8, const char *) = nullptr;
  };
  Terminal(Calculator &calculator, Services &services, Ui &ui)
      : calculator_(calculator), services_(services), ui_(ui) {}
  ~Terminal();
  void init(Backend backend) { backend_ = backend; }
  // Command mode is the default. RS forces legacy raw keys; US restores
  // commands; GS toggles. Framed USB Screen traffic is decoded before this.
  int receive(u8 byte);
  void tick();
  bool pending() const { return pending_; }
  bool raw() const { return raw_; }
  bool reading_keys() const { return executing_; }
  bool execute(const char *m8_line);
  const char *directory() const { return directory_; }

private:
  void out(const char *format, ...);
  void m8(const char *text);
  void path_text(const char *text);
  void redraw();
  void remember();
  void navigate(int delta);
  bool path(const char *&args, char out[files::PATH_SIZE]);
  bool remove_tree(const char *path, unsigned depth = 0);
  bool get(const char *args);
  bool put(const char *args);
  void cancel_upload();
  bool script_command(const char *line);
  Calculator &calculator_;
  Services &services_;
  Ui &ui_;
  Backend backend_{};
  terminal_line_editor::EscapeDecoder escape_;
  u8 line_[terminal_core::INPUT_CAPACITY]{};
  usize length_ = 0, cursor_ = 0;
  char history_[8][terminal_core::INPUT_CAPACITY]{},
      saved_[terminal_core::INPUT_CAPACITY]{};
  unsigned history_count_ = 0;
  int navigation_ = -1;
  bool raw_ = false, pending_ = false, executing_ = false, cr_ = false,
       overflow_ = false;
  u8 confirmation_ = 0;
  char directory_[files::PATH_SIZE] = "/";
  files::WriteSession *upload_ = nullptr;
  u32 upload_size_ = 0, upload_used_ = 0, upload_crc_ = 0, upload_running_crc_ = 0, upload_revision_ = 0;
};
} // namespace picocalc
#endif
