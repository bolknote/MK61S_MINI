#include "terminal.hpp"
#include "m61_platform.hpp"
#include "mk8_codec.hpp"
#include "script.hpp"
#include "terminal_catalog.hpp"
#include "terminal_encoding.hpp"
#include "terminal_file_transfer.hpp"
#include "terminal_script.hpp"
#include "diagnostics.hpp"
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
namespace picocalc {
namespace {
bool utf8(const char *input, char *out, unsigned capacity) {
  usize n = 0;
  if (!mk8::to_utf8((const u8 *)input, std::strlen(input), (u8 *)out,
                    capacity - 1, n))
    return false;
  out[n] = 0;
  return true;
}
bool slot_number(const char *args, unsigned &slot) {
  slot = 0;
  unsigned digits = 0;
  while (*args >= '0' && *args <= '9') {
    slot = slot * 10 + *args++ - '0';
    if (++digits > 2)
      return false;
  }
  return digits && slot <= 99 && terminal_core::at_end(args);
}
} // namespace
Terminal::~Terminal() { cancel_upload(); }
void Terminal::out(const char *format, ...) {
  char text[512];
  va_list args;
  va_start(args, format);
  const int n = std::vsnprintf(text, sizeof(text), format, args);
  va_end(args);
  if (n > 0 && backend_.write)
    backend_.write(backend_.context, text,
                   (unsigned)n < sizeof(text) ? (unsigned)n : sizeof(text) - 1);
}
void Terminal::m8(const char *text) {
  struct Chunk {
    Terminal *self;
    char bytes[128];
    unsigned used = 0;
  } chunk{this, {}, 0};
  terminal_encoding::write_m8(
      text,
      [](u8 byte, void *raw) {
        auto &chunk = *(Chunk *)raw;
        chunk.bytes[chunk.used++] = (char)byte;
        if (chunk.used == sizeof(chunk.bytes)) {
          if (chunk.self->backend_.write)
            chunk.self->backend_.write(chunk.self->backend_.context,
                                       chunk.bytes, chunk.used);
          chunk.used = 0;
        }
        return true;
      },
      &chunk);
  if (chunk.used && backend_.write)
    backend_.write(backend_.context, chunk.bytes, chunk.used);
}
void Terminal::path_text(const char *text) {
  u8 bytes[files::PATH_SIZE];
  usize n = 0;
  if (mk8::from_utf8((const u8 *)text, std::strlen(text), bytes,
                     sizeof(bytes) - 1, n)) {
    bytes[n] = 0;
    m8((const char *)bytes);
  }
}
void Terminal::redraw() {
  out("\r\033[2Kmk61> ");
  m8((const char *)line_);
  if (cursor_ < length_)
    out("\033[%uD", (unsigned)(length_ - cursor_));
}
void Terminal::remember() {
  if (!length_ || (history_count_ &&
                   !std::strcmp(history_[history_count_ - 1], (char *)line_)))
    return;
  if (history_count_ == 8) {
    std::memmove(history_, history_ + 1, 7 * sizeof(history_[0]));
    --history_count_;
  }
  std::strcpy(history_[history_count_++], (char *)line_);
}
void Terminal::navigate(int delta) {
  if (!history_count_)
    return;
  if (navigation_ < 0)
    std::strcpy(saved_, (char *)line_);
  const int next = navigation_ + delta;
  if (next < -1 || next >= (int)history_count_)
    return;
  navigation_ = next;
  std::strcpy((char *)line_,
              next < 0 ? saved_ : history_[history_count_ - 1 - next]);
  length_ = cursor_ = std::strlen((char *)line_);
  redraw();
}
int Terminal::receive(u8 byte) {
  if (byte == 0x1D || byte == 0x1E || byte == 0x1F) {
    raw_ = byte == 0x1D ? !raw_ : byte == 0x1E;
    pending_ = overflow_ = false;
    length_ = cursor_ = 0;
    line_[0] = 0;
    escape_.reset();
    cr_ = false;
    if (!raw_)
      out("\r\nMK61S PicoCalc terminal; help; raw = keyboard\r\nmk61> ");
    return -1;
  }
  if (raw_ || executing_)
    return byte;
  if (pending_)
    return -1;
  terminal_line_editor::Key key;
  if (escape_.feed(byte, key)) {
    using K = terminal_line_editor::Key;
    if (key == K::UP)
      navigate(1);
    else if (key == K::DOWN)
      navigate(-1);
    else {
      if (key == K::LEFT)
        terminal_line_editor::move_left(line_, length_, cursor_);
      if (key == K::RIGHT)
        terminal_line_editor::move_right(line_, length_, cursor_);
      if (key == K::HOME)
        cursor_ = 0;
      if (key == K::END)
        cursor_ = length_;
      if (key == K::DELETE_FORWARD)
        terminal_line_editor::delete_forward(line_, length_, cursor_,
                                             sizeof(line_));
      if (key != K::NONE)
        redraw();
    }
    return -1;
  }
  if (byte == '\r' || byte == '\n') {
    if (byte == '\n' && cr_) {
      cr_ = false;
      return -1;
    }
    cr_ = byte == '\r';
    out("\r\n");
    pending_ = true;
    return -1;
  }
  cr_ = false;
  if (byte == 3) {
    cancel_upload();
    length_ = cursor_ = 0;
    line_[0] = 0;
    overflow_ = false;
    confirmation_ = 0;
    redraw();
    return -1;
  }
  if (byte == 8 || byte == 127) {
    terminal_line_editor::backspace(line_, length_, cursor_, sizeof(line_));
    redraw();
    return -1;
  }
  if (byte < 32)
    return -1;
  byte = terminal_encoding::input_byte(byte);
  const bool append = cursor_ == length_;
  if (!terminal_line_editor::insert_byte(line_, length_, cursor_, sizeof(line_),
                                         byte)) {
    overflow_ = true;
    out("\a");
  } else if (append) {
    const char text[] = {(char)byte, 0};
    m8(text);
  } else
    redraw();
  return -1;
}
void Terminal::tick() {
  if (!pending_)
    return;
  pending_ = false;
  executing_ = true;
  if (overflow_)
    out("ERROR: command too long\r\n");
  else {
    remember();
    if (length_ && !execute((const char *)line_))
      out("ERROR\r\n");
  }
  executing_ = false;
  length_ = cursor_ = 0;
  line_[0] = 0;
  navigation_ = -1;
  overflow_ = false;
  if (!raw_)
    out("mk61> ");
}
bool Terminal::path(const char *&args, char out_path[files::PATH_SIZE]) {
  char name[240], encoded[files::PATH_SIZE];
  return terminal_core::parse_token(args, name, sizeof(name)) &&
         utf8(name, encoded, sizeof(encoded)) &&
         script::normalize_path(directory_, encoded, out_path);
}
void Terminal::cancel_upload() {
  files::cancel_write(upload_);
  upload_size_ = upload_used_ = upload_running_crc_ = 0;
}
bool Terminal::get(const char *args) {
  char name[files::PATH_SIZE];
  files::Entry entry;
  if (!path(args, name)) return false;
  args=terminal_core::skip_spaces(args);
  const bool m8=!std::strncmp(args,"m8",2) && terminal_core::at_end(args+2);
  if ((!terminal_core::at_end(args) && !m8) ||
      !files::stat(name, entry) || entry.directory || (!m8 && entry.size > 65534))
    return false;
  program_store::Entry logical{};
  if(m8 && (!program_store::text_content(script::file_type(name)) || !script::register_file(name,logical))) return false;
  const u32 size=m8?logical.data_len:entry.size;
  const auto read=[&](u32 at,u8* bytes,unsigned n,unsigned& used) {
    if(!m8) return files::read_range(name,at,bytes,n,used);
    u16 count=0;const bool ok=program_store::read_range_id(logical.id,(u16)at,bytes,(u16)n,&count);
    used=count;return ok;
  };
  const u32 revision = files::revision();
  u32 crc = 0;
  u8 bytes[96];
  unsigned used;
  for (u32 at = 0; at < size;) {
    const unsigned n =
        size - at < sizeof(bytes) ? size - at : sizeof(bytes);
    if (!read(at, bytes, n, used) || used != n ||
        files::revision() != revision)
      return false;
    for (unsigned i = 0; i < n; ++i)
      crc = terminal_file_transfer::checksum_update(crc, bytes[i]);
    at += n;
    if (backend_.service)
      backend_.service(backend_.context);
  }
  crc = terminal_file_transfer::checksum_finish(crc, size);
  out("@MKC:GET %lu %lu\r\n", (unsigned long)size, (unsigned long)crc);
  for (u32 at = 0; at < size;) {
    const unsigned n =
        size - at < sizeof(bytes) ? size - at : sizeof(bytes);
    char hex[193];
    if (!read(at, bytes, n, used) || used != n ||
        files::revision() != revision)
      return false;
    for (unsigned i = 0; i < n; ++i) {
      hex[i * 2] = terminal_file_transfer::hex_char(bytes[i] >> 4);
      hex[i * 2 + 1] = terminal_file_transfer::hex_char(bytes[i] & 15);
    }
    hex[n * 2] = 0;
    out("@MKC:DATA %lu %s\r\n", (unsigned long)at, hex);
    at += n;
    if (backend_.service)
      backend_.service(backend_.context);
  }
  out("@MKC:END %lu %lu\r\n", (unsigned long)size, (unsigned long)crc);
  return true;
}
bool Terminal::put(const char *args) {
  char action[16];
  if (!terminal_core::parse_token(args, action, sizeof(action)))
    return false;
  if (!std::strcmp(action, "cancel") && terminal_core::at_end(args)) {
    cancel_upload();
    out("@MKC:CANCELLED\r\n");
    return true;
  }
  if (!std::strcmp(action, "begin")) {
    char name[files::PATH_SIZE];
    usize size = 0, crc = 0;
    if (!path(args, name) ||
        !terminal_core::parse_unsigned(args, 10, 65534, size) ||
        !terminal_core::parse_unsigned(args, 10, UINT32_MAX, crc) || files::usb_active())
      return false;
    args=terminal_core::skip_spaces(args);
    const bool m8=!std::strncmp(args,"m8",2) && terminal_core::at_end(args+2);
    if((!terminal_core::at_end(args) && !m8) ||
       (m8 && !program_store::text_content(script::file_type(name)))) return false;
    cancel_upload();
    upload_ = files::begin_write(name,m8);
    if (!upload_)
      return false;
    upload_size_ = (u32)size;
    upload_crc_ = (u32)crc;
    upload_running_crc_=0;
    upload_revision_ = files::revision();
    out("@MKC:READY %lu\r\n", (unsigned long)size);
    return true;
  }
  if (!upload_ || files::usb_active() ||
      upload_revision_ != files::revision()) {
    cancel_upload();
    out("@MKC:ERROR PUT_INTERRUPTED\r\n");
    return false;
  }
  if (!std::strcmp(action, "data")) {
    usize offset = 0, n = 0;
    char hex[193];
    u8 data[96];
    if (!terminal_core::parse_unsigned(args, 10, 65534, offset) ||
        !terminal_core::parse_token(args, hex, sizeof(hex)) ||
        !terminal_core::at_end(args) ||
        !terminal_file_transfer::decode_hex(hex, data, sizeof(data), n) || !n ||
        offset != upload_used_ || n > upload_size_ - upload_used_)
      return false;
    if(!files::append_write(upload_,data,n)) { cancel_upload();return false; }
    for(unsigned i=0;i<n;++i) upload_running_crc_=terminal_file_transfer::checksum_update(upload_running_crc_,data[i]);
    upload_used_ += n;
    out("@MKC:ACK %lu\r\n", (unsigned long)upload_used_);
    return true;
  }
  if (std::strcmp(action, "end") || !terminal_core::at_end(args) ||
      upload_used_ != upload_size_)
    return false;
  const u32 crc = terminal_file_transfer::checksum_finish(upload_running_crc_, upload_size_);
  if (crc != upload_crc_) {
    cancel_upload();
    out("@MKC:ERROR PUT_CHECKSUM\r\n");
    return false;
  }
  if (!files::commit_write(upload_))
    return false;
  out("@MKC:DONE %lu %lu\r\n", (unsigned long)upload_size_, (unsigned long)crc);
  cancel_upload();
  return true;
}
bool Terminal::remove_tree(const char *name, unsigned depth) {
  if (depth > 16 || !std::strcmp(name, "/"))
    return false;
  files::Entry info;
  if (!files::stat(name, info))
    return false;
  if (info.directory)
    for (;;) {
      unsigned used = 0;
      bool more;
      files::Entry child;
      if (!files::list(name, 0, &child, 1, used, more))
        return false;
      if (!used)
        break;
      char path[files::PATH_SIZE];
      if (!script::normalize_path(name, child.name, path) ||
          !remove_tree(path, depth + 1))
        return false;
      if (backend_.service)
        backend_.service(backend_.context);
    }
  return files::remove(name);
}
bool Terminal::script_command(const char *line) {
  const auto result = terminal_script::execute(line);
  using K = terminal_protocol::ResultKind;
  switch (result.kind) {
  case K::OK:
    return true;
  case K::RUN_PROGRAM:
    hidden_start_loaded_program((u8)result.key);
    return true;
  case K::REINIT_CALCULATOR:
    m61_text::cancel();
    reinit_mk61_calculator_state();
    return true;
  case K::LOAD_BINARY: {
    program_store::Entry directory;
    return script::register_file(directory_, directory) &&
           load_binary_program(directory.id, result.args);
  }
  case K::LOAD_SLOT: {
    unsigned slot;
    char name[16];
    if (upload_ || !slot_number(result.args, slot))
      return false;
    std::snprintf(name, sizeof(name), "/%u.m61", slot);
    return services_.leave_for_script() && script::start(name);
  }
  case K::OPEN_FILE: {
    if (services_.dirty() || m61_text::active() || upload_)
      return false;
    program_store::Entry directory, entry;
    if (!script::register_file(directory_, directory) ||
        storage_path::resolve_file(directory.id, result.args, entry) !=
            storage_path::Status::OK)
      return false;
    const char *name = script::file_path(entry.id);
    if (!name)
      return false;
    if (entry.type == program_store::ProgramType::MK61) {
      char source[files::PATH_SIZE];
      std::strcpy(source, name);
      return services_.leave_for_script() && script::start(source);
    }
    services_.open(Action::EXPLORER, ui_.settings().russian, calculator_);
    return services_.run_external(name) == 0;
  }
  case K::WAIT: {
    const u32 until = millis() + (u32)result.key;
    while ((i32)(millis() - until) < 0)
      if (backend_.service)
        backend_.service(backend_.context);
    return true;
  }
  default:
    return false;
  }
}
bool Terminal::execute(const char *line) {
  line = terminal_core::skip_spaces(line);
  if (!line || !*line)
    return true;
  if (confirmation_) {
    const u8 command = confirmation_;
    confirmation_ = 0;
    if (!terminal_core::exact_confirmation(line, 'y'))
      return true;
    if (command == CMD_CLEAR) {
      if (!calculator_.idle() || core_61::is_RUN() || m61_text::active())
        return false;
      MK61Emu_ClearCodePage();
      return true;
    }
    if (command == CMD_FORMAT_STORAGE)
      return !services_.dirty() && !m61_text::active() && files::format();
    return backend_.board_command &&
           backend_.board_command(backend_.context, command, "now");
  }
  if (!std::strcmp(line, "raw")) {
    raw_ = true;
    out("Raw keyboard; Ctrl+] or Ctrl+_ returns to commands\r\n");
    return true;
  }
  const u8 id = terminal_catalog::lookup((const u8 *)line);
  const char *args = line;
  while (*args && !terminal_core::is_space(*args))
    ++args;
  args = terminal_core::skip_spaces(args);
  if (id == CMD_HELP) {
    for (usize i = 0; i < terminal_catalog::count(); ++i) {
      const auto command = terminal_catalog::at(i);
      out("%-10s ", command.name);
      m8(command.desc);
      out("\r\n");
      if (backend_.service)
        backend_.service(backend_.context);
    }
    out("raw        keyboard mode; Ctrl+] toggles; Ctrl+_ commands; Ctrl+^ "
        "raw\r\n");
    return true;
  }
  if (id == CMD_HISTORY) {
    for (unsigned i = 0; i < history_count_; ++i) {
      m8(history_[i]);
      out("\r\n");
    }
    return true;
  }
  if(id==CMD_CRASH || id==CMD_WATCHDOG || id==CMD_PROFILE)
    return diagnostics::command(id,args,directory_,backend_.write,backend_.context);
  if (id == CMD_FS_GET)
    return get(args);
  if (id == CMD_FS_PUT)
    return put(args);
  if (id == CMD_FS_PWD) {
    path_text(directory_);
    out("\r\n");
    return terminal_core::at_end(args);
  }
  if (id == CMD_FS_STAT) {
    u64 total = 0, free = 0;
    if (!files::space(total, free))
      return false;
    out("FAT total=%llu free=%llu\r\n", (unsigned long long)total,
        (unsigned long long)free);
    return true;
  }
  if (id == CMD_FS_CD || id == CMD_FS_LIST || id == CMD_FS_MKDIR ||
      id == CMD_FS_MOVE || id == CMD_FS_REMOVE || id == CMD_FS_RMDIR) {
    char name[files::PATH_SIZE];
    bool recursive = false;
    if ((id == CMD_FS_MKDIR || id == CMD_FS_REMOVE) &&
        !std::strncmp(args, id == CMD_FS_MKDIR ? "-p " : "-r ", 3)) {
      recursive = true;
      args += 3;
    }
    if (terminal_core::at_end(args) && (id == CMD_FS_CD || id == CMD_FS_LIST))
      std::strcpy(name, id == CMD_FS_CD ? "/" : directory_);
    else if (!path(args, name))
      return false;
    if (id == CMD_FS_MOVE) {
      char to[files::PATH_SIZE];
      return path(args, to) && terminal_core::at_end(args) &&
             files::rename(name, to);
    }
    if (!terminal_core::at_end(args))
      return false;
    if (id == CMD_FS_CD) {
      files::Entry info;
      if (std::strcmp(name, "/") &&
          (!files::stat(name, info) || !info.directory))
        return false;
      std::strcpy(directory_, name);
      return true;
    }
    if (id == CMD_FS_LIST) {
      unsigned count=0;
      for (unsigned i = 0; i < 4096; ++i) {
        files::Entry entry;
        unsigned used = 0;
        bool more;
        if (!files::list(name, i, &entry, 1, used, more))
          return false;
        if (!used)
          break;
        if(entry.directory) out("d\t");
        else out("f\t%lu B\t",(unsigned long)entry.size);
        path_text(entry.name);
        out("%s\r\n", entry.directory ? "/" : "");
        ++count;
        if (backend_.service)
          backend_.service(backend_.context);
        if (!more)
          break;
      }
      out("%u %s\r\n",count,count==1?"entry.":"entries.");
      return true;
    }
    if (id == CMD_FS_MKDIR && recursive) {
      for (char *p = name + 1; *p; ++p)
        if (*p == '/') {
          *p = 0;
          const bool ok = files::exists(name) || files::mkdir(name);
          *p = '/';
          if (!ok)
            return false;
        }
      return files::exists(name) || files::mkdir(name);
    }
    if (id == CMD_FS_MKDIR)
      return files::mkdir(name);
    return recursive ? remove_tree(name)
                     : std::strcmp(name, "/") && files::remove(name);
  }
  if (id == CMD_SAVE) {
    char name[files::PATH_SIZE];
    unsigned slot;
    if (slot_number(args, slot))
      std::snprintf(name, sizeof(name), "/%u.m61", slot);
    else {
      if (!path(args, name) || !terminal_core::at_end(args))
        return false;
      const char *base = std::strrchr(name, '/');
      if (!std::strchr(base ? base : name, '.')) {
        if (std::strlen(name) + 4 >= sizeof(name))
          return false;
        std::strcat(name, ".m61");
      }
      if (script::file_type(name) != program_store::ProgramType::MK61)
        return false;
    }
    return services_.save_program(name, calculator_);
  }
  if (id == CMD_USB_DISK) {
    if (!std::strcmp(args, "off")) {
      if (!files::usb_ejected())
        return false;
      services_.input('\r');
      return !files::usb_active();
    }
    if (!terminal_core::at_end(args) || services_.dirty() ||
        m61_text::active() || upload_)
      return false;
    services_.open(Action::USB_DISK, ui_.settings().russian, calculator_);
    return files::usb_active();
  }
  if (id == CMD_CLEAR || id == CMD_FORMAT_STORAGE ||
      (id == CMD_RESET && terminal_core::at_end(args))) {
    if ((id == CMD_FORMAT_STORAGE && std::strcmp(args, "SD") &&
         std::strcmp(args, "C6")) ||
        (id == CMD_CLEAR && !terminal_core::at_end(args)))
      return false;
    confirmation_ = id;
    out("%s: confirm Y/y\r\n", id == CMD_FORMAT_STORAGE
                                   ? "Erase ALL microSD files"
                               : id == CMD_CLEAR ? "Clear MK61 program"
                                                 : "Restart");
    return true;
  }
  if (terminal_command_allowed_in_script(id))
    return script_command(line);
  if (backend_.board_command &&
      backend_.board_command(backend_.context, id, args))
    return true;
  out("Unavailable command on Pico H\r\n");
  return false;
}
} // namespace picocalc
