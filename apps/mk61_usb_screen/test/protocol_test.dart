import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/protocol/mk61_protocol.dart';

void main() {
  group('MK61 wire protocol', () {
    test('CRC-16/CCITT matches the standard vector', () {
      expect(MkProtocol.crc16(ascii.encode('123456789')), 0x29b1);
    });

    test('COBS round-trips embedded and trailing zeroes', () {
      final source = Uint8List.fromList([0, 1, 2, 0, 3, 0]);
      final encoded = MkProtocol.cobsEncode(source);
      expect(encoded, isNot(contains(0)));
      expect(MkProtocol.cobsDecode(encoded), source);
    });

    test('packet encoding preserves header and payload', () {
      final framed = MkProtocol.encodePacket(
        type: MkMessage.ping,
        flags: 0x5a,
        sequence: 0xbeef,
        payload: const [0, 17, 255],
      );
      expect(framed.last, 0);
      final packet = MkProtocol.decodePacket(
        framed.sublist(0, framed.length - 1),
      );
      expect(packet.type, MkMessage.ping);
      expect(packet.flags, 0x5a);
      expect(packet.sequence, 0xbeef);
      expect(packet.payload, [0, 17, 255]);
    });

    test('stream parser accepts arbitrary fragmentation', () {
      final first = MkProtocol.encodePacket(
        type: MkMessage.offer,
        sequence: 1,
        payload: List<int>.filled(10, 0),
      );
      final second = MkProtocol.encodePacket(
        type: MkMessage.pong,
        sequence: 2,
        payload: const [7, 0],
      );
      final stream = Uint8List.fromList([...first, ...second]);
      final parser = MkStreamParser();
      final packets = <MkPacket>[];
      for (var offset = 0; offset < stream.length; offset += 3) {
        final end = offset + 3 < stream.length ? offset + 3 : stream.length;
        packets.addAll(parser.add(stream.sublist(offset, end)));
      }
      expect(packets.map((packet) => packet.type), [
        MkMessage.offer,
        MkMessage.pong,
      ]);
      expect(parser.discardedPackets, 0);
    });

    test('stream parser discards an entire overflowing frame then resyncs', () {
      final parser = MkStreamParser();
      parser.add(List<int>.filled(MkProtocol.maxFramedPacket + 20, 1));
      expect(parser.add(const [0]), isEmpty);
      expect(parser.discardedPackets, 1);

      final valid = MkProtocol.encodePacket(
        type: MkMessage.pong,
        sequence: 9,
        payload: const [1, 0],
      );
      final packets = parser.add(valid);
      expect(packets, hasLength(1));
      expect(packets.single.sequence, 9);
    });

    test('PackBits decoder handles literals and runs', () {
      final decoded = MkProtocol.decodePackBits(const [2, 1, 2, 3, 253, 9], 7);
      expect(decoded, [1, 2, 3, 9, 9, 9, 9]);
    });

    test('capabilities expose the graphical profile', () {
      final caps = DeviceCapabilities.parse(const [
        192,
        0,
        64,
        8,
        31,
        0,
        184,
        11,
        1,
        40,
        6,
        5,
        8,
        2,
      ]);
      expect(caps.validGeometry, isTrue);
      expect(caps.keyboardLayout, 1);
      expect(caps.textRows, 6);
      expect(caps.glyphHeight, 8);
    });
  });
}
