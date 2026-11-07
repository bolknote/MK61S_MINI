#pragma once
#include <cstdint>

// Bookkeeping only. No expected values, mathematical rules or hidden tests.
// The caller records whether *all segments* of a public run stopped normally.
struct Mk61DebugGate {
    std::uint32_t revision = 0;
    std::uint16_t executed = 0;
    std::uint16_t failed = 0;
    std::uint8_t cases = 0;
    bool has_program = false;

    bool configure(unsigned count, bool program) {
        if (count == 0 || count > 16) return false;
        revision = 0; executed = failed = 0;
        cases = static_cast<std::uint8_t>(count); has_program = program;
        return true;
    }
    void edited() {
        ++revision; executed = failed = 0; has_program = true;
    }
    bool ran(unsigned index, bool stopped) {
        if (index >= cases || !has_program) return false;
        const auto bit = static_cast<std::uint16_t>(1u << index);
        executed |= bit;
        if (stopped) failed &= static_cast<std::uint16_t>(~bit);
        else failed |= bit;
        return true;
    }
    bool can_done() const {
        const auto mask = static_cast<std::uint16_t>((1u << cases) - 1u);
        return has_program && cases != 0 && executed == mask && failed == 0;
    }
};
