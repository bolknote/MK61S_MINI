#include "calculator.hpp"
#include "display_symbols.hpp"
#include <cstring>

namespace picocalc {

Key map_key(u8 code) {
    if(code >= 'A' && code <= 'Z') code += 'a' - 'A';
    if(code >= '0' && code <= '9') return {(u8)(2 + code - '0'), 1, NONE, "DIGIT"};
    switch(code) {
        case '.': case ',': return {7, 8, NONE, "."};
        case '+': return {2, 8, NONE, "+"};
        case '-': return {3, 8, NONE, "-"};
        case '*': return {4, 8, NONE, "*"};
        case '/': return {5, 8, NONE, "/"};
        case 0x0A: case 0x0D: return {11, 8, NONE, "ENTER"};
        case 0x08: case 0x1B: case 0x7F: case 0xB1: case 0xD4:
            return {10, 8, NONE, "Cx"};
        case 'e': return {9, 8, NONE, "EXP"};
        case 'n': return {8, 8, NONE, "+/-"};
        case 'x': return {6, 8, NONE, "X<>Y"};
        case 'f': case 0x81: return {11, 9, NONE, "F"};
        case 'k': case 0x82: return {10, 9, NONE, "K"};
        case 'r': case 0x83: return {2, 9, NONE, "S/P"};
        case 'g': case 0x84: return {3, 9, NONE, "GOTO"};
        case 'c': case 0x85: return {5, 9, NONE, "CALL"};
        case 'b': case 0x86: return {4, 9, NONE, "RETURN"};
        case 'l': case 0x87: return {8, 9, NONE, "RECALL"};
        case 's': case 0x88: return {6, 9, NONE, "STORE"};
        case '[': case 0x89: case 0xB4: return {7, 9, NONE, "STEP <"};
        case ']': case 0x90: case 0xB7: return {9, 9, NONE, "STEP >"};
        case 'd': return {0, 0, DEGREE, "DEG"};
        case 'a': return {0, 0, RADIAN, "RAD"};
        case 't': return {0, 0, GRADE, "GRAD"};
        default: return {};
    }
}

void Calculator::init(bool expanded) {
    read_ = count_ = press_steps_ = 0;
    release_steps_ = 0;
    dropped_keys_ = 0;
    releasing_ = f_pending_ = false;
    last_key_ = "READY";
    core_61::set_expanded_program_mode(expanded);
    core_61::enable();
    core_61::edit_program = false;
    MK61Emu_SetAngleUnit(DEGREE);
    MK61Emu_SetKeyPress(0, 0);
    // Power-on ROM sequence, identical to the existing core tests.
    for(unsigned i = 0; i < 8; ++i) core_61::step();
}

void Calculator::set_memory_mode(u8 mode) {
    if(mode > 1 || (mode == 1) == core_61::expanded_program_is_on()) return;
    const AngleUnit angle = MK61Emu_GetAngleUnit();
    init(mode == 1);
    MK61Emu_SetAngleUnit(angle);
}

bool Calculator::input(u8 code) {
    const Key key = map_key(code);
    if(!key.valid()) return false;
    if(count_ == QUEUE_SIZE) {
        ++dropped_keys_;
        return false;
    }
    queue_[(read_ + count_) % QUEUE_SIZE] = key;
    ++count_;
    return true;
}

void Calculator::tick() {
    if(!press_steps_ && !releasing_ && count_) {
        active_ = queue_[read_];
        read_ = (read_ + 1) % QUEUE_SIZE;
        --count_;
        last_key_ = active_.label;
        if(active_.angle != NONE) {
            MK61Emu_SetAngleUnit(active_.angle);
        } else {
            if(f_pending_) {
                if(active_.x == 9 && active_.y == 8) core_61::edit_program = true;
                if(active_.x == 8 && active_.y == 8) core_61::edit_program = false;
            }
            f_pending_ = active_.x == 11 && active_.y == 9;
            core_61::clear_displayed();
            press_steps_ = 4;
        }
    }
    if(press_steps_) {
        MK61Emu_SetKeyPress(active_.x, active_.y);
        core_61::step();
        if(--press_steps_ == 0 || core_61::is_RUN()) {
            press_steps_ = 0;
            releasing_ = true;
            release_steps_ = 0;
        }
    } else {
        MK61Emu_SetKeyPress(0, 0);
        core_61::step();
        if(releasing_ && (core_61::is_RUN() || core_61::is_displayed() ||
                          ++release_steps_ >= 512)) releasing_ = false;
    }
}

Snapshot Calculator::snapshot() const {
    Snapshot result;
    static constexpr char symbols[16] = {'O','1','2','3','4','5','6','7','8','9','-','L','C',
        (char)display_symbol::uc1609::CYR_GHE, 'E', ' '};
    std::strncpy(result.indicator, MK61Emu_GetIndicatorStr(nullptr),
                 sizeof(result.indicator) - 1);
    core_61::update_indicator(result.face_indicator, symbols);
    if(const u8* masks = core_61::segment_display_frame()) {
        std::memcpy(result.segments, masks, sizeof(result.segments));
        result.segmented = true;
    }
    for(unsigned i = 0; i < 3; ++i)
        read_stack_register((stack)(Y + i), result.stack_values[i], nullptr);
    result.last_key = last_key_;
    result.angle = MK61Emu_GetAngleUnit();
    result.ip = core_61::get_IP();
    result.running = core_61::is_RUN();
    result.programming = core_61::edit_program;
    result.dropped_keys = dropped_keys_;
    return result;
}

} // namespace picocalc
