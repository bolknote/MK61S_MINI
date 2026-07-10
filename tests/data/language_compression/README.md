# FOCAL and Tiny BASIC compression corpus

These are complete source programs deliberately sized just above the former
1023-byte FOCAL/Tiny BASIC editor limit, and below the current 1536-byte
filesystem/editor quota. They exercise repeated language syntax, formulas,
labels, strings, and prose comments rather than synthetic runs of one byte.

Run the comparison with:

```sh
python3 tools/rle_strategy_benchmark.py \
  tests/data/language_compression/*.foc \
  tests/data/language_compression/*.tbi \
  --scan-splits --lzo
```

The LZO measurements below use liblzo2 2.10. Sizes are compressed stream sizes
without a common codec/original-length wrapper. A three-byte wrapper would not
change any fit result.

| Program | Raw | Over 1023 | Bolk RLE | Optimal PackBits | LZO1X-1 | LZO1X-1-11 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `loan.foc` | 1035 | 12 | 1053 | 1044 | 689 | 689 |
| `projectile.foc` | 1088 | 65 | 1111 | 1097 | 827 | 831 |
| `statistics.foc` | 1078 | 55 | 1090 | 1087 | 719 | 719 |
| `loan.tbi` | 1112 | 89 | 1125 | 1121 | 811 | 818 |
| `projectile.tbi` | 1084 | 61 | 1103 | 1093 | 917 | 929 |
| `statistics.tbi` | 1121 | 98 | 1129 | 1130 | 442 | 446 |

Byte RLE does not help this corpus. Even an optimal PackBits parser expands
every source by exactly 9 bytes; scanning every control-byte split still
expands each source by 5 bytes. Normal source code has repeated words and
phrases, but almost no long runs of the same byte.

LZO1X-1 reduces the files to 39.4–84.6% of their original size, and all six
compressed streams fit the former 1023-byte limit. LZO1X-1-11 gives nearly the
same ratios while reducing 32-bit compressor work memory from 64 KiB to 8 KiB.
LZO decompression itself does not require work memory, but the firmware still
needs room for the full expanded source or a parser that can consume a
decompression stream.
