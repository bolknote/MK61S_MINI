#ifndef LANGUAGE_WORKSPACE_HPP
#define LANGUAGE_WORKSPACE_HPP

#include "rust_types.h"

namespace language_workspace {

enum class Owner : u8 {
  NONE,
  FOCAL,
  TINYBASIC,
  IMAGE_VIEWER,
  USB_DISK,
  TERMINAL_TRANSFER
};

static constexpr usize SIZE = 8192;

// Исключительная аренда для одной из крупных взаимоисключающих сред выполнения.
// Один владелец может вкладывать аренды, но другой не может вытеснить активное
// состояние. Предыдущий пользователь очищается только при получении самой
// внешней аренды новым владельцем.
class [[nodiscard]] Lease {
  public:
    constexpr Lease(void)
      : owner(Owner::NONE), memory(nullptr), requested(0), was_fresh(false) {}
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return memory != 0; }
    bool fresh(void) const { return was_fresh; }
    void* data(void) const { return memory; }
    usize size(void) const { return requested; }

    bool acquire(Owner owner, usize required);
    void reset(void);

  private:
    Owner owner;
    void* memory;
    usize requested;
    bool was_fresh;
};

Owner resident_owner(void);
Owner active_owner(void);
void* data(Owner owner);

} // пространство имён language_workspace

#endif
