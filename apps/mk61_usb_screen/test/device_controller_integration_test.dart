import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mk61_usb_screen/device/device_controller.dart';
import 'package:mk61_usb_screen/device/keyboard_definition.dart';
import 'package:mk61_usb_screen/device/serial_transport.dart';
import 'package:mk61_usb_screen/protocol/mk61_protocol.dart';

class _FakeSerialTransport implements DeviceSerialTransport {
  static const portName = '/dev/cu.usbmodem-MK61';
  final _FakeSerialConnection connection = _FakeSerialConnection();
  int openCount = 0;
  int? openedBaudRate;

  @override
  List<String> get availablePorts => [portName];

  @override
  DeviceSerialConnection open(String name, {required int baudRate}) {
    if (name != portName) throw StateError('unexpected port $name');
    openCount++;
    openedBaudRate = baudRate;
    return connection;
  }
}

class _FakeSerialConnection implements DeviceSerialConnection {
  final StreamController<Uint8List> _input = StreamController<Uint8List>(
    sync: true,
  );
  final MkStreamParser _hostParser = MkStreamParser();
  final List<MkPacket> hostPackets = [];
  final List<int> hostTerminalBytes = [];
  void Function(MkPacket packet)? onHostPacket;

  int _deviceSequence = 0;
  bool closed = false;

  @override
  Stream<Uint8List> get input => _input.stream;

  @override
  int write(Uint8List bytes, {required int timeoutMs}) {
    if (closed) throw StateError('connection is closed');
    expect(timeoutMs, 100);
    final packets = _hostParser.add(bytes);
    hostTerminalBytes.addAll(_hostParser.takeTerminalBytes());
    hostPackets.addAll(packets);
    for (final packet in packets) {
      onHostPacket?.call(packet);
    }
    return bytes.length;
  }

  void sendDeviceTerminal(String text) {
    _input.add(Uint8List.fromList(utf8.encode(text)));
  }

  void sendDevicePacket(
    int type, [
    List<int> payload = const [],
    List<int> fragmentSizes = const [],
  ]) {
    final framed = MkProtocol.encodePacket(
      type: type,
      sequence: _deviceSequence++ & 0xffff,
      payload: payload,
    );
    if (fragmentSizes.isEmpty) {
      _input.add(framed);
      return;
    }

    var offset = 0;
    var fragment = 0;
    while (offset < framed.length) {
      final requested = fragmentSizes[fragment % fragmentSizes.length];
      final end = (offset + requested).clamp(0, framed.length);
      _input.add(Uint8List.sublistView(framed, offset, end));
      offset = end;
      fragment++;
    }
  }

  void skipDeviceSequence() {
    _deviceSequence++;
  }

  @override
  void close() {
    if (closed) return;
    closed = true;
    unawaited(_input.close());
  }
}

List<int> _capabilities({
  required bool includeProfile,
  bool terminalKeyboard = true,
}) => [
  192,
  0,
  64,
  8,
  MkCapability.packBits |
      MkCapability.keyEvents |
      MkCapability.heartbeat |
      MkCapability.atomicFrames |
      MkCapability.terminalMux |
      (terminalKeyboard ? MkCapability.terminalKeyboard : 0),
  0,
  0xb8,
  0x0b,
  MkKeyboardLayout.mini,
  40,
  if (includeProfile) ...[6, 5, 8, 2],
];

List<int> _frameBegin(int id, {required bool keyframe, required int rects}) => [
  id & 0xff,
  id >> 8,
  keyframe ? 1 : 0,
  rects,
];

List<int> _frameEnd(int id, List<int> framebuffer) {
  final crc = MkProtocol.crc16(framebuffer);
  return [id & 0xff, id >> 8, crc & 0xff, crc >> 8];
}

Future<DeviceController> _openController(_FakeSerialTransport transport) async {
  final controller = DeviceController(serialTransport: transport);
  await controller.refreshPorts();
  expect(transport.openCount, 1);
  expect(transport.openedBaudRate, 115200);
  expect(controller.state, DeviceConnectionState.waitingForOffer);
  return controller;
}

void _attach(
  DeviceController controller,
  _FakeSerialConnection connection, {
  bool terminalKeyboard = true,
}) {
  connection.sendDevicePacket(
    MkMessage.offer,
    _capabilities(includeProfile: false, terminalKeyboard: terminalKeyboard),
    const [1, 2, 5, 3],
  );
  expect(controller.state, DeviceConnectionState.attaching);
  expect(connection.hostPackets.last.type, MkMessage.attach);

  connection.sendDevicePacket(
    MkMessage.caps,
    _capabilities(includeProfile: true, terminalKeyboard: terminalKeyboard),
    const [2, 1, 7],
  );
  expect(controller.state, DeviceConnectionState.attached);
  expect(controller.capabilities?.textRows, 6);
  expect(connection.hostPackets.last.type, MkMessage.requestKeyframe);
}

void main() {
  test(
    'runs handshake, atomic frame, virtual keys, and clean detach',
    () async {
      final transport = _FakeSerialTransport();
      final controller = await _openController(transport);
      addTearDown(controller.dispose);
      final connection = transport.connection;

      _attach(controller, connection);

      expect(controller.terminalAvailable, isTrue);
      expect(controller.sendTerminalLine('ver'), isTrue);
      expect(utf8.decode(connection.hostTerminalBytes), 'ver\r');
      connection.sendDeviceTerminal('ver\r\nMK61> ');
      expect(controller.terminalText, contains('ver'));
      expect(controller.terminalText, contains('MK61> '));
      controller.clearTerminal();
      connection.sendDeviceTerminal('abc\b \bD\rXY\r\n');
      expect(controller.terminalText, 'XYD\n');

      final framebuffer = Uint8List(MkGeometry.frameBytes);
      for (var x = 0; x < MkGeometry.width; x++) {
        framebuffer[x] = x.isEven ? 0xaa : 0x55;
      }
      connection.sendDevicePacket(
        MkMessage.frameBegin,
        _frameBegin(1, keyframe: true, rects: 1),
      );
      connection.sendDevicePacket(MkMessage.rect, [
        1,
        0,
        0,
        0,
        MkGeometry.width,
        MkCodec.raw,
        ...framebuffer.sublist(0, MkGeometry.width),
      ]);
      connection.sendDevicePacket(
        MkMessage.frameEnd,
        _frameEnd(1, framebuffer),
      );

      expect(controller.completedFrames, 1);
      expect(controller.framebuffer, framebuffer);

      final packetCountBeforeKeys = connection.hostPackets.length;
      controller.keyDown(39);
      controller.keyDown(
        39,
      ); // Desktop auto-repeat must not duplicate key-down.
      controller.keyUp(39);
      controller.keyDown(37);
      controller.keyDown(38);
      controller.releaseAllKeys();

      final keyPackets = connection.hostPackets.sublist(packetCountBeforeKeys);
      expect(keyPackets.map((packet) => packet.type), [
        MkMessage.keyEvent,
        MkMessage.keyEvent,
        MkMessage.keyEvent,
        MkMessage.keyEvent,
        MkMessage.releaseAllKeys,
      ]);
      expect(keyPackets[0].payload, [39, 1]);
      expect(keyPackets[1].payload, [39, 0]);
      expect(controller.pressedKeys, isEmpty);

      final packetCountBeforeText = connection.hostPackets.length;
      final terminalByteCountBeforeText = connection.hostTerminalBytes.length;
      expect(controller.tapActions(['k', 'digit8', 'digit8']), isTrue);
      expect(controller.tapActions(['not-a-key']), isFalse);
      expect(connection.hostPackets, hasLength(packetCountBeforeText));
      expect(
        utf8.decode(
          connection.hostTerminalBytes.sublist(terminalByteCountBeforeText),
        ),
        'kbd 25\rkbd 12\rkbd 12\r',
      );
      expect(controller.pressedKeys, isEmpty);

      await controller.disconnect();
      expect(connection.hostPackets.last.type, MkMessage.detach);
      expect(controller.state, DeviceConnectionState.disconnected);
      expect(connection.closed, isTrue);
    },
  );

  test(
    'fresh OFFER resets a stale attached session and re-handshakes',
    () async {
      final transport = _FakeSerialTransport();
      final controller = await _openController(transport);
      addTearDown(controller.dispose);
      final connection = transport.connection;
      _attach(controller, connection);

      controller.keyDown(19);
      expect(controller.pressedKeys, contains(19));
      final attachCountBefore = connection.hostPackets
          .where((packet) => packet.type == MkMessage.attach)
          .length;

      connection.sendDevicePacket(
        MkMessage.offer,
        _capabilities(includeProfile: false),
      );
      expect(controller.state, DeviceConnectionState.attaching);
      expect(controller.pressedKeys, isEmpty);
      expect(controller.completedFrames, 0);
      expect(
        connection.hostPackets
            .where((packet) => packet.type == MkMessage.attach)
            .length,
        attachCountBefore + 1,
      );

      connection.sendDevicePacket(
        MkMessage.caps,
        _capabilities(includeProfile: true),
      );
      expect(controller.state, DeviceConnectionState.attached);
      expect(connection.hostPackets.last.type, MkMessage.requestKeyframe);
    },
  );

  test(
    'device DETACH closes cleanly and leaves auto-connect scanning',
    () async {
      final transport = _FakeSerialTransport();
      final controller = await _openController(transport);
      addTearDown(controller.dispose);
      final connection = transport.connection;
      _attach(controller, connection);

      connection.sendDevicePacket(MkMessage.detach);
      await Future<void>.delayed(Duration.zero);

      expect(controller.state, DeviceConnectionState.scanning);
      expect(controller.attached, isFalse);
      expect(controller.hasOpenPort, isFalse);
      expect(controller.lastError, isNull);
      expect(connection.closed, isTrue);
    },
  );

  test(
    'sequence loss and bad framebuffer CRC both request a keyframe',
    () async {
      final transport = _FakeSerialTransport();
      final controller = await _openController(transport);
      addTearDown(controller.dispose);
      final connection = transport.connection;
      _attach(controller, connection);

      final keyframesBefore = connection.hostPackets
          .where((packet) => packet.type == MkMessage.requestKeyframe)
          .length;
      connection.skipDeviceSequence();
      connection.sendDevicePacket(
        MkMessage.frameBegin,
        _frameBegin(9, keyframe: true, rects: 0),
      );
      connection.sendDevicePacket(MkMessage.frameEnd, const [9, 0, 0, 0]);

      expect(controller.sequenceGaps, 1);
      expect(controller.rejectedFrames, 1);
      expect(
        connection.hostPackets
            .where((packet) => packet.type == MkMessage.requestKeyframe)
            .length,
        keyframesBefore + 2,
      );
    },
  );

  test('legacy firmware falls back to binary key taps', () async {
    final transport = _FakeSerialTransport();
    final controller = await _openController(transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;
    _attach(controller, connection, terminalKeyboard: false);

    expect(controller.terminalKeyboardAvailable, isFalse);
    final packetCount = connection.hostPackets.length;
    final terminalByteCount = connection.hostTerminalBytes.length;
    expect(controller.tapActions(['k', 'digit8', 'digit8']), isTrue);
    expect(connection.hostTerminalBytes, hasLength(terminalByteCount));

    final packets = connection.hostPackets.sublist(packetCount);
    expect(packets.map((packet) => packet.type), [
      MkMessage.keyEvent,
      MkMessage.keyEvent,
      MkMessage.keyEvent,
      MkMessage.keyEvent,
      MkMessage.keyEvent,
      MkMessage.keyEvent,
    ]);
    expect(packets.map((packet) => packet.payload), [
      [37, 1],
      [37, 0],
      [18, 1],
      [18, 0],
      [18, 1],
      [18, 0],
    ]);
  });

  test('heartbeat PING/PONG keeps the real controller session alive', () async {
    final transport = _FakeSerialTransport();
    final controller = DeviceController(serialTransport: transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;
    connection.onHostPacket = (packet) {
      if (packet.type == MkMessage.ping) {
        scheduleMicrotask(
          () => connection.sendDevicePacket(MkMessage.pong, packet.payload),
        );
      }
    };

    controller.start();
    for (
      var attempt = 0;
      attempt < 50 && controller.state != DeviceConnectionState.waitingForOffer;
      attempt++
    ) {
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
    expect(controller.state, DeviceConnectionState.waitingForOffer);
    _attach(controller, connection);

    await Future<void>.delayed(const Duration(milliseconds: 850));
    expect(
      connection.hostPackets.any((packet) => packet.type == MkMessage.ping),
      isTrue,
    );
    expect(controller.state, DeviceConnectionState.attached);
    expect(controller.lastError, isNull);
  });
}
