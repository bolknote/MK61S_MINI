import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/device/cp1251.dart';

void main() {
  test('CP1251 round-trips Russian terminal text', () {
    const source = 'МК-61: Ёж, цена 20€…';
    final encoded = encodeCp1251(source);
    expect(decodeCp1251(encoded), source);
    expect(encoded.sublist(0, 2), <int>[0xcc, 0xca]);
  });

  test('undefined byte and unsupported input are explicit', () {
    expect(decodeCp1251(<int>[0x98]), '\uFFFD');
    expect(() => encodeCp1251('→'), throwsFormatException);
  });
}
