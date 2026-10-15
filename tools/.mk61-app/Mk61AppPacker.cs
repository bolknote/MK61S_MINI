/*
 * (c) Copyright 2021 by Einar Saukas. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *     * Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright
 *       notice, this list of conditions and the following disclaimer in the
 *       documentation and/or other materials provided with the distribution.
 *     * The name of its author may not be used to endorse or promote products
 *       derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
 * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 * LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
 * ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

// Dependency-free .NET helper loaded by PowerShell's built-in Add-Type.
// Keep syntax compatible with Windows PowerShell 5.1 / .NET Framework.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace Mk61.Build {
  public sealed class PackResult {
    public int AppBytes;
    public int ImageBytes;
    public int MemoryBytes;
    public int RelocationCount;
    public int RelocationBytes;
    public int PlainBytes;
    public int BcjBytes;
    public bool UsesBcj;
  }

  internal sealed class BitWriter {
    internal readonly List<byte> Output = new List<byte>();
    private int bitIndex;
    private int bitMask;
    private bool backtrack = true;

    internal void Bit(bool value) {
      if(backtrack) {
        if(value) {
          if(Output.Count == 0) throw new InvalidDataException("invalid ZX0 backtrack");
          Output[Output.Count - 1] |= 1;
        }
        backtrack = false;
        return;
      }
      if(bitMask == 0) {
        bitMask = 0x80;
        bitIndex = Output.Count;
        Output.Add(0);
      }
      if(value) Output[bitIndex] |= (byte)bitMask;
      bitMask >>= 1;
    }

    internal void Byte(int value) { Output.Add((byte)(value & 255)); }

    internal void Gamma(int value, bool inverted) {
      if(value <= 0) throw new InvalidDataException("invalid ZX0 gamma value");
      int bit = 1;
      while(bit <= value / 2) bit <<= 1;
      for(;;) {
        bit >>= 1;
        if(bit == 0) break;
        Bit(false);
        bool data = (value & bit) != 0;
        Bit(inverted ? !data : data);
      }
      Bit(true);
    }

    internal void BeginBacktrack() { backtrack = true; }
  }

  internal sealed class BitReader {
    private readonly byte[] data;
    internal int Position;
    private int bitValue;
    private int bitMask;

    internal BitReader(byte[] source) { data = source; }

    internal int Byte() {
      if(Position >= data.Length) throw new InvalidDataException("truncated ZX0 stream");
      return data[Position++];
    }

    internal int Bit() {
      bitMask >>= 1;
      if(bitMask == 0) {
        bitMask = 0x80;
        bitValue = Byte();
      }
      return (bitValue & bitMask) != 0 ? 1 : 0;
    }

    internal int Gamma(bool inverted, int first) {
      int result = 1;
      int current = first < 0 ? Bit() : first;
      while(current == 0) {
        int value = Bit();
        if(inverted) value ^= 1;
        result = checked((result << 1) | value);
        current = Bit();
      }
      return result;
    }
  }

  internal sealed class Token {
    internal int Length;
    internal int Offset;
    internal Token(int length, int offset) { Length = length; Offset = offset; }
  }

  internal sealed class Section {
    internal uint Name;
    internal uint Type;
    internal uint Flags;
    internal uint Address;
    internal uint Offset;
    internal uint Size;
    internal uint Link;
    internal uint Info;
    internal uint Alignment;
    internal uint EntrySize;
  }

  public static class AppPacker {
    private const int HeaderSize = 64;
    private const int MaxMemorySize = 20 * 1024;
    private const uint LoadAddress = 0x20000000;
    private const int MaxOffset = 32640;
    private const uint PortableFlag = 1;
    private const uint BcjFlag = 2;
    private const uint RelocatableFlag = 4;

    private static readonly Dictionary<string, byte> Kinds =
      new Dictionary<string, byte>(StringComparer.Ordinal) {
        {"focal", 1}, {"tinybasic", 2}, {"wbmp-viewer", 3}, {"app", 4},
        {"chip8", 5}, {"markdown-viewer", 6}, {"setup", 7},
        {"usbdisk", 8}, {"explorer", 9}, {"language-vm", 10}, {"language-input", 11}
      };

    private static ushort U16(byte[] data, int offset) {
      if(offset < 0 || offset + 2 > data.Length) throw new InvalidDataException("truncated 16-bit field");
      return (ushort)(data[offset] | (data[offset + 1] << 8));
    }

    private static uint U32(byte[] data, int offset) {
      if(offset < 0 || offset + 4 > data.Length) throw new InvalidDataException("truncated 32-bit field");
      return (uint)(data[offset] | (data[offset + 1] << 8) |
                    (data[offset + 2] << 16) | (data[offset + 3] << 24));
    }

    private static void Put16(byte[] data, int offset, int value) {
      data[offset] = (byte)value;
      data[offset + 1] = (byte)(value >> 8);
    }

    private static void Put32(byte[] data, int offset, uint value) {
      data[offset] = (byte)value;
      data[offset + 1] = (byte)(value >> 8);
      data[offset + 2] = (byte)(value >> 16);
      data[offset + 3] = (byte)(value >> 24);
    }

    private static uint Crc32(byte[] data) {
      uint state = 0xffffffffU;
      for(int index = 0; index < data.Length; ++index) {
        state ^= data[index];
        for(int bit = 0; bit < 8; ++bit)
          state = (state & 1) != 0 ? (state >> 1) ^ 0xedb88320U : state >> 1;
      }
      return state ^ 0xffffffffU;
    }

    // The same ZX0 v2 optimal parse as third_party/zx0/optimize.c. The pool is
    // local to one parse, so concurrent bundle builds never share block state.
    private sealed class ParseBlock {
      internal ParseBlock Chain, FreeNext;
      internal int Bits, Index, Offset, References;
    }

    private sealed class ParsePool {
      private ParseBlock free;
      internal ParseBlock Allocate(int bits, int index, int offset, ParseBlock chain) {
        ParseBlock block;
        if(free != null) {
          block = free;
          free = block.FreeNext;
          if(block.Chain != null && --block.Chain.References == 0) {
            block.Chain.FreeNext = free;
            free = block.Chain;
          }
        } else block = new ParseBlock();
        block.Bits = bits;
        block.Index = index;
        block.Offset = offset;
        if(chain != null) ++chain.References;
        block.Chain = chain;
        block.References = 0;
        block.FreeNext = null;
        return block;
      }
      internal void Assign(ref ParseBlock target, ParseBlock block) {
        ++block.References;
        if(target != null && --target.References == 0) {
          target.FreeNext = free;
          free = target;
        }
        target = block;
      }
    }

    private static int GammaBits(int value) {
      int bits = 1;
      while((value >>= 1) != 0) bits += 2;
      return bits;
    }

    private static List<Token> OptimalTokens(byte[] data) {
      if(data.Length == 0) throw new InvalidDataException("ZX0 input is empty");
      int maxOffset = Math.Max(1, Math.Min(data.Length - 1, MaxOffset));
      ParseBlock[] lastLiteral = new ParseBlock[maxOffset + 1];
      ParseBlock[] lastMatch = new ParseBlock[maxOffset + 1];
      ParseBlock[] optimal = new ParseBlock[data.Length];
      int[] matchLength = new int[maxOffset + 1];
      int[] bestLength = new int[Math.Max(3, data.Length)];
      bestLength[2] = 2;
      ParsePool pool = new ParsePool();
      pool.Assign(ref lastMatch[1], pool.Allocate(-1, -1, 1, null));
      for(int index = 0; index < data.Length; ++index) {
        int bestLengthSize = 2;
        int ceiling = Math.Max(1, Math.Min(index, MaxOffset));
        for(int offset = 1; offset <= ceiling; ++offset) {
          int length, bits;
          if(index != 0 && index >= offset && data[index] == data[index - offset]) {
            if(lastLiteral[offset] != null) {
              length = index - lastLiteral[offset].Index;
              bits = lastLiteral[offset].Bits + 1 + GammaBits(length);
              pool.Assign(ref lastMatch[offset],
                pool.Allocate(bits, index, offset, lastLiteral[offset]));
              if(optimal[index] == null || optimal[index].Bits > bits)
                pool.Assign(ref optimal[index], lastMatch[offset]);
            }
            if(++matchLength[offset] > 1) {
              if(bestLengthSize < matchLength[offset]) {
                bits = optimal[index - bestLength[bestLengthSize]].Bits +
                  GammaBits(bestLength[bestLengthSize] - 1);
                do {
                  ++bestLengthSize;
                  int bits2 = optimal[index - bestLengthSize].Bits + GammaBits(bestLengthSize - 1);
                  if(bits2 <= bits) { bestLength[bestLengthSize] = bestLengthSize; bits = bits2; }
                  else bestLength[bestLengthSize] = bestLength[bestLengthSize - 1];
                } while(bestLengthSize < matchLength[offset]);
              }
              length = bestLength[matchLength[offset]];
              bits = optimal[index - length].Bits + 8 +
                GammaBits((offset - 1) / 128 + 1) + GammaBits(length - 1);
              if(lastMatch[offset] == null || lastMatch[offset].Index != index || lastMatch[offset].Bits > bits) {
                pool.Assign(ref lastMatch[offset],
                  pool.Allocate(bits, index, offset, optimal[index - length]));
                if(optimal[index] == null || optimal[index].Bits > bits)
                  pool.Assign(ref optimal[index], lastMatch[offset]);
              }
            }
          } else {
            matchLength[offset] = 0;
            if(lastMatch[offset] != null) {
              length = index - lastMatch[offset].Index;
              bits = lastMatch[offset].Bits + 1 + GammaBits(length) + length * 8;
              pool.Assign(ref lastLiteral[offset],
                pool.Allocate(bits, index, 0, lastMatch[offset]));
              if(optimal[index] == null || optimal[index].Bits > bits)
                pool.Assign(ref optimal[index], lastLiteral[offset]);
            }
          }
        }
      }
      List<Token> tokens = new List<Token>();
      for(ParseBlock block = optimal[data.Length - 1]; block.Chain != null; block = block.Chain)
        tokens.Add(new Token(block.Index - block.Chain.Index, block.Offset));
      tokens.Reverse();
      return tokens;
    }

    private static byte[] Zx0Encode(byte[] data) {
      BitWriter writer = new BitWriter();
      int position = 0;
      int lastOffset = 1;
      foreach(Token token in OptimalTokens(data)) {
        if(token.Length <= 0 || position + token.Length > data.Length)
          throw new InvalidDataException("invalid ZX0 token");
        if(token.Offset == 0) {
          writer.Bit(false);
          writer.Gamma(token.Length, false);
          for(int index = 0; index < token.Length; ++index) writer.Byte(data[position + index]);
        } else if(token.Offset == lastOffset) {
          writer.Bit(false);
          writer.Gamma(token.Length, false);
        } else {
          writer.Bit(true);
          writer.Gamma((token.Offset - 1) / 128 + 1, true);
          writer.Byte((127 - ((token.Offset - 1) % 128)) << 1);
          writer.BeginBacktrack();
          writer.Gamma(token.Length - 1, false);
          lastOffset = token.Offset;
        }
        position += token.Length;
      }
      if(position != data.Length) throw new InvalidDataException("incomplete ZX0 token plan");
      writer.Bit(true);
      writer.Gamma(256, true);
      return writer.Output.ToArray();
    }

    private static byte[] Zx0Decode(byte[] data, int expectedSize) {
      BitReader reader = new BitReader(data);
      List<byte> output = new List<byte>(expectedSize);
      int lastOffset = 1;
      bool literal = true;
      for(;;) {
        if(literal) {
          int length = reader.Gamma(false, -1);
          for(int index = 0; index < length; ++index) output.Add((byte)reader.Byte());
          if(reader.Bit() != 0) {
            literal = false;
          } else {
            length = reader.Gamma(false, -1);
            if(lastOffset > output.Count) throw new InvalidDataException("invalid ZX0 last offset");
            for(int index = 0; index < length; ++index) output.Add(output[output.Count - lastOffset]);
            literal = reader.Bit() == 0;
          }
        } else {
          int high = reader.Gamma(true, -1);
          if(high == 256) {
            if(output.Count != expectedSize || reader.Position != data.Length)
              throw new InvalidDataException("invalid ZX0 end marker");
            return output.ToArray();
          }
          if(high > 255) throw new InvalidDataException("invalid ZX0 offset");
          int low = reader.Byte();
          lastOffset = high * 128 - (low >> 1);
          int length = reader.Gamma(false, low & 1) + 1;
          if(lastOffset <= 0 || lastOffset > output.Count)
            throw new InvalidDataException("invalid ZX0 offset");
          for(int index = 0; index < length; ++index) output.Add(output[output.Count - lastOffset]);
          literal = reader.Bit() == 0;
        }
        if(output.Count > expectedSize) throw new InvalidDataException("ZX0 output exceeds image");
      }
    }

    private static byte[] BcjTransform(byte[] data, bool encode) {
      byte[] output = (byte[])data.Clone();
      int index = 0;
      while(index + 3 < output.Length) {
        if((output[index + 1] & 0xf8) == 0xf0 && (output[index + 3] & 0xf8) == 0xf8) {
          uint address = (uint)((((output[index + 1] & 7) << 19) |
                                 (output[index] << 11) |
                                 ((output[index + 3] & 7) << 8) |
                                 output[index + 2]) << 1);
          address = encode ? unchecked(address + (uint)index + 4U) :
                             unchecked(address - (uint)index - 4U);
          address >>= 1;
          output[index + 1] = (byte)(0xf0 | ((address >> 19) & 7));
          output[index] = (byte)(address >> 11);
          output[index + 3] = (byte)(0xf8 | ((address >> 8) & 7));
          output[index + 2] = (byte)address;
          index += 4;
        } else index += 2;
      }
      return output;
    }

    private static int ValidateRelocations(byte[] table, byte[] image, int memorySize) {
      int position = 0;
      int end = 0;
      int count = 0;
      while(position < table.Length) {
        int gap = 0;
        int shift = 0;
        for(;;) {
          if(position >= table.Length || shift > 14)
            throw new InvalidDataException("malformed relocation table");
          int value = table[position++];
          if(shift != 0 && value == 0)
            throw new InvalidDataException("non-canonical relocation table");
          gap |= (value & 0x7f) << shift;
          if((value & 0x80) == 0) break;
          shift += 7;
        }
        int offset = end + gap;
        if(offset < 0 || offset + 4 > image.Length)
          throw new InvalidDataException("relocation is outside the image");
        uint pointer = U32(image, offset);
        if(pointer < LoadAddress || pointer > LoadAddress + memorySize)
          throw new InvalidDataException("relocation does not refer to the APP image");
        end = offset + 4;
        ++count;
      }
      return count;
    }

    private static ushort TypeMagic(string value) {
      if(String.IsNullOrEmpty(value)) return 0;
      if(value.Length != 2) throw new InvalidDataException("handled magic must contain two ASCII letters or digits");
      for(int index = 0; index < 2; ++index) {
        char c = value[index];
        if(c > 127 || !(Char.IsLetterOrDigit(c)))
          throw new InvalidDataException("handled magic must contain two ASCII letters or digits");
      }
      return (ushort)(value[0] | (value[1] << 8));
    }

    private static bool Equal(byte[] left, byte[] right) {
      if(left.Length != right.Length) return false;
      for(int index = 0; index < left.Length; ++index)
        if(left[index] != right[index]) return false;
      return true;
    }

    public static PackResult PackFile(string kind, string imagePath,
                                      string relocationPath, int memorySize,
                                      int entryOffset, uint loadAddress,
                                      string handledMagic, string outputPath) {
      byte kindValue;
      if(!Kinds.TryGetValue(kind, out kindValue)) throw new InvalidDataException("unknown APP kind");
      byte[] image = File.ReadAllBytes(imagePath);
      byte[] table = File.ReadAllBytes(relocationPath);
      if(image.Length == 0 || image.Length > memorySize || memorySize > MaxMemorySize)
        throw new InvalidDataException("module exceeds the 20 KiB APP image limit");
      if(entryOffset < 0 || entryOffset >= image.Length || (entryOffset & 1) != 0)
        throw new InvalidDataException("entry offset must be aligned and inside the image");
      if(loadAddress != LoadAddress) throw new InvalidDataException("current APP ABI has a fixed virtual link base");
      int relocationCount = ValidateRelocations(table, image, memorySize);

      byte[] plain = Zx0Encode(image);
      if(!Equal(Zx0Decode(plain, image.Length), image))
        throw new InvalidDataException("internal plain ZX0 verification failed");
      byte[] filtered = BcjTransform(image, true);
      if(!Equal(BcjTransform(filtered, false), image))
        throw new InvalidDataException("BCJ round-trip failed");
      byte[] bcj = Zx0Encode(filtered);
      if(!Equal(Zx0Decode(bcj, filtered.Length), filtered))
        throw new InvalidDataException("internal BCJ ZX0 verification failed");
      bool useBcj = bcj.Length < plain.Length;
      byte[] code = useBcj ? bcj : plain;
      int storedSize = checked(code.Length + table.Length);
      if(HeaderSize + storedSize > HeaderSize + MaxMemorySize)
        throw new InvalidDataException("module exceeds the 20 KiB APP container limit");

      byte[] stored = new byte[storedSize];
      Array.Copy(code, 0, stored, 0, code.Length);
      Array.Copy(table, 0, stored, code.Length, table.Length);
      byte[] header = new byte[HeaderSize];
      byte[] magic = Encoding.ASCII.GetBytes("MK61APP\0");
      Array.Copy(magic, header, magic.Length);
      Put16(header, 8, 1);
      Put16(header, 10, HeaderSize);
      Put16(header, 12, 6);
      header[14] = kindValue;
      header[15] = 1;
      Put32(header, 16, PortableFlag | RelocatableFlag | (useBcj ? BcjFlag : 0));
      Put32(header, 20, loadAddress);
      Put32(header, 24, (uint)storedSize);
      Put32(header, 28, (uint)image.Length);
      Put32(header, 32, (uint)memorySize);
      Put32(header, 36, (uint)entryOffset);
      Put32(header, 40, (uint)code.Length);
      Put32(header, 44, (uint)relocationCount);
      Put32(header, 48, Crc32(stored));
      Put32(header, 52, Crc32(image));
      Put16(header, 56, TypeMagic(handledMagic));
      Put16(header, 58, 0);
      byte[] headerPrefix = new byte[60];
      Array.Copy(header, headerPrefix, 60);
      Put32(header, 60, Crc32(headerPrefix));

      byte[] module = new byte[HeaderSize + storedSize];
      Array.Copy(header, module, HeaderSize);
      Array.Copy(stored, 0, module, HeaderSize, storedSize);
      string parent = Path.GetDirectoryName(Path.GetFullPath(outputPath));
      Directory.CreateDirectory(parent);
      File.WriteAllBytes(outputPath, module);
      return new PackResult {
        AppBytes = module.Length,
        ImageBytes = image.Length,
        MemoryBytes = memorySize,
        RelocationCount = relocationCount,
        RelocationBytes = table.Length,
        PlainBytes = plain.Length,
        BcjBytes = bcj.Length,
        UsesBcj = useBcj
      };
    }

    private static Section ReadSection(byte[] data, uint table, ushort size,
                                       ushort count, int index) {
      if(index < 0 || index >= count || size != 40)
        throw new InvalidDataException("invalid ELF section table");
      ulong location = (ulong)table + (ulong)index * size;
      if(location + 40 > (ulong)data.Length)
        throw new InvalidDataException("truncated ELF section table");
      int at = (int)location;
      return new Section {
        Name = U32(data, at), Type = U32(data, at + 4),
        Flags = U32(data, at + 8), Address = U32(data, at + 12),
        Offset = U32(data, at + 16), Size = U32(data, at + 20),
        Link = U32(data, at + 24), Info = U32(data, at + 28),
        Alignment = U32(data, at + 32), EntrySize = U32(data, at + 36)
      };
    }

    private static byte[] Contents(byte[] data, Section section) {
      if(section.Offset > data.Length || section.Size > data.Length - section.Offset)
        throw new InvalidDataException("truncated ELF section");
      byte[] result = new byte[section.Size];
      Array.Copy(data, section.Offset, result, 0, section.Size);
      return result;
    }

    private static string SectionName(byte[] names, uint start) {
      if(start >= names.Length) throw new InvalidDataException("invalid ELF section name");
      int end = (int)start;
      while(end < names.Length && names[end] != 0) ++end;
      if(end == names.Length) throw new InvalidDataException("unterminated ELF section name");
      return Encoding.ASCII.GetString(names, (int)start, end - (int)start);
    }

    private static byte[] EncodeOffsets(List<int> offsets) {
      List<byte> output = new List<byte>();
      int end = 0;
      foreach(int offset in offsets) {
        int gap = offset - end;
        if(gap < 0 || offset > MaxMemorySize - 4)
          throw new InvalidDataException("overlapping or out-of-range APP relocation");
        while(gap >= 128) {
          output.Add((byte)((gap & 127) | 128));
          gap >>= 7;
        }
        output.Add((byte)gap);
        end = offset + 4;
      }
      return output.ToArray();
    }

    public static int ExtractRelocations(string elfPath, uint baseAddress,
                                         int imageSize, int memorySize,
                                         string outputPath) {
      byte[] data = File.ReadAllBytes(elfPath);
      if(data.Length < 52 || data[0] != 0x7f || data[1] != (byte)'E' ||
         data[2] != (byte)'L' || data[3] != (byte)'F' || data[4] != 1 ||
         data[5] != 1 || data[6] != 1 || U16(data, 16) != 2 ||
         U16(data, 18) != 40 || U16(data, 46) != 40)
        throw new InvalidDataException("expected linked little-endian ARM ELF32");
      uint sectionTable = U32(data, 32);
      ushort sectionCount = U16(data, 48);
      ushort stringIndex = U16(data, 50);
      Section[] sections = new Section[sectionCount];
      for(int index = 0; index < sections.Length; ++index)
        sections[index] = ReadSection(data, sectionTable, 40, sectionCount, index);
      if(stringIndex >= sections.Length) throw new InvalidDataException("invalid ELF string section");
      byte[] names = Contents(data, sections[stringIndex]);
      HashSet<int> moduleSections = new HashSet<int>();
      for(int index = 0; index < sections.Length; ++index) {
        string name = SectionName(names, sections[index].Name);
        if(name == ".module_image" || name == ".module_bss") moduleSections.Add(index);
      }
      if(moduleSections.Count == 0) throw new InvalidDataException("missing APP sections");

      List<int> offsets = new List<int>();
      int records = 0;
      for(int index = 0; index < sections.Length; ++index) {
        Section section = sections[index];
        string sectionName = SectionName(names, section.Name);
        if((section.Flags & 2) != 0 && section.Size != 0 && !moduleSections.Contains(index))
          throw new InvalidDataException("unpacked ELF section: " + sectionName);
        if(section.Type != 4 && section.Type != 9) continue;
        if(section.Info >= sections.Length) throw new InvalidDataException("invalid ELF relocation target");
        int target = (int)section.Info;
        if((sections[target].Flags & 2) == 0) continue;
        if(section.Type != 9 || section.EntrySize != 8 || !moduleSections.Contains(target))
          throw new InvalidDataException("unsupported ELF relocation section");
        if(section.Link >= sections.Length) throw new InvalidDataException("invalid ELF symbol table index");
        Section symbols = sections[section.Link];
        if(symbols.Type != 2 || symbols.EntrySize != 16)
          throw new InvalidDataException("invalid ELF symbol table");
        byte[] table = Contents(data, section);
        byte[] symbolData = Contents(data, symbols);
        if((table.Length & 7) != 0) throw new InvalidDataException("truncated ELF relocation table");
        for(int at = 0; at < table.Length; at += 8) {
          uint address = U32(table, at);
          uint info = U32(table, at + 4);
          int kind = (int)(info & 255);
          uint symbolIndex = info >> 8;
          ulong symbolOffset = (ulong)symbolIndex * 16;
          if(symbolOffset + 16 > (ulong)symbolData.Length)
            throw new InvalidDataException("invalid ELF relocation symbol");
          ushort targetSection = U16(symbolData, (int)symbolOffset + 14);
          ++records;
          if(kind == 0 || kind == 40) continue;
          if(kind == 3 || kind == 10 || kind == 30 || kind == 42 || kind == 51) {
            if(!moduleSections.Contains(targetSection))
              throw new InvalidDataException(String.Format(
                "PC-relative relocation {0} leaves APP at 0x{1:x}", kind, address));
            continue;
          }
          if(kind != 2)
            throw new InvalidDataException(String.Format(
              "unsupported ARM relocation {0} at 0x{1:x}; use -mword-relocations", kind, address));
          if(targetSection == 0xfff1) continue;
          if(!moduleSections.Contains(targetSection))
            throw new InvalidDataException(String.Format(
              "absolute relocation leaves APP at 0x{0:x}", address));
          long destination = (long)address - baseAddress;
          if(destination < 0 || destination + 4 > imageSize)
            throw new InvalidDataException("relocation destination outside image");
          Section source = sections[target];
          long pointerOffset = (long)source.Offset + address - source.Address;
          if(pointerOffset < 0 || pointerOffset + 4 > data.Length)
            throw new InvalidDataException("relocation source outside ELF section");
          uint pointer = U32(data, (int)pointerOffset);
          if(pointer < baseAddress || pointer > baseAddress + memorySize)
            throw new InvalidDataException("relocation target outside APP memory (including one-past-end)");
          offsets.Add((int)destination);
        }
      }
      if(records == 0)
        throw new InvalidDataException("ELF contains no relocation records; link with --emit-relocs");
      offsets.Sort();
      byte[] encoded = EncodeOffsets(offsets);
      File.WriteAllBytes(outputPath, encoded);
      return offsets.Count;
    }
  }
}
