import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../protocol/mk61_protocol.dart';
import 'keyboard_definition.dart';
import 'serial_transport.dart';

enum DeviceConnectionState {
  disconnected,
  scanning,
  opening,
  waitingForOffer,
  attaching,
  attached,
  error,
}

class DeviceController extends ChangeNotifier {
  DeviceController({DeviceSerialTransport? serialTransport})
    : _serialTransport = serialTransport ?? const LibSerialTransport();

  static const _baudRate = 115200;
  static const _scanInterval = Duration(seconds: 1);
  static const _probeTimeout = Duration(milliseconds: 3500);
  static const _attachTimeout = Duration(milliseconds: 1800);
  static const _heartbeatInterval = Duration(milliseconds: 750);
  static const _fallbackHeartbeatTimeout = Duration(milliseconds: 3500);
  static const _terminalLogLimit = 64 * 1024;
  static const _terminalCommandByteLimit = 238;
  static final Uint8List _activateUsbScreenCommand = Uint8List.fromList(
    utf8.encode('uscreen\r'),
  );

  final MkStreamParser _parser = MkStreamParser();
  final FrameAssembler _frames = FrameAssembler();
  final Set<int> _pressedKeys = <int>{};
  final List<int> _terminalBytes = <int>[];
  final DeviceSerialTransport _serialTransport;
  final Stopwatch _clock = Stopwatch()..start();
  final ValueNotifier<int> _displayChanges = ValueNotifier<int>(0);
  final ValueNotifier<int> _terminalChanges = ValueNotifier<int>(0);

  Timer? _scanTimer;
  Timer? _probeTimer;
  Timer? _heartbeatTimer;
  DeviceSerialConnection? _connection;
  StreamSubscription<Uint8List>? _readerSubscription;
  int? _lastPacketMicros;
  int? _lastFrameMicros;
  int? _lastDeviceSequence;
  int _hostSequence = 0;
  int _pingNonce = 0;
  int _probeIndex = 0;
  bool _opening = false;
  bool _closing = false;
  bool _disposed = false;
  bool _allowAutomaticActivation = true;
  bool _activationRequested = false;

  List<String> _ports = const [];
  Map<String, DeviceSerialPort> _portDescriptors = const {};
  String? _selectedPort;
  String? _connectedPort;
  DeviceConnectionState _state = DeviceConnectionState.disconnected;
  DeviceCapabilities? _capabilities;
  String? _lastError;
  bool _autoConnect = true;
  int _rxBytes = 0;
  int _txBytes = 0;
  int _sequenceGaps = 0;
  double _framesPerSecond = 0;
  int _displayRevision = 0;
  int _terminalRevision = 0;
  int _terminalStart = 0;
  int _terminalTextCacheRevision = -1;
  String _terminalTextCache = '';

  List<String> get ports => _ports;
  String? get selectedPort => _selectedPort;
  String? get connectedPort => _connectedPort;
  DeviceConnectionState get state => _state;
  DeviceCapabilities? get capabilities => _capabilities;
  String? get lastError => _lastError;
  bool get autoConnect => _autoConnect;
  bool get attached => _state == DeviceConnectionState.attached;
  bool get hasOpenPort => _connection != null;
  bool get canRequestUsbScreen =>
      _connection != null &&
      _state == DeviceConnectionState.waitingForOffer &&
      !_activationRequested;
  int get rxBytes => _rxBytes;
  int get txBytes => _txBytes;
  int get sequenceGaps => _sequenceGaps;
  int get discardedPackets => _parser.discardedPackets;
  int get completedFrames => _frames.completedFrames;
  int get rejectedFrames => _frames.rejectedFrames;
  double get framesPerSecond => _framesPerSecond;
  int get displayRevision => _displayRevision;
  int get terminalRevision => _terminalRevision;
  ValueListenable<int> get displayChanges => _displayChanges;
  ValueListenable<int> get terminalChanges => _terminalChanges;
  Uint8List get framebuffer => _frames.framebuffer;
  Set<int> get pressedKeys => Set.unmodifiable(_pressedKeys);
  bool get terminalLogEmpty => _terminalBytes.length == _terminalStart;
  String get terminalText {
    if (_terminalTextCacheRevision != _terminalRevision) {
      _terminalTextCache = _renderTerminalText(
        utf8.decode(
          _terminalBytes.sublist(_terminalStart),
          allowMalformed: true,
        ),
      );
      _terminalTextCacheRevision = _terminalRevision;
    }
    return _terminalTextCache;
  }

  bool get keyEventsAvailable =>
      attached && ((_capabilities?.flags ?? 0) & MkCapability.keyEvents) != 0;
  bool get heartbeatAvailable =>
      attached && ((_capabilities?.flags ?? 0) & MkCapability.heartbeat) != 0;
  bool get terminalAvailable =>
      attached && ((_capabilities?.flags ?? 0) & MkCapability.terminalMux) != 0;
  bool get terminalKeyboardAvailable =>
      terminalAvailable &&
      ((_capabilities?.flags ?? 0) & MkCapability.terminalKeyboard) != 0;

  KeyboardDefinition get keyboard => KeyboardDefinition.forLayout(
    _capabilities?.keyboardLayout ?? MkKeyboardLayout.mini,
  );

  String get stateLabel => switch (_state) {
    DeviceConnectionState.disconnected => 'Отключено',
    DeviceConnectionState.scanning => 'Поиск устройства',
    DeviceConnectionState.opening => 'Открытие порта',
    DeviceConnectionState.waitingForOffer =>
      _activationRequested ? 'Включение USB Screen' : 'Ожидание USB Screen',
    DeviceConnectionState.attaching => 'Переключение экрана',
    DeviceConnectionState.attached => 'USB Screen подключён',
    DeviceConnectionState.error => 'Ошибка подключения',
  };

  void start() {
    if (_scanTimer != null || _disposed) return;
    _state = DeviceConnectionState.scanning;
    _scanTimer = Timer.periodic(_scanInterval, (_) => refreshPorts());
    _heartbeatTimer = Timer.periodic(
      _heartbeatInterval,
      (_) => _serviceHeartbeat(),
    );
    unawaited(refreshPorts());
  }

  Future<void> refreshPorts() async {
    if (_disposed) return;
    try {
      final descriptors = _serialTransport.availablePorts.toList()
        ..sort((left, right) => left.name.compareTo(right.name));
      _portDescriptors = Map.unmodifiable({
        for (final descriptor in descriptors) descriptor.name: descriptor,
      });
      final discovered = descriptors
          .map((descriptor) => descriptor.name)
          .toList(growable: false);
      if (!listEquals(discovered, _ports)) {
        _ports = List.unmodifiable(discovered);
        if (_selectedPort == null || !_ports.contains(_selectedPort)) {
          final candidates = _automaticCandidates();
          _selectedPort = candidates.isNotEmpty
              ? candidates.first
              : (_ports.isEmpty ? null : _ports.first);
        }
        _notify();
      }
      if (_autoConnect && _connection == null && !_opening) {
        final candidates = _automaticCandidates();
        if (candidates.isNotEmpty) {
          final candidate = candidates[_probeIndex % candidates.length];
          _probeIndex = (_probeIndex + 1) % candidates.length;
          await _open(candidate, automatic: true);
        } else if (_state != DeviceConnectionState.scanning) {
          _state = DeviceConnectionState.scanning;
          _notify();
        }
      }
    } catch (error) {
      _lastError = 'Не удалось получить список портов: $error';
      _state = DeviceConnectionState.error;
      _notify();
    }
  }

  void selectPort(String? value) {
    if (value == null || !_ports.contains(value) || value == _selectedPort) {
      return;
    }
    _selectedPort = value;
    _allowAutomaticActivation = true;
    _notify();
  }

  void setAutoConnect(bool value) {
    if (_autoConnect == value) return;
    _autoConnect = value;
    if (value) _allowAutomaticActivation = true;
    if (value && _connection == null) {
      _state = DeviceConnectionState.scanning;
      unawaited(refreshPorts());
    }
    _notify();
  }

  Future<void> connectSelected() async {
    final name = _selectedPort;
    if (name == null || _opening) return;
    _allowAutomaticActivation = true;
    await _closePort(sendDetach: attached);
    await _open(name, automatic: false);
  }

  /// Starts USB Screen on an already-open device after an explicit device-side
  /// exit. Initial connections call the same command automatically.
  bool requestUsbScreen() {
    if (!canRequestUsbScreen) return false;
    _allowAutomaticActivation = true;
    _activationRequested = true;
    _lastError = null;
    _probeTimer?.cancel();
    _probeTimer = Timer(_probeTimeout, () {
      if (_state == DeviceConnectionState.waitingForOffer &&
          _activationRequested) {
        _activationRequested = false;
        _lastError = 'Устройство не подтвердило запуск USB Screen';
        _notify();
      }
    });
    if (!_writeBytes(_activateUsbScreenCommand)) {
      _probeTimer?.cancel();
      _probeTimer = null;
      _activationRequested = false;
      return false;
    }
    _notify();
    return true;
  }

  Future<void> disconnect({bool userInitiated = true}) async {
    if (userInitiated) _autoConnect = false;
    await _closePort(sendDetach: attached);
    _state = userInitiated
        ? DeviceConnectionState.disconnected
        : DeviceConnectionState.scanning;
    _markDisplayChanged();
    _lastError = null;
    _notify();
  }

  Future<void> _open(String name, {required bool automatic}) async {
    if (_opening || _disposed) return;
    _opening = true;
    _probeTimer?.cancel();
    _state = DeviceConnectionState.opening;
    _markDisplayChanged();
    _connectedPort = name;
    _selectedPort = name;
    _lastError = null;
    _notify();

    DeviceSerialConnection? candidate;
    try {
      candidate = _serialTransport.open(name, baudRate: _baudRate);
      _connection = candidate;
      _parser.reset();
      _terminalBytes.clear();
      _terminalStart = 0;
      _markTerminalChanged();
      _frames.reset();
      _lastDeviceSequence = null;
      _lastPacketMicros = _clock.elapsedMicroseconds;
      _hostSequence = 0;
      _capabilities = null;
      _pressedKeys.clear();
      _activationRequested = false;
      _state = DeviceConnectionState.waitingForOffer;
      _probeTimer = Timer(_probeTimeout, () {
        if (_state == DeviceConnectionState.waitingForOffer) {
          unawaited(_probeExpired(automatic));
        }
      });
      // Reset all session state before subscribing: a synchronous/fresh CDC
      // stream is allowed to deliver an OFFER immediately from listen().
      _readerSubscription = candidate.input.listen(
        (bytes) {
          if (identical(_connection, candidate)) _onBytes(bytes);
        },
        onError: (Object error, StackTrace stack) {
          if (identical(_connection, candidate)) {
            unawaited(_connectionFailed('Ошибка чтения $name: $error'));
          }
        },
        onDone: () {
          if (identical(_connection, candidate)) {
            unawaited(_connectionFailed('Порт $name был закрыт'));
          }
        },
        cancelOnError: false,
      );
      if (_allowAutomaticActivation &&
          _state == DeviceConnectionState.waitingForOffer) {
        _activationRequested = true;
        if (!_writeBytes(_activateUsbScreenCommand)) {
          _activationRequested = false;
        }
      }
      _notify();
    } catch (error) {
      if (candidate != null) {
        if (identical(candidate, _connection)) _connection = null;
        candidate.close();
      }
      _lastError = automatic ? null : 'Не удалось открыть $name: $error';
      _state = automatic
          ? DeviceConnectionState.scanning
          : DeviceConnectionState.error;
      _connectedPort = null;
      _notify();
    } finally {
      _opening = false;
    }
  }

  Future<void> _probeExpired(bool automatic) async {
    await _closePort(sendDetach: false);
    _state = automatic
        ? DeviceConnectionState.scanning
        : DeviceConnectionState.error;
    _markDisplayChanged();
    _lastError = automatic
        ? null
        : 'На выбранном порту нет предложения USB Screen';
    _notify();
  }

  void _onBytes(Uint8List bytes) {
    if (_disposed || _connection == null) return;
    _rxBytes += bytes.length;
    final discardedBefore = _parser.discardedPackets;
    final packets = _parser.add(bytes);
    final terminalBytes = _parser.takeTerminalBytes();
    if (terminalBytes.isNotEmpty) _appendTerminal(terminalBytes);
    if (_parser.discardedPackets != discardedBefore && attached) {
      _send(MkMessage.requestKeyframe);
    }
    for (final packet in packets) {
      _onPacket(packet);
    }
  }

  void _onPacket(MkPacket packet) {
    _lastPacketMicros = _clock.elapsedMicroseconds;
    final previous = _lastDeviceSequence;
    if (previous != null && packet.sequence != ((previous + 1) & 0xffff)) {
      _sequenceGaps++;
      if (attached) _send(MkMessage.requestKeyframe);
    }
    _lastDeviceSequence = packet.sequence;

    switch (packet.type) {
      case MkMessage.offer:
        _handleOffer(packet.payload);
        return;
      case MkMessage.caps:
        _handleCapabilities(packet.payload);
        return;
      case MkMessage.frameBegin:
      case MkMessage.rect:
      case MkMessage.frameEnd:
        if (!attached) return;
        final rejectedBefore = _frames.rejectedFrames;
        final complete = _frames.consume(packet);
        if (_frames.rejectedFrames != rejectedBefore) {
          _lastError = _frames.lastError;
          _send(MkMessage.requestKeyframe);
          _notify();
        }
        if (complete) _frameCompleted();
        return;
      case MkMessage.pong:
        // Receipt itself refreshes the monotonic packet timestamp.
        return;
      case MkMessage.detach:
        _deviceDetached();
        return;
    }
  }

  void _handleOffer(List<int> payload) {
    if (_state != DeviceConnectionState.waitingForOffer &&
        _state != DeviceConnectionState.attaching &&
        _state != DeviceConnectionState.attached) {
      return;
    }
    try {
      final offer = DeviceCapabilities.parse(payload);
      if (!offer.validGeometry) {
        throw FormatException(
          'ожидался экран ${MkGeometry.width}×${MkGeometry.height}',
        );
      }

      // The device deliberately returns to WAITING_FOR_HOST after its
      // heartbeat expires.  The serial port may still be open (for example
      // after a suspended laptop resumes), so a fresh OFFER is the session
      // reset signal even when the client still believed it was attached.
      final wasAttached = attached;
      if (wasAttached) {
        _pressedKeys.clear();
        _frames.reset();
        _lastFrameMicros = null;
        _framesPerSecond = 0;
      }
      _capabilities = offer;
      _activationRequested = false;
      _state = DeviceConnectionState.attaching;
      if (wasAttached) _markDisplayChanged();
      _probeTimer?.cancel();
      _send(MkMessage.attach);
      _probeTimer = Timer(_attachTimeout, () {
        if (_state == DeviceConnectionState.attaching) {
          unawaited(_connectionFailed('Устройство не подтвердило подключение'));
        }
      });
      _notify();
    } on FormatException catch (error) {
      unawaited(_connectionFailed('Несовместимое устройство: $error'));
    }
  }

  void _handleCapabilities(List<int> payload) {
    if (_state != DeviceConnectionState.attaching && !attached) return;
    try {
      final caps = DeviceCapabilities.parse(payload);
      if (!caps.validGeometry ||
          (caps.flags & MkCapability.atomicFrames) == 0) {
        throw const FormatException('неподдерживаемая геометрия или кадры');
      }
      _capabilities = caps;
      _probeTimer?.cancel();
      _frames.reset();
      _state = DeviceConnectionState.attached;
      _markDisplayChanged();
      _lastError = null;
      _send(MkMessage.requestKeyframe);
      _notify();
    } on FormatException catch (error) {
      unawaited(_connectionFailed('Несовместимые возможности: $error'));
    }
  }

  void _frameCompleted() {
    final clearedError = _lastError != null;
    _lastError = null;
    final now = _clock.elapsedMicroseconds;
    final previous = _lastFrameMicros;
    if (previous != null) {
      final micros = now - previous;
      if (micros > 0) {
        final instant = 1000000 / micros;
        _framesPerSecond = _framesPerSecond == 0
            ? instant.toDouble()
            : _framesPerSecond * 0.8 + instant * 0.2;
      }
    }
    _lastFrameMicros = now;
    _markDisplayChanged();
    if (clearedError) _notify();
  }

  void _serviceHeartbeat() {
    if (_disposed || _connection == null) return;
    if (heartbeatAvailable) {
      final timeoutMs = _capabilities?.heartbeatTimeoutMs;
      final timeout = timeoutMs != null && timeoutMs > 0
          ? Duration(milliseconds: timeoutMs + 500)
          : _fallbackHeartbeatTimeout;
      final lastPacket = _lastPacketMicros;
      if (lastPacket != null &&
          _clock.elapsedMicroseconds - lastPacket > timeout.inMicroseconds) {
        unawaited(_connectionFailed('Устройство перестало отвечать'));
        return;
      }
      final payload = Uint8List(2);
      MkProtocol.writeU16(payload, 0, _pingNonce++ & 0xffff);
      _send(MkMessage.ping, payload);
    }
  }

  void keyDown(int scanCode) {
    final keyCount = _capabilities?.keyCount ?? 0;
    if (!keyEventsAvailable || scanCode < 0 || scanCode >= keyCount) return;
    if (!_pressedKeys.add(scanCode)) return;
    _send(MkMessage.keyEvent, [scanCode, 1]);
    _notify();
  }

  void keyUp(int scanCode) {
    if (!_pressedKeys.remove(scanCode)) return;
    if (keyEventsAvailable) _send(MkMessage.keyEvent, [scanCode, 0]);
    _notify();
  }

  void releaseAllKeys() {
    if (_pressedKeys.isEmpty) return;
    _pressedKeys.clear();
    if (keyEventsAvailable) _send(MkMessage.releaseAllKeys);
    _notify();
  }

  /// Sends a short sequence through the firmware's `kbd <scan-code>` terminal
  /// command. Unlike synthetic down/up pairs, `kbd` inserts one press directly
  /// into the calculator keyboard queue, which preserves repeated SMS taps.
  bool tapActions(Iterable<String> actions) {
    if (!attached) return false;
    final scanCodes = <int>[];
    for (final action in actions) {
      final scanCode = keyboard.scanCodeFor(action);
      if (scanCode == null || _pressedKeys.contains(scanCode)) return false;
      scanCodes.add(scanCode);
    }
    if (scanCodes.isEmpty) return false;

    if (!terminalKeyboardAvailable) {
      return keyEventsAvailable && _tapLegacy(scanCodes);
    }

    final commands = StringBuffer();
    for (final scanCode in scanCodes) {
      commands
        ..write('kbd ')
        ..write(scanCode.toRadixString(16).padLeft(2, '0'))
        ..writeCharCode(0x0d);
    }
    return _writeBytes(Uint8List.fromList(utf8.encode(commands.toString())));
  }

  bool _tapLegacy(List<int> scanCodes) {
    for (final scanCode in scanCodes) {
      _pressedKeys.add(scanCode);
      if (!_send(MkMessage.keyEvent, [scanCode, 1])) {
        _pressedKeys.remove(scanCode);
        _notify();
        return false;
      }
      _pressedKeys.remove(scanCode);
      if (!_send(MkMessage.keyEvent, [scanCode, 0])) {
        _notify();
        return false;
      }
    }
    _notify();
    return true;
  }

  bool sendTerminalLine(String line) {
    if (!terminalAvailable) return false;
    final sanitized = line.replaceAll(RegExp(r'[\x00\r\n]'), '');
    final encoded = utf8.encode(sanitized);
    if (encoded.length > _terminalCommandByteLimit) {
      _lastError = 'Команда терминала длиннее $_terminalCommandByteLimit байт';
      _notify();
      return false;
    }
    return _writeBytes(Uint8List.fromList([...encoded, 0x0d]));
  }

  void clearTerminal() {
    if (terminalLogEmpty) return;
    _terminalBytes.clear();
    _terminalStart = 0;
    _markTerminalChanged();
  }

  void _appendTerminal(List<int> bytes) {
    if (bytes.isEmpty) return;
    _terminalBytes.addAll(bytes);
    final overflow = _terminalBytes.length - _terminalStart - _terminalLogLimit;
    if (overflow > 0) _terminalStart += overflow;
    // Compact only after a complete extra log window has accumulated. This
    // turns per-chunk front deletion into amortized O(1) appends.
    if (_terminalStart >= _terminalLogLimit &&
        _terminalStart * 2 >= _terminalBytes.length) {
      _terminalBytes.removeRange(0, _terminalStart);
      _terminalStart = 0;
    }
    _markTerminalChanged();
  }

  bool _send(int type, [List<int> payload = const []]) {
    final connection = _connection;
    if (connection == null) return false;
    try {
      final packet = MkProtocol.encodePacket(
        type: type,
        sequence: _hostSequence++ & 0xffff,
        payload: payload,
      );
      return _writeBytes(packet);
    } catch (error) {
      if (!_closing) unawaited(_connectionFailed('Ошибка записи: $error'));
      return false;
    }
  }

  bool _writeBytes(Uint8List bytes) {
    final connection = _connection;
    if (connection == null) return false;
    try {
      final written = connection.write(bytes, timeoutMs: 100);
      _txBytes += written;
      if (written != bytes.length) {
        throw StateError('записано $written из ${bytes.length} байт');
      }
      return true;
    } catch (error) {
      if (!_closing) unawaited(_connectionFailed('Ошибка записи: $error'));
      return false;
    }
  }

  Future<void> _connectionFailed(String message) async {
    if (_connection == null || _disposed || _closing) return;
    _lastError = message;
    // A physical reconnect is a new user-visible connection and may activate
    // USB Screen again even if the previous live session was exited manually.
    _allowAutomaticActivation = true;
    await _closePort(sendDetach: false);
    _state = _autoConnect
        ? DeviceConnectionState.scanning
        : DeviceConnectionState.error;
    _markDisplayChanged();
    _notify();
  }

  void _deviceDetached() {
    if (_connection == null || _disposed || _closing) return;
    _probeTimer?.cancel();
    _probeTimer = null;
    _allowAutomaticActivation = false;
    _activationRequested = false;
    _pressedKeys.clear();
    _capabilities = null;
    _lastDeviceSequence = null;
    _lastPacketMicros = _clock.elapsedMicroseconds;
    _lastFrameMicros = null;
    _framesPerSecond = 0;
    _frames.reset();
    _lastError = null;
    _state = DeviceConnectionState.waitingForOffer;
    _markDisplayChanged();
    _notify();
  }

  Future<void> _closePort({required bool sendDetach}) async {
    if (_closing) return;
    _closing = true;
    try {
      _probeTimer?.cancel();
      _probeTimer = null;
      if (sendDetach && _connection != null) {
        if (_pressedKeys.isNotEmpty) _send(MkMessage.releaseAllKeys);
        _send(MkMessage.detach);
        try {
          _connection?.drain();
        } catch (_) {
          // A removed USB device cannot be drained; heartbeat/firmware escape
          // remains the bounded fallback for that physical failure.
        }
      }
      _pressedKeys.clear();

      final connection = _connection;
      _connection = null;
      final subscription = _readerSubscription;
      _readerSubscription = null;
      if (subscription != null) {
        try {
          await subscription.cancel();
        } catch (_) {
          // The OS may already have removed the port.
        }
      }
      connection?.close();
      _connectedPort = null;
      _capabilities = null;
      _activationRequested = false;
      _lastDeviceSequence = null;
      _lastPacketMicros = null;
      _lastFrameMicros = null;
      _framesPerSecond = 0;
      _frames.reset();
    } finally {
      _closing = false;
    }
  }

  List<String> _automaticCandidates() {
    return _ports
        .where((name) => _portDescriptors[name]?.isAutomaticCandidate ?? false)
        .toList(growable: false);
  }

  void _markDisplayChanged() {
    _displayRevision++;
    if (!_disposed) _displayChanges.value = _displayRevision;
  }

  void _markTerminalChanged() {
    _terminalRevision++;
    if (!_disposed) _terminalChanges.value = _terminalRevision;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _scanTimer?.cancel();
    _heartbeatTimer?.cancel();
    _probeTimer?.cancel();
    if (_connection != null) {
      if (_pressedKeys.isNotEmpty) _send(MkMessage.releaseAllKeys);
      _send(MkMessage.detach);
      try {
        _connection?.drain();
      } catch (_) {
        // Best effort during synchronous widget teardown.
      }
    }
    _readerSubscription?.cancel();
    final connection = _connection;
    _connection = null;
    connection?.close();
    _displayChanges.dispose();
    _terminalChanges.dispose();
    super.dispose();
  }
}

String _renderTerminalText(String source) {
  final lines = <List<int>>[<int>[]];
  var row = 0;
  var column = 0;

  for (final rune in source.runes) {
    switch (rune) {
      case 0x0d: // carriage return
        column = 0;
        continue;
      case 0x0a: // line feed
        row++;
        column = 0;
        if (row == lines.length) lines.add(<int>[]);
        continue;
      case 0x08: // backspace
        if (column > 0) column--;
        continue;
      case 0x09: // tab
        final spaces = 4 - (column & 3);
        for (var i = 0; i < spaces; i++) {
          final line = lines[row];
          if (column < line.length) {
            line[column] = 0x20;
          } else {
            line.add(0x20);
          }
          column++;
        }
        continue;
    }
    if (rune < 0x20 || rune == 0x7f) continue;
    final line = lines[row];
    while (line.length < column) {
      line.add(0x20);
    }
    if (column < line.length) {
      line[column] = rune;
    } else {
      line.add(rune);
    }
    column++;
  }

  return lines.map(String.fromCharCodes).join('\n');
}
