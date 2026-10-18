import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/protocol/mk61_protocol.dart';

MkPacket packet(int type, List<int> payload) => MkPacket(
  type: type,
  flags: 0,
  sequence: 0,
  payload: Uint8List.fromList(payload),
);

List<int> begin(int id, {required bool keyframe, required int rects}) => [
  id & 0xff,
  id >> 8,
  keyframe ? 1 : 0,
  rects,
];

List<int> end(int id, List<int> framebuffer) {
  final crc = MkProtocol.crc16(framebuffer);
  return [id & 0xff, id >> 8, crc & 0xff, crc >> 8];
}

void main() {
  test(
    'negotiates PicoCalc native geometry and assembles all 320x320 pixels',
    () {
      final caps = DeviceCapabilities.parse([
        64,
        1,
        64,
        8,
        0x10,
        1,
        0xb8,
        0xb,
        0,
        40,
        18,
        8,
        16,
        1,
        64,
        1,
      ]);
      expect(caps.validGeometry, isTrue);
      expect(caps.width, 320);
      expect(caps.height, 320);
      final assembler = FrameAssembler()..configure(caps.width, caps.height);
      final expected = Uint8List.fromList(
        List.generate(12800, (i) => (i * 37 + 7) & 255),
      );
      assembler.consume(
        packet(MkMessage.frameBegin, begin(42, keyframe: true, rects: 80)),
      );
      for (var page = 0; page < 40; page++) {
        for (final x in [0, 160]) {
          assembler.consume(
            packet(MkMessage.rect, [
              42,
              0,
              x,
              page,
              160,
              MkCodec.raw,
              ...expected.sublist(page * 320 + x, page * 320 + x + 160),
            ]),
          );
        }
      }
      expect(
        assembler.consume(packet(MkMessage.frameEnd, end(42, expected))),
        isTrue,
      );
      expect(assembler.framebuffer, expected);
      assembler.configure(192, 64);
      expect(assembler.framebuffer.length, 1536);
    },
  );
  test('rejects native geometry without the negotiated capability', () {
    final caps = DeviceCapabilities.parse([
      64,
      1,
      64,
      8,
      0x10,
      0,
      0xb8,
      0xb,
      0,
      40,
      18,
      8,
      16,
      1,
      64,
      1,
    ]);
    expect(caps.validGeometry, isFalse);
    expect(() => FrameAssembler().configure(640, 320), throwsFormatException);
  });
  test('commits a complete atomic keyframe', () {
    final assembler = FrameAssembler();
    final expected = Uint8List(MkGeometry.frameBytes);
    expected[5] = 0xaa;
    expected[6] = 0xbb;

    expect(
      assembler.consume(
        packet(MkMessage.frameBegin, begin(7, keyframe: true, rects: 1)),
      ),
      isFalse,
    );
    expect(
      assembler.consume(
        packet(MkMessage.rect, [7, 0, 5, 0, 2, MkCodec.raw, 0xaa, 0xbb]),
      ),
      isFalse,
    );
    expect(
      assembler.consume(packet(MkMessage.frameEnd, end(7, expected))),
      isTrue,
    );
    expect(assembler.framebuffer, expected);
    expect(assembler.completedFrames, 1);
  });

  test('applies a PackBits diff to the previous frame', () {
    final assembler = FrameAssembler();
    final blank = Uint8List(MkGeometry.frameBytes);
    assembler.consume(
      packet(MkMessage.frameBegin, begin(1, keyframe: true, rects: 0)),
    );
    expect(
      assembler.consume(packet(MkMessage.frameEnd, end(1, blank))),
      isTrue,
    );

    final expected = Uint8List.fromList(blank);
    expected.setRange(MkGeometry.width + 10, MkGeometry.width + 14, [
      9,
      9,
      9,
      9,
    ]);
    assembler.consume(
      packet(MkMessage.frameBegin, begin(2, keyframe: false, rects: 1)),
    );
    assembler.consume(
      packet(MkMessage.rect, [2, 0, 10, 1, 4, MkCodec.packBits, 253, 9]),
    );
    expect(
      assembler.consume(packet(MkMessage.frameEnd, end(2, expected))),
      isTrue,
    );
    expect(assembler.framebuffer, expected);
  });

  test('rejects a frame without publishing partial pixels', () {
    final assembler = FrameAssembler();
    final before = assembler.framebuffer;
    assembler.consume(
      packet(MkMessage.frameBegin, begin(3, keyframe: true, rects: 1)),
    );
    assembler.consume(
      packet(MkMessage.rect, [3, 0, 0, 0, 1, MkCodec.raw, 0xff]),
    );
    expect(
      assembler.consume(packet(MkMessage.frameEnd, const [3, 0, 0, 0])),
      isFalse,
    );
    expect(assembler.framebuffer, before);
    expect(assembler.rejectedFrames, 1);
  });
}
