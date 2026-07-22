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
  _FakeSerialTransport({List<DeviceSerialPort>? ports})
    : _ports =
          ports ??
          const [
            DeviceSerialPort(
              name: portName,
              vendorId: 0x0483,
              productId: 0x5740,
              manufacturer: 'STMicroelectronics',
              productName: 'BLACKPILL_F411CE CDC in FS Mode',
            ),
          ];

  List<DeviceSerialPort> _ports;
  final _FakeSerialConnection connection = _FakeSerialConnection();
  int openCount = 0;
  int? openedBaudRate;

  void replacePorts(List<DeviceSerialPort> ports) {
    _ports = List<DeviceSerialPort>.of(ports);
  }

  @override
  List<DeviceSerialPort> get availablePorts => _ports;

  @override
  DeviceSerialConnection open(String name, {required int baudRate}) {
    if (!_ports.any((port) => port.name == name)) {
      throw StateError('unexpected port $name');
    }
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
  bool drained = false;

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

  void sendDeviceTerminalBytes(List<int> bytes) {
    _input.add(Uint8List.fromList(bytes));
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
  void drain() {
    if (closed) throw StateError('connection is closed');
    drained = true;
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
  bool keyEvents = true,
  bool heartbeat = true,
  bool terminalMux = true,
  bool terminalKeyboard = true,
}) => [
  192,
  0,
  64,
  8,
  MkCapability.packBits |
      (keyEvents ? MkCapability.keyEvents : 0) |
      (heartbeat ? MkCapability.heartbeat : 0) |
      MkCapability.atomicFrames |
      (terminalMux ? MkCapability.terminalMux : 0) |
      (terminalMux && terminalKeyboard ? MkCapability.terminalKeyboard : 0),
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
  expect(controller.stateLabel, 'Включение USB Screen');
  expect(utf8.decode(transport.connection.hostTerminalBytes), 'uscreen\r');
  return controller;
}

void _attach(
  DeviceController controller,
  _FakeSerialConnection connection, {
  bool keyEvents = true,
  bool heartbeat = true,
  bool terminalMux = true,
  bool terminalKeyboard = true,
}) {
  connection.sendDevicePacket(
    MkMessage.offer,
    _capabilities(
      includeProfile: false,
      keyEvents: keyEvents,
      heartbeat: heartbeat,
      terminalMux: terminalMux,
      terminalKeyboard: terminalKeyboard,
    ),
    const [1, 2, 5, 3],
  );
  expect(controller.state, DeviceConnectionState.attaching);
  expect(connection.hostPackets.last.type, MkMessage.attach);

  connection.sendDevicePacket(
    MkMessage.caps,
    _capabilities(
      includeProfile: true,
      keyEvents: keyEvents,
      heartbeat: heartbeat,
      terminalMux: terminalMux,
      terminalKeyboard: terminalKeyboard,
    ),
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
      expect(utf8.decode(connection.hostTerminalBytes), 'uscreen\rver\r');
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
      expect(connection.drained, isTrue);
      expect(controller.state, DeviceConnectionState.disconnected);
      expect(connection.closed, isTrue);
    },
  );

  test('renders the supported ANSI terminal subset', () async {
    final transport = _FakeSerialTransport();
    final controller = await _openController(transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;
    _attach(controller, connection);

    connection.sendDeviceTerminal('ABCDE\x1b[2Dxy');
    expect(controller.terminalText, 'ABCxy');

    controller.clearTerminal();
    connection.sendDeviceTerminal('abc\n123\x1b[1;2HZ');
    expect(controller.terminalText, 'aZc\n123');

    controller.clearTerminal();
    connection.sendDeviceTerminal('A\nB\x1b[1A\x1b[1CX\x1b[1B\x1b[1CY');
    expect(controller.terminalText, 'A X\nB   Y');

    controller.clearTerminal();
    connection.sendDeviceTerminal('abc\n123\x1b[1;3fZ');
    expect(controller.terminalText, 'abZ\n123');

    controller.clearTerminal();
    connection.sendDeviceTerminal('abcdef\x1b[3D\x1b[K');
    expect(controller.terminalText, 'abc');

    controller.clearTerminal();
    connection.sendDeviceTerminal('abcdef\r\x1b[3C\x1b[1K');
    expect(controller.terminalText, '    ef');

    controller.clearTerminal();
    connection.sendDeviceTerminal('abc\x1b[sXY\x1b[uZ');
    expect(controller.terminalText, 'abcZY');

    controller.clearTerminal();
    connection.sendDeviceTerminal('abc\x1b7XY\x1b8Z');
    expect(controller.terminalText, 'abcZY');

    controller.clearTerminal();
    connection.sendDeviceTerminal('old\ntext\x1b[2J\x1b[Hnew');
    expect(controller.terminalText, 'new');

    controller.clearTerminal();
    connection.sendDeviceTerminal('old\x1b[');
    expect(controller.terminalText, 'old');
    connection.sendDeviceTerminal('2J\x1b[Hnew');
    expect(controller.terminalText, 'new');

    controller.clearTerminal();
    connection.sendDeviceTerminal('A\x1b[31mB\x1b[0mC');
    expect(controller.terminalText, 'ABC');

    controller.clearTerminal();
    connection.sendDeviceTerminalBytes([0x41, 0xff, 0x42]);
    expect(controller.terminalText, 'A\uFFFDB');
  });

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
    'device DETACH stops auto-activation and allows an explicit restart',
    () async {
      final transport = _FakeSerialTransport();
      final controller = await _openController(transport);
      addTearDown(controller.dispose);
      final connection = transport.connection;
      _attach(controller, connection);
      final terminalBytesBeforeDetach = connection.hostTerminalBytes.length;

      connection.sendDevicePacket(MkMessage.detach);

      expect(controller.state, DeviceConnectionState.waitingForOffer);
      expect(controller.attached, isFalse);
      expect(controller.hasOpenPort, isTrue);
      expect(controller.lastError, isNull);
      expect(connection.closed, isFalse);
      expect(controller.canRequestUsbScreen, isTrue);
      expect(
        connection.hostTerminalBytes,
        hasLength(terminalBytesBeforeDetach),
      );

      expect(controller.requestUsbScreen(), isTrue);
      expect(controller.stateLabel, 'Включение USB Screen');
      expect(controller.canRequestUsbScreen, isFalse);
      expect(
        utf8.decode(
          connection.hostTerminalBytes.sublist(terminalBytesBeforeDetach),
        ),
        'uscreen\r',
      );

      _attach(controller, connection);
      expect(controller.state, DeviceConnectionState.attached);
    },
  );

  test('activation is retried until the firmware offers USB Screen', () async {
    final transport = _FakeSerialTransport();
    final controller = await _openController(transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;

    await Future<void>.delayed(const Duration(milliseconds: 450));
    expect(utf8.decode(connection.hostTerminalBytes), 'uscreen\ruscreen\r');

    _attach(controller, connection);
    final bytesAfterAttach = connection.hostTerminalBytes.length;
    await Future<void>.delayed(const Duration(milliseconds: 450));
    expect(connection.hostTerminalBytes, hasLength(bytesAfterAttach));
  });

  test('a CDC port disappearing closes its stale serial connection', () async {
    final transport = _FakeSerialTransport();
    final controller = await _openController(transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;

    transport.replacePorts(const []);
    await controller.refreshPorts();

    expect(connection.closed, isTrue);
    expect(controller.hasOpenPort, isFalse);
    expect(controller.connectedPort, isNull);
    expect(controller.selectedPort, isNull);
    expect(controller.state, DeviceConnectionState.scanning);
  });

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

  test('key events work without terminal multiplexing', () async {
    final transport = _FakeSerialTransport();
    final controller = await _openController(transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;
    _attach(controller, connection, terminalMux: false);

    expect(controller.terminalAvailable, isFalse);
    expect(controller.keyEventsAvailable, isTrue);
    final packetCount = connection.hostPackets.length;
    expect(controller.tapActions(['left']), isTrue);
    controller.keyDown(19);
    controller.keyUp(19);

    final packets = connection.hostPackets.sublist(packetCount);
    expect(packets.map((packet) => packet.type), [
      MkMessage.keyEvent,
      MkMessage.keyEvent,
      MkMessage.keyEvent,
      MkMessage.keyEvent,
    ]);
  });

  test('unsupported key and heartbeat capabilities are never used', () async {
    final transport = _FakeSerialTransport();
    final controller = DeviceController(serialTransport: transport);
    addTearDown(controller.dispose);
    controller.start();
    for (
      var attempt = 0;
      attempt < 50 && controller.state != DeviceConnectionState.waitingForOffer;
      attempt++
    ) {
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
    final connection = transport.connection;
    _attach(
      controller,
      connection,
      keyEvents: false,
      heartbeat: false,
      terminalMux: false,
    );
    final packetCount = connection.hostPackets.length;

    controller.keyDown(19);
    controller.keyUp(19);
    expect(controller.tapActions(['left']), isFalse);
    await Future<void>.delayed(const Duration(milliseconds: 850));

    expect(controller.pressedKeys, isEmpty);
    expect(
      connection.hostPackets
          .sublist(packetCount)
          .where((packet) => packet.type == MkMessage.ping),
      isEmpty,
    );
  });

  test(
    'automatic discovery never writes to an unidentified serial port',
    () async {
      const unrelatedName = 'COM7';
      final transport = _FakeSerialTransport(
        ports: const [DeviceSerialPort(name: unrelatedName)],
      );
      final controller = DeviceController(serialTransport: transport);
      addTearDown(controller.dispose);

      await controller.refreshPorts();
      expect(controller.ports, [unrelatedName]);
      expect(controller.selectedPort, unrelatedName);
      expect(controller.state, DeviceConnectionState.scanning);
      expect(transport.openCount, 0);
      expect(transport.connection.hostTerminalBytes, isEmpty);

      // An explicit selection is the user's authorization to probe a custom
      // board whose descriptors are not on the automatic allowlist.
      await controller.connectSelected();
      expect(transport.openCount, 1);
      expect(utf8.decode(transport.connection.hostTerminalBytes), 'uscreen\r');
    },
  );

  test('USB identity, not a tempting port name, controls auto-probing', () {
    const disguised = DeviceSerialPort(
      name: '/dev/cu.usbmodem-MK61',
      vendorId: 0x1234,
      productId: 0x5740,
      productName: 'BLACKPILL_F411CE CDC in FS Mode',
    );
    const known = DeviceSerialPort(
      name: 'COM42',
      vendorId: 0x0483,
      productId: 0x5740,
      productName: 'BLACKPILL_F411CE CDC in FS Mode',
    );
    expect(disguised.isAutomaticCandidate, isFalse);
    expect(known.isAutomaticCandidate, isTrue);
  });

  test('frame and terminal traffic use isolated update channels', () async {
    final transport = _FakeSerialTransport();
    final controller = await _openController(transport);
    addTearDown(controller.dispose);
    final connection = transport.connection;
    _attach(controller, connection);

    var generalChanges = 0;
    var displayChanges = 0;
    var terminalChanges = 0;
    controller.addListener(() => generalChanges++);
    controller.displayChanges.addListener(() => displayChanges++);
    controller.terminalChanges.addListener(() => terminalChanges++);

    final framebuffer = Uint8List(MkGeometry.frameBytes);
    connection.sendDevicePacket(
      MkMessage.frameBegin,
      _frameBegin(7, keyframe: true, rects: 0),
    );
    connection.sendDevicePacket(MkMessage.frameEnd, _frameEnd(7, framebuffer));
    expect(displayChanges, 1);
    expect(generalChanges, 0);

    connection.sendDeviceTerminal('terminal-only');
    expect(terminalChanges, 1);
    expect(generalChanges, 0);
    expect(controller.terminalText, 'terminal-only');

    final longChunk = String.fromCharCodes(List<int>.filled(70 * 1024, 0x78));
    connection.sendDeviceTerminal(longChunk);
    expect(controller.terminalText.length, 64 * 1024);
    expect(
      controller.terminalText.endsWith('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'),
      isTrue,
    );
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
