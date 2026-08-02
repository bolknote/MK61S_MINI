#ifndef LANGUAGE_WORKSPACE_HPP
#define LANGUAGE_WORKSPACE_HPP

#include "shared_memory.hpp"

namespace language_workspace {

enum class Owner : u8 {
  NONE = (u8) shared_memory::Owner::NONE,
  FOCAL = (u8) shared_memory::Owner::FOCAL,
  TINYBASIC = (u8) shared_memory::Owner::TINYBASIC,
  IMAGE_VIEWER = (u8) shared_memory::Owner::IMAGE_VIEWER,
  MARKDOWN_VIEWER = (u8) shared_memory::Owner::MARKDOWN_VIEWER,
  CHIP8 = (u8) shared_memory::Owner::CHIP8,
  USB_DISK = (u8) shared_memory::Owner::USB_DISK,
  TERMINAL_TRANSFER = (u8) shared_memory::Owner::TERMINAL_TRANSFER
};

static constexpr usize SIZE = shared_memory::WORKSPACE_SIZE;

// Исключительная аренда для одной из крупных взаимоисключающих сред выполнения.
// Один владелец может вкладывать аренды, но другой не может вытеснить активное
// состояние. Предыдущий пользователь очищается только при получении самой
// внешней аренды новым владельцем.
class [[nodiscard]] Lease {
  public:
    constexpr Lease(void) : lease() {}
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return lease.ok(); }
    bool fresh(void) const { return lease.fresh(); }
    void* data(void) const { return lease.data(); }
    usize size(void) const { return lease.size(); }

    bool acquire(Owner owner, usize required);
    void reset(void);

  private:
    shared_memory::Lease lease;
};

Owner resident_owner(void);
Owner active_owner(void);
bool discard(Owner owner);
void* data(Owner owner);

} // пространство имён language_workspace

#endif
