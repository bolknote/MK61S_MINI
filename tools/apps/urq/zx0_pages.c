/* Host-only optimal ZX0 page encoder. Uses the existing vendored ZX0 code. */
#include <stdio.h>
#include <stdlib.h>
#include "../packer/third_party/zx0/zx0.h"

int main(int argc, char **argv) {
  if(argc != 3) return 2;
  FILE *input = fopen(argv[1], "rb");
  FILE *output = fopen(argv[2], "wb");
  if(!input || !output) return 3;
  unsigned char page[512];
  size_t count;
  while((count = fread(page, 1, sizeof(page), input)) != 0) {
    BLOCK *plan = optimize(page, (int)count, 0, 32640);
    int size = 0, delta = 0;
    unsigned char *packed = compress(plan, page, (int)count, 0, 0, 1, &size, &delta);
    if(!packed || size <= 0) return 4;
    const int raw = size >= (int)count;
    const unsigned length = raw ? (unsigned)count : (unsigned)size;
    const unsigned char header[2] = {length & 255U, length >> 8U};
    if(fwrite(header, 1, 2, output) != 2 ||
       fwrite(raw ? page : packed, 1, length, output) != length) return 5;
    free(packed);
  }
  if(ferror(input) || fclose(input) || fclose(output)) return 6;
  return 0;
}
