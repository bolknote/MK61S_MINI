using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading;

namespace Mk61.ArduinoE2E {
    // Only the physical programmer/serial boundary is simulated. The host
    // still discovers identities and sends every C6 command and payload.
    public static class Device {
        public static string Root {
            get {
                string root = Environment.GetEnvironmentVariable("MK61_E2E_ROOT");
                if (String.IsNullOrEmpty(root)) throw new Exception("No test device root");
                return root;
            }
        }
        public static string Mode {
            get { string p = Path.Combine(Root, "mode"); return File.Exists(p) ? File.ReadAllText(p).Trim() : ""; }
        }
        public static int Count(string name) {
            string p = Path.Combine(Root, name);
            int n = File.Exists(p) ? Int32.Parse(File.ReadAllText(p)) : 0;
            File.WriteAllText(p, (n + 1).ToString());
            return n + 1;
        }
        public static string[] Ports() {
            int n = Count("discoveries");
            if (Mode == "missing-port" || (Mode == "delayed-port" && n < 3)) return new string[0];
            return Mode == "multiple" ? new string[] {"COM71", "COM72"} : new string[] {"COM71"};
        }
        public static uint Fnv(string value) {
            uint hash = 2166136261;
            foreach (byte b in Encoding.ASCII.GetBytes(value)) hash = unchecked((hash ^ b) * 16777619);
            return hash;
        }
        public static string[] FirmwareIdentity(string image) {
            byte[] data = File.ReadAllBytes(image);
            byte[] magic = Encoding.ASCII.GetBytes("MK61FWC\0");
            int found = -1;
            for (int i = 0; i + 40 <= data.Length; i++) {
                bool same = true;
                for (int j = 0; j < magic.Length; j++) if (data[i+j] != magic[j]) same = false;
                if (!same) continue;
                if (BitConverter.ToUInt16(data, i+8) != 1 ||
                    BitConverter.ToUInt16(data, i+10) != 40 ||
                    BitConverter.ToUInt32(data, i+12) != 0x08000000) continue;
                if (found >= 0 || i % 4 != 0) throw new Exception("Invalid firmware footer");
                found = i;
            }
            if (found < 0 || BitConverter.ToUInt16(data, found+8) != 1 ||
                BitConverter.ToUInt16(data, found+10) != 40 ||
                BitConverter.ToUInt32(data, found+12) != 0x08000000 ||
                BitConverter.ToUInt32(data, found+16) != data.Length ||
                BitConverter.ToUInt32(data, found+32) != 1 ||
                BitConverter.ToUInt32(data, found+36) != 0) throw new Exception("Unsealed firmware");
            uint build = BitConverter.ToUInt32(data, found+24);
            uint crc = 0xffffffff;
            for (int i = 0; i < data.Length; i++) {
                byte b = (i >= found+20 && i < found+28) ? (byte)0 : data[i];
                crc ^= b;
                for (int j = 0; j < 8; j++) crc = (crc & 1) == 0 ? crc >> 1 : (crc >> 1) ^ 0xedb88320;
            }
            if (build == 0 || build != ~crc || build != BitConverter.ToUInt32(data, found+20))
                throw new Exception("Flashed firmware CRC mismatch");
            uint hash = BitConverter.ToUInt32(data, found+28);
            foreach (string profile in new string[] {"mini-v2-a00", "mini-v2-a02",
                    "mini-v3-a00", "mini-v3-a02", "mini-v3-ws0010",
                    "classic-v2-uc1609", "classic-v3-uc1609", "40th-uc1609"}) {
                if (Fnv(profile) == hash) return new string[] {profile, build.ToString("X8")};
            }
            throw new Exception("Unknown compiled firmware profile");
        }
        public static uint Checksum(byte[] bytes) {
            uint crc = 0;
            foreach (byte b in bytes) crc = CrcByte(crc, b);
            int length = bytes.Length;
            while (length != 0) { crc = CrcByte(crc, (byte)(length & 255)); length >>= 8; }
            return ~crc;
        }
        private static uint CrcByte(uint crc, byte b) {
            crc ^= (uint)b << 24;
            for (int i = 0; i < 8; i++) crc = (crc & 0x80000000) == 0 ? crc << 1 : (crc << 1) ^ 0x04c11db7;
            return crc;
        }
        public static byte[] M8(byte[] utf8) {
            string text = new UTF8Encoding(false, true).GetString(utf8);
            if (text.Length > 0 && text[0] == '\ufeff') text = text.Substring(1);
            string privateChars = "\u2190\u2192\u2191\u2193\u03c0\u221a\u21bb\u2260\u2264\u2265\u00d7\u00f7\u00b2\u02b8\u02e3\u22bb\u207b\u21b5";
            Encoding cp = Encoding.GetEncoding(1251, EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback);
            List<byte> result = new List<byte>();
            foreach (char c in text) {
                int privateIndex = privateChars.IndexOf(c);
                if (privateIndex >= 0) result.Add((byte)(14 + privateIndex));
                else result.AddRange(cp.GetBytes(new char[] {c}));
            }
            return result.ToArray();
        }
        public static int Main(string[] args) {
            try {
                Directory.CreateDirectory(Root);
                File.WriteAllLines(Path.Combine(Root, "programmer.args"), args);
                if (Mode == "dfu-failure") return 7;
                int download = Array.IndexOf(args, "--download");
                if (download < 0 || download + 2 >= args.Length ||
                    args[download+2] != "0x8000000" || Array.IndexOf(args, "--start") < 0)
                    throw new Exception("Wrong STM32 programmer arguments");
                FirmwareIdentity(args[download+1]);
                File.Copy(args[download+1], Path.Combine(Root, "firmware.bin"), true);
                return 0;
            } catch (Exception e) { Console.Error.WriteLine(e.Message); return 91; }
        }
    }

    public sealed class Serial : IDisposable {
        private Queue<string> lines = new Queue<string>();
        private MemoryStream pending;
        private string pendingPath;
        private int expectedSize;
        private uint expectedCrc;
        private int opens;
        private bool disconnected;
        public string PortName { get; set; }
        public int BaudRate { get; set; }
        public int DataBits { get; set; }
        public object Parity { get; set; }
        public object StopBits { get; set; }
        public object Handshake { get; set; }
        public bool DtrEnable { get; set; }
        public bool RtsEnable { get; set; }
        public string NewLine { get; set; }
        public Encoding Encoding { get; set; }
        public int ReadTimeout { get; set; }
        public int WriteTimeout { get; set; }
        public bool IsOpen { get; private set; }
        public Serial(string port) { PortName = port; ReadTimeout = 8000; WriteTimeout = 2000; }
        public void Open() {
            opens = Device.Count("opens");
            if (Device.Mode == "busy-once" && opens == 1) throw new UnauthorizedAccessException("busy");
            if (Device.Mode == "busy") throw new UnauthorizedAccessException("busy");
            if (!File.Exists(Path.Combine(Device.Root, "firmware.bin"))) throw new IOException("No firmware after DFU");
            IsOpen = true;
        }
        public void Close() { IsOpen = false; }
        public void Dispose() { Close(); }
        public void DiscardInBuffer() { lines.Clear(); }
        public string ReadLine() {
            if (!IsOpen || disconnected) throw new IOException("CDC disconnected");
            if (lines.Count != 0) return lines.Dequeue();
            Thread.Sleep(Math.Min(ReadTimeout, 10));
            throw new TimeoutException();
        }
        private string Target(string remote) {
            string root = Path.GetFullPath(Path.Combine(Device.Root, "fs")) + Path.DirectorySeparatorChar;
            string path = Path.GetFullPath(Path.Combine(root, remote.TrimStart('/').Replace('/', Path.DirectorySeparatorChar)));
            if (!path.StartsWith(root, StringComparison.Ordinal)) throw new Exception("Path escaped C6");
            return path;
        }
        private void List(string path) {
            string target = path == "/" ? Path.Combine(Device.Root, "fs") : Target(path);
            int count = 0;
            if (Directory.Exists(target)) {
                foreach (string d in Directory.GetDirectories(target)) { lines.Enqueue("d\t" + Path.GetFileName(d) + "/"); count++; }
                foreach (string f in Directory.GetFiles(target)) { lines.Enqueue("f\t" + new FileInfo(f).Length + " B\t" + Path.GetFileName(f)); count++; }
            }
            lines.Enqueue(count + (count == 1 ? " entry." : " entries."));
        }
        public void Write(string text) {
            if (!IsOpen || disconnected) throw new IOException("CDC disconnected");
            foreach (string command in text.Split(new char[] {'\r'}, StringSplitOptions.RemoveEmptyEntries)) {
                File.AppendAllText(Path.Combine(Device.Root, "commands.log"), command + "\n");
                lines.Enqueue("/> " + command);
                Match m;
                if (command == "identity") {
                    int n = Device.Count("identities");
                    if (Device.Mode == "legacy-first" && n == 1) { lines.Enqueue("MK61s mini ver. boot"); continue; }
                    string[] id = Device.FirmwareIdentity(Path.Combine(Device.Root, "firmware.bin"));
                    if (Device.Mode == "wrong-profile") id[0] = id[0] == "mini-v2-a00" ? "mini-v2-a02" : "mini-v2-a00";
                    if (Device.Mode == "wrong-build") id[1] = (UInt32.Parse(id[1], NumberStyles.HexNumber) ^ 1).ToString("X8");
                    bool other = PortName == "COM72" || (Device.Mode == "identity-switch" && opens >= 3);
                    lines.Enqueue("MK61 ID v=1 public=" + (other ? "FEDCBA9876543210 short=76543210 usb=665544332211" :
                        "0123456789ABCDEF short=89ABCDEF usb=112233445566") +
                        " volume=ABCDEF01 build=" + id[1] + " profile=" + id[0]);
                } else if (command == "ver") {
                    lines.Enqueue("MK61s mini ver. e2e");
                } else if ((m = Regex.Match(command, "^ls \"([^\"]+)\"$")).Success) {
                    List(m.Groups[1].Value);
                } else if ((m = Regex.Match(command, "^mkdir (?:-p )?\"([^\"]+)\"$")).Success) {
                    Directory.CreateDirectory(Target(m.Groups[1].Value));
                } else if ((m = Regex.Match(command, "^rm -r \"([^\"]+)\"$")).Success) {
                    string p = Target(m.Groups[1].Value);
                    if (File.Exists(p)) File.Delete(p); else if (Directory.Exists(p)) Directory.Delete(p, true);
                } else if ((m = Regex.Match(command, "^fsput begin \"([^\"]+)\" ([0-9]+) ([0-9]+)$")).Success) {
                    pendingPath = Target(m.Groups[1].Value);
                    expectedSize = Int32.Parse(m.Groups[2].Value);
                    expectedCrc = UInt32.Parse(m.Groups[3].Value);
                    pending = new MemoryStream();
                    lines.Enqueue("@MKC:READY " + expectedSize);
                } else if ((m = Regex.Match(command, "^fsput data ([0-9]+) ([0-9A-F]+)$")).Success) {
                    if (pending == null || Int32.Parse(m.Groups[1].Value) != pending.Length) throw new Exception("Wrong fsput offset");
                    string hex = m.Groups[2].Value;
                    if (hex.Length % 2 != 0 || hex.Length > 192) throw new Exception("Wrong terminal chunk size");
                    for (int i = 0; i < hex.Length; i += 2) pending.WriteByte(Byte.Parse(hex.Substring(i,2), NumberStyles.HexNumber));
                    if (Device.Mode == "disconnect") { disconnected = true; throw new IOException("CDC disconnected"); }
                    lines.Enqueue("@MKC:ACK " + (pending.Length + (Device.Mode == "wrong-ack" ? 1 : 0)));
                } else if (command == "fsput end") {
                    byte[] bytes = pending.ToArray();
                    if (bytes.Length != expectedSize || Device.Checksum(bytes) != expectedCrc) throw new Exception("Bad fsput checksum");
                    Directory.CreateDirectory(Path.GetDirectoryName(pendingPath));
                    File.WriteAllBytes(pendingPath, bytes);
                    pending.Dispose(); pending = null;
                    lines.Enqueue("@MKC:DONE " + bytes.Length + " " + expectedCrc);
                } else if (command == "fsput cancel") {
                    if (pending != null) { pending.Dispose(); pending = null; }
                    lines.Enqueue("@MKC:CANCELLED");
                } else if ((m = Regex.Match(command, "^fsget \"([^\"]+)\"$")).Success) {
                    byte[] bytes = File.ReadAllBytes(Target(m.Groups[1].Value));
                    uint crc = Device.Checksum(bytes);
                    lines.Enqueue("@MKC:GET " + bytes.Length + " " + crc);
                    if (Device.Mode == "corrupt-readback" && bytes.Length != 0) bytes[0] ^= 1;
                    for (int offset = 0; offset < bytes.Length; offset += 96) {
                        int count = Math.Min(96, bytes.Length-offset);
                        lines.Enqueue("@MKC:DATA " + offset + " " + BitConverter.ToString(bytes,offset,count).Replace("-",""));
                    }
                    lines.Enqueue("@MKC:END " + bytes.Length + " " + crc);
                } else { throw new Exception("Unimplemented C6 command: " + command); }
                lines.Enqueue("/> ");
            }
        }
    }
}
