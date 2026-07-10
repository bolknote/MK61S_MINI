#include <cassert>
#include <iostream>

#include "debug.h"

int main(void) {
  dbg::core_trace("trace ", -1);
  dbg::core_trace("trace ", 1);
  dbg::core_trace("trace ", 1);
  dbg::core_trace("trace ", 2);

  dbg::print("text");
  dbg::print('[', "left", ']', "right");
  dbg::print("value=", 1);
  dbg::print("value=", 1, "!");
  dbg::print("a=", 1, " b=", 2);
  dbg::print("a=", 1, " b=", 2, ".");

  dbg::printhex("hex=", 1);
  dbg::printhex("hex=", 1, '!');
  dbg::printhex("hex=", 1, ".");
  dbg::printhex("a=", 1, " b=", 2);
  dbg::printhex(1, '!');
  dbg::printhex(1, ".");
  dbg::printhex('[', 1, ']');

  dbg::printhexln((usize)1);
  dbg::printhexln("hex=", (usize)1);
  dbg::printhexln("hex=", (usize)1, ".");
  dbg::printhexln("a=", (usize)1, " b=", (usize)2);
  dbg::printhexln("a=", (usize)1, " b=", (usize)2, " c=", (usize)3);
  dbg::printhexln("a=", (usize)1, " b=", (usize)2, " c=", (usize)3,
                  " d=", (usize)4);

  dbg::println("text");
  dbg::println("value=", 1);
  dbg::println("left", "right");
  dbg::println("value=", 1, ".");
  dbg::println("a", "b", "c");
  dbg::println("a=", 1, " b=", 2);
  dbg::println("value=", 1, " ", ".");
  dbg::println("a=", 1, " b=", 2, ".");
  dbg::println("a=", 1, " b=", 2, " c=", 3);
  dbg::println("a=", 1, " b=", 2, " c=", 3, " d=", 4);

  bool else_taken = false;
  if(true)
    dbg(MINI, "disabled-safe");
  else
    else_taken = true;
  assert(!else_taken);

  std::cout << "debug_self_test: ok\n";
  return 0;
}
