#ifndef MK61_MENU_MODEL_HPP
#define MK61_MENU_MODEL_HPP

#include "mk8_literal.hpp"

namespace menu_model {
enum class MainItem : u8 {
#define MK61_MAIN_ITEM(id, en_object, ru_object, action, size, en, ru) id,
#include "main_menu_items.inc"
#undef MK61_MAIN_ITEM
    COUNT
};
constexpr unsigned MAIN_COUNT = (unsigned)MainItem::COUNT;

inline const char* mainLabel(MainItem item, bool russian) {
    switch(item) {
#define MK61_MAIN_ITEM(id, en_object, ru_object, action, size, en, ru) \
        case MainItem::id: return russian ? M8(ru) : en;
#include "main_menu_items.inc"
#undef MK61_MAIN_ITEM
        default: return "";
    }
}

// The original menu clamps at the endpoints and scrolls just enough to
// retain the active row. Keep these rules identical on all displays.
constexpr unsigned step(unsigned active, unsigned count, int direction) {
    if(count == 0) return 0;
    if(active >= count) active = count - 1;
    if(direction < 0) return active ? active - 1 : 0;
    return direction > 0 && active + 1 < count ? active + 1 : active;
}
constexpr unsigned firstVisible(unsigned active, unsigned count, unsigned rows) {
    if(rows == 0 || count <= rows) return 0;
    if(active >= count) active = count - 1;
    return active + 1 > rows ? active + 1 - rows : 0;
}
} // namespace menu_model
#endif
