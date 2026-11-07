// Research-only readout of the sibling assembler's complete opcode catalog.
#include "mkpro/core/opcodes.hpp"
#include <algorithm>
#include <iomanip>
#include <iostream>

int main() {
  std::cout << '[';
  bool first = true;
  for (const auto &row : mkpro::opcode_catalog()) {
    if (!first) std::cout << ',';
    first = false;
    const bool manual = std::find(row.enterable.begin(), row.enterable.end(),
                                  mkpro::DeliveryMode::Manual) != row.enterable.end();
    std::cout << "{\"code\":" << row.code << ",\"hex\":" << std::quoted(row.hex)
              << ",\"name\":" << std::quoted(row.name)
              << ",\"takes_address\":" << (row.takes_address ? "true" : "false")
              << ",\"keyboard_enterable\":" << (manual ? "true" : "false")
              << ",\"risk\":" << std::quoted(mkpro::opcode_risk_name(row.risk)) << '}';
  }
  std::cout << "]\n";
}
