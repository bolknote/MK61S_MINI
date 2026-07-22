import 'dart:typed_data';

abstract final class MkMessage {
  static const offer = 0x10;
  static const attach = 0x11;
  static const caps = 0x12;
  static const detach = 0x13;
  static const ping = 0x14;
  static const pong = 0x15;
  static const requestKeyframe = 0x16;
  static const frameBegin = 0x20;
  static const rect = 0x21;
  static const frameEnd = 0x22;
  static const keyEvent = 0x30;
  static const releaseAllKeys = 0x31;
}

abstract final class MkCodec {
  static const raw = 0;
  static const packBits = 1;
}

abstract final class MkCapability {
  static const diff = 1 << 0;
  static const packBits = 1 << 1;
  static const keyEvents = 1 << 2;
  static const heartbeat = 1 << 3;
  static const atomicFrames = 1 << 4;
  static const terminalMux = 1 << 5;
  static const terminalKeyboard = 1 << 6;
}

abstract final class MkGeometry {
  static const width = 192;
  static const height = 64;
  static const pageHeight = 8;
  static const pages = height ~/ pageHeight;
  static const frameBytes = width * height ~/ 8;
}

class MkPacket {
  const MkPacket({
    required this.type,
    required this.flags,
    required this.sequence,
    required this.payload,
  });

  final int type;
  final int flags;
  final int sequence;
  final Uint8List payload;
}

class MkProtocol {
  static const version = 2;
  static const magic0 = 0x4d;
  static const magic1 = 0x53;
  static const headerSize = 9;
  static const crcSize = 2;
  static const maxPayload = 224;
  static const maxRawPacket = headerSize + maxPayload + crcSize;
  static const maxFramedPacket = maxRawPacket + maxRawPacket ~/ 254 + 3;

  static int readU16(List<int> bytes, int offset) =>
      bytes[offset] | (bytes[offset + 1] << 8);

  static void writeU16(Uint8List bytes, int offset, int value) {
    bytes[offset] = value & 0xff;
    bytes[offset + 1] = (value >> 8) & 0xff;
  }

  static int crc16(List<int> bytes, [int? length]) {
    var crc = 0xffff;
    final count = length ?? bytes.length;
    for (var i = 0; i < count; i++) {
      crc ^= (bytes[i] & 0xff) << 8;
      for (var bit = 0; bit < 8; bit++) {
        crc = (crc & 0x8000) != 0
            ? ((crc << 1) ^ 0x1021) & 0xffff
            : (crc << 1) & 0xffff;
      }
    }
    return crc;
  }

  static Uint8List cobsEncode(List<int> input) {
    final output = <int>[0];
    var codeIndex = 0;
    var code = 1;
    for (final byte in input) {
      if (byte == 0) {
        output[codeIndex] = code;
        codeIndex = output.length;
        output.add(0);
        code = 1;
      } else {
        output.add(byte & 0xff);
        code++;
        if (code == 0xff) {
          output[codeIndex] = code;
          codeIndex = output.length;
          output.add(0);
          code = 1;
        }
      }
    }
    output[codeIndex] = code;
    return Uint8List.fromList(output);
  }

  static Uint8List cobsDecode(List<int> input) {
    if (input.isEmpty) throw const FormatException('empty COBS packet');
    final output = <int>[];
    var source = 0;
    while (source < input.length) {
      final code = input[source++];
      if (code == 0) throw const FormatException('zero inside COBS packet');
      final count = code - 1;
      if (source + count > input.length) {
        throw const FormatException('truncated COBS packet');
      }
      output.addAll(input.sublist(source, source + count));
      source += count;
      if (code != 0xff && source < input.length) output.add(0);
    }
    return Uint8List.fromList(output);
  }

  static Uint8List encodePacket({
    required int type,
    required int sequence,
    int flags = 0,
    List<int> payload = const [],
  }) {
    if (payload.length > maxPayload) {
      throw ArgumentError.value(payload.length, 'payload.length');
    }
    final raw = Uint8List(headerSize + payload.length + crcSize);
    raw[0] = magic0;
    raw[1] = magic1;
    raw[2] = version;
    raw[3] = type;
    raw[4] = flags;
    writeU16(raw, 5, sequence);
    writeU16(raw, 7, payload.length);
    raw.setRange(headerSize, headerSize + payload.length, payload);
    writeU16(
      raw,
      headerSize + payload.length,
      crc16(raw, headerSize + payload.length),
    );
    final encoded = cobsEncode(raw);
    return Uint8List.fromList([0, ...encoded, 0]);
  }

  static MkPacket decodePacket(List<int> encoded) {
    final raw = cobsDecode(encoded);
    if (raw.length < headerSize + crcSize) {
      throw const FormatException('short protocol packet');
    }
    if (raw[0] != magic0 || raw[1] != magic1) {
      throw const FormatException('wrong protocol magic');
    }
    if (raw[2] != version) {
      throw FormatException('unsupported protocol version ${raw[2]}');
    }
    final payloadLength = readU16(raw, 7);
    if (payloadLength > maxPayload ||
        raw.length != headerSize + payloadLength + crcSize) {
      throw const FormatException('invalid protocol length');
    }
    final expectedCrc = readU16(raw, headerSize + payloadLength);
    if (crc16(raw, headerSize + payloadLength) != expectedCrc) {
      throw const FormatException('CRC mismatch');
    }
    return MkPacket(
      type: raw[3],
      flags: raw[4],
      sequence: readU16(raw, 5),
      payload: Uint8List.sublistView(
        raw,
        headerSize,
        headerSize + payloadLength,
      ),
    );
  }

  static Uint8List decodePackBits(List<int> encoded, int expectedSize) {
    final output = <int>[];
    var source = 0;
    while (source < encoded.length) {
      final control = encoded[source++];
      if (control <= 127) {
        final count = control + 1;
        if (source + count > encoded.length) {
          throw const FormatException('truncated PackBits literal');
        }
        output.addAll(encoded.sublist(source, source + count));
        source += count;
      } else if (control >= 129) {
        final count = 257 - control;
        if (source >= encoded.length) {
          throw const FormatException('truncated PackBits run');
        }
        output.addAll(List<int>.filled(count, encoded[source++]));
      } else {
        throw const FormatException('non-canonical PackBits no-op');
      }
      if (output.length > expectedSize) {
        throw const FormatException('PackBits output overflow');
      }
    }
    if (output.length != expectedSize) {
      throw const FormatException('wrong PackBits output length');
    }
    return Uint8List.fromList(output);
  }
}

class MkStreamParser {
  final List<int> _encoded = [];
  final BytesBuilder _terminal = BytesBuilder(copy: false);
  bool _insidePacket = false;
  bool _overflowed = false;
  int discardedPackets = 0;

  List<MkPacket> add(List<int> bytes) {
    final packets = <MkPacket>[];
    for (final byte in bytes) {
      if (!_insidePacket) {
        if (byte == 0) {
          _insidePacket = true;
          _encoded.clear();
          _overflowed = false;
        } else {
          _terminal.addByte(byte);
        }
        continue;
      }

      if (byte != 0) {
        if (_overflowed) continue;
        if (_encoded.length < MkProtocol.maxFramedPacket) {
          _encoded.add(byte);
        } else {
          _encoded.clear();
          _overflowed = true;
          discardedPackets++;
        }
        continue;
      }
      if (_overflowed) {
        _overflowed = false;
        _encoded.clear();
        _insidePacket = false;
        continue;
      }
      // Повторные нули сохраняют анализатор взведённым. Это одновременно чистая
      // точка повторной синхронизации и граница между соседними пакетами.
      if (_encoded.isEmpty) continue;
      try {
        packets.add(MkProtocol.decodePacket(_encoded));
      } on FormatException {
        discardedPackets++;
      }
      _encoded.clear();
      _insidePacket = false;
    }
    return packets;
  }

  Uint8List takeTerminalBytes() {
    if (_terminal.length == 0) return Uint8List(0);
    return _terminal.takeBytes();
  }

  void reset() {
    _encoded.clear();
    _terminal.takeBytes();
    _insidePacket = false;
    _overflowed = false;
  }
}

class DeviceCapabilities {
  const DeviceCapabilities({
    required this.width,
    required this.height,
    required this.pageHeight,
    required this.flags,
    required this.heartbeatTimeoutMs,
    required this.keyboardLayout,
    required this.keyCount,
    this.textRows,
    this.glyphWidth,
    this.glyphHeight,
    this.lineGap,
  });

  factory DeviceCapabilities.parse(List<int> payload) {
    if (payload.length != 10 && payload.length != 14) {
      throw const FormatException('invalid capabilities payload');
    }
    return DeviceCapabilities(
      width: MkProtocol.readU16(payload, 0),
      height: payload[2],
      pageHeight: payload[3],
      flags: MkProtocol.readU16(payload, 4),
      heartbeatTimeoutMs: MkProtocol.readU16(payload, 6),
      keyboardLayout: payload[8],
      keyCount: payload[9],
      textRows: payload.length == 14 ? payload[10] : null,
      glyphWidth: payload.length == 14 ? payload[11] : null,
      glyphHeight: payload.length == 14 ? payload[12] : null,
      lineGap: payload.length == 14 ? payload[13] : null,
    );
  }

  final int width;
  final int height;
  final int pageHeight;
  final int flags;
  final int heartbeatTimeoutMs;
  final int keyboardLayout;
  final int keyCount;
  final int? textRows;
  final int? glyphWidth;
  final int? glyphHeight;
  final int? lineGap;

  bool get validGeometry =>
      width == MkGeometry.width &&
      height == MkGeometry.height &&
      pageHeight == MkGeometry.pageHeight;
}

class FrameAssembler {
  Uint8List _framebuffer = Uint8List(MkGeometry.frameBytes);
  Uint8List? _staging;
  int? _frameId;
  int _expectedRects = 0;
  int _receivedRects = 0;

  int completedFrames = 0;
  int rejectedFrames = 0;
  String? lastError;

  Uint8List get framebuffer => Uint8List.fromList(_framebuffer);

  bool consume(MkPacket packet) {
    try {
      switch (packet.type) {
        case MkMessage.frameBegin:
          _begin(packet.payload);
          return false;
        case MkMessage.rect:
          _rect(packet.payload);
          return false;
        case MkMessage.frameEnd:
          return _end(packet.payload);
      }
    } on FormatException catch (error) {
      _reject(error.message.toString());
    }
    return false;
  }

  void _begin(List<int> payload) {
    if (payload.length != 4 || payload[2] > 1 || payload[3] > 32) {
      throw const FormatException('invalid FRAME_BEGIN');
    }
    _frameId = MkProtocol.readU16(payload, 0);
    _expectedRects = payload[3];
    _receivedRects = 0;
    _staging = payload[2] != 0
        ? Uint8List(MkGeometry.frameBytes)
        : Uint8List.fromList(_framebuffer);
  }

  void _rect(List<int> payload) {
    if (_staging == null || _frameId == null || payload.length < 6) {
      throw const FormatException('RECT outside frame');
    }
    final frameId = MkProtocol.readU16(payload, 0);
    final x = payload[2];
    final page = payload[3];
    final width = payload[4];
    final codec = payload[5];
    if (frameId != _frameId ||
        width == 0 ||
        page >= MkGeometry.pages ||
        x + width > MkGeometry.width ||
        _receivedRects >= _expectedRects) {
      throw const FormatException('invalid RECT geometry');
    }
    final encoded = payload.sublist(6);
    final pixels = switch (codec) {
      MkCodec.raw when encoded.length == width => Uint8List.fromList(encoded),
      MkCodec.raw => throw const FormatException('wrong RAW length'),
      MkCodec.packBits => MkProtocol.decodePackBits(encoded, width),
      _ => throw FormatException('unknown rectangle codec $codec'),
    };
    _staging!.setRange(
      page * MkGeometry.width + x,
      page * MkGeometry.width + x + width,
      pixels,
    );
    _receivedRects++;
  }

  bool _end(List<int> payload) {
    if (_staging == null || _frameId == null || payload.length != 4) {
      throw const FormatException('invalid FRAME_END');
    }
    final frameId = MkProtocol.readU16(payload, 0);
    final expectedCrc = MkProtocol.readU16(payload, 2);
    if (frameId != _frameId || _receivedRects != _expectedRects) {
      throw const FormatException('incomplete frame');
    }
    if (MkProtocol.crc16(_staging!) != expectedCrc) {
      throw const FormatException('framebuffer CRC mismatch');
    }
    _framebuffer = _staging!;
    _staging = null;
    _frameId = null;
    completedFrames++;
    lastError = null;
    return true;
  }

  void _reject(String message) {
    _staging = null;
    _frameId = null;
    rejectedFrames++;
    lastError = message;
  }

  void reset() {
    _framebuffer = Uint8List(MkGeometry.frameBytes);
    _staging = null;
    _frameId = null;
    completedFrames = 0;
    rejectedFrames = 0;
    lastError = null;
  }
}
