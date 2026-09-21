import 'dart:typed_data';

// Windows-1251 is the fixed MK-61S terminal wire encoding. Keep this tiny
// codec local to the desktop boundary: the firmware never negotiates UTF-8.
const List<int> _cp1251Upper = <int>[
  0x0402, 0x0403, 0x201a, 0x0453, 0x201e, 0x2026, 0x2020, 0x2021,
  0x20ac, 0x2030, 0x0409, 0x2039, 0x040a, 0x040c, 0x040b, 0x040f,
  0x0452, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014,
  0xfffd, 0x2122, 0x0459, 0x203a, 0x045a, 0x045c, 0x045b, 0x045f,
  0x00a0, 0x040e, 0x045e, 0x0408, 0x00a4, 0x0490, 0x00a6, 0x00a7,
  0x0401, 0x00a9, 0x0404, 0x00ab, 0x00ac, 0x00ad, 0x00ae, 0x0407,
  0x00b0, 0x00b1, 0x0406, 0x0456, 0x0491, 0x00b5, 0x00b6, 0x00b7,
  0x0451, 0x2116, 0x0454, 0x00bb, 0x0458, 0x0405, 0x0455, 0x0457,
];

String decodeCp1251(Iterable<int> bytes) {
  final codepoints = <int>[];
  for (final byte in bytes) {
    final value = byte & 0xff;
    if (value < 0x80) {
      codepoints.add(value);
    } else if (value >= 0xc0) {
      codepoints.add(0x0410 + value - 0xc0);
    } else {
      codepoints.add(_cp1251Upper[value - 0x80]);
    }
  }
  return String.fromCharCodes(codepoints);
}

Uint8List encodeCp1251(String text) {
  final output = BytesBuilder(copy: false);
  for (final codepoint in text.runes) {
    if (codepoint < 0x80) {
      output.addByte(codepoint);
      continue;
    }
    if (codepoint >= 0x0410 && codepoint <= 0x044f) {
      output.addByte(0xc0 + codepoint - 0x0410);
      continue;
    }
    final index = _cp1251Upper.indexOf(codepoint);
    if (index < 0 || codepoint == 0xfffd) {
      throw FormatException(
        'Символ U+${codepoint.toRadixString(16).toUpperCase().padLeft(4, '0')} '
        'не представим в CP1251',
      );
    }
    output.addByte(0x80 + index);
  }
  return output.takeBytes();
}
