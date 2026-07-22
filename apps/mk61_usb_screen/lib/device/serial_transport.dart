import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

class DeviceSerialPort {
  const DeviceSerialPort({
    required this.name,
    this.description,
    this.vendorId,
    this.productId,
    this.manufacturer,
    this.productName,
    this.serialNumber,
  });

  final String name;
  final String? description;
  final int? vendorId;
  final int? productId;
  final String? manufacturer;
  final String? productName;
  final String? serialNumber;

  /// Automatic activation is deliberately limited to the USB identity used by
  /// MK61 firmware. Port names such as COM3 or ttyUSB0 are not evidence: they
  /// may belong to modems, UPSes, debug consoles, or unrelated controllers.
  bool get isAutomaticCandidate {
    if (vendorId != 0x0483 || productId != 0x5740) return false;
    final identity = [
      description,
      manufacturer,
      productName,
    ].whereType<String>().join(' ').toLowerCase();
    return identity.contains('mk61') ||
        identity.contains('mk-61') ||
        identity.contains('blackpill_f411ce') ||
        identity.contains('blackpill f411ce');
  }
}

abstract interface class DeviceSerialTransport {
  List<DeviceSerialPort> get availablePorts;

  DeviceSerialConnection open(String name, {required int baudRate});
}

abstract interface class DeviceSerialConnection {
  Stream<Uint8List> get input;

  int write(Uint8List bytes, {required int timeoutMs});

  void drain();

  void close();
}

class LibSerialTransport implements DeviceSerialTransport {
  const LibSerialTransport();

  @override
  List<DeviceSerialPort> get availablePorts =>
      SerialPort.availablePorts.map(_describePort).toList(growable: false);

  static DeviceSerialPort _describePort(String name) {
    final port = SerialPort(name);
    try {
      return DeviceSerialPort(
        name: name,
        description: port.description,
        vendorId: port.vendorId,
        productId: port.productId,
        manufacturer: port.manufacturer,
        productName: port.productName,
        serialNumber: port.serialNumber,
      );
    } catch (_) {
      // Keep the port available for an explicit user-selected connection, but
      // never auto-probe it when its USB identity cannot be read safely.
      return DeviceSerialPort(name: name);
    } finally {
      port.dispose();
    }
  }

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
      try {
        config.setFlowControl(SerialPortFlowControl.none);
      } catch (_) {
        // The port does not own the config until it is assigned below.
        config.dispose();
        rethrow;
      }
      // libserialport retains the assigned config and releases it from
      // SerialPort.dispose(). Disposing it here would make closing the port
      // free the same native pointer twice.
      port.config = config;
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
  void drain() => _port.drain();

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
