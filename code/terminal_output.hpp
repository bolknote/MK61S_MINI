#ifndef MK61_TERMINAL_OUTPUT_HPP
#define MK61_TERMINAL_OUTPUT_HPP

namespace terminal_output {

// Keep the repeated label/value sequence out of line: diagnostics contain
// hundreds of fields, and inlining their Print calls wastes resident Flash.
// Delegate formatting to the stream so signedness, base and text stay intact;
// no temporary report buffer or persistent RAM is needed.
template<typename Output, typename Value, typename... Format>
[[gnu::cold, gnu::noinline]] void field(Output& output, const char* label,
                                      Value value, Format... format) {
  output.print(label);
  output.print(value, format...);
}

template<typename Output, typename Value, typename... Format>
[[gnu::cold, gnu::noinline]] void line(Output& output, const char* label,
                                     Value value, Format... format) {
  field(output, label, value, format...);
  output.println();
}

} // namespace terminal_output

#endif
