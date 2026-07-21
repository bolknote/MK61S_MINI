import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

abstract interface class DeviceSerialTransport {
  List<String> get availablePorts;

  DeviceSerialConnection open(String name, {required int baudRate});
}

abstract interface class DeviceSerialConnection {
  Stream<Uint8List> get input;

  int write(Uint8List bytes, {required int timeoutMs});

  void close();
}

class LibSerialTransport implements DeviceSerialTransport {
  const LibSerialTransport();

  @override
  List<String> get availablePorts => SerialPort.availablePorts;

  @override
  DeviceSerialConnection open(String name, {required int baudRate}) {
    final port = SerialPort(name);
    try {
      if (!port.openReadWrite()) {
        throw SerialPort.lastError ?? StateError('порт не открылся');
      }

      final config = SerialPortConfig()
        ..baudRate = baudRate
        ..bits = 8
        ..parity = SerialPortParity.none
        ..stopBits = 1;
      config.setFlowControl(SerialPortFlowControl.none);
      try {
        port.config = config;
      } finally {
        config.dispose();
      }
      return _LibSerialConnection(port);
    } catch (_) {
      try {
        if (port.isOpen) port.close();
      } catch (_) {
        // Best effort while abandoning a failed candidate.
      }
      port.dispose();
      rethrow;
    }
  }
}

class _LibSerialConnection implements DeviceSerialConnection {
  _LibSerialConnection(this._port)
    : _reader = SerialPortReader(_port, timeout: 100);

  final SerialPort _port;
  final SerialPortReader _reader;
  bool _closed = false;

  @override
  Stream<Uint8List> get input => _reader.stream;

  @override
  int write(Uint8List bytes, {required int timeoutMs}) =>
      _port.write(bytes, timeout: timeoutMs);

  @override
  void close() {
    if (_closed) return;
    _closed = true;
    _reader.close();
    try {
      if (_port.isOpen) _port.close();
    } catch (_) {
      // The OS may already have removed the port.
    }
    _port.dispose();
  }
}
