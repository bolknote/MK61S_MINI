# ByteKiller format based on Raw, Copyright (C) 2004 Gregory Montoir,
# GPL-2.0-or-later. Runs on PowerShell 5.1 without Python or a compiler.
$script:AwReverse = @(0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15)
function Read-AwBe16([byte[]]$b,[int]$i) { return ([int]$b[$i] -shl 8) -bor [int]$b[$i+1] }
function Read-AwBe32([byte[]]$b,[int]$i) {
  if ($i -lt 0 -or $i -gt $b.Length-4) { throw 'Truncated ByteKiller input' }
  return ([uint32]$b[$i] -shl 24) -bor ([uint32]$b[$i+1] -shl 16) -bor ([uint32]$b[$i+2] -shl 8) -bor [uint32]$b[$i+3]
}
function Get-AwFnv([byte[]]$b) {
  [uint32]$h=2166136261
  foreach ($v in $b) { $h=[uint32]((([uint64]($h -bxor [uint32]$v))*16777619) -band [uint64]4294967295) }
  return $h
}
function Set-AwLe32([byte[]]$b,[int]$i,[uint32]$v) {
  $b[$i]=[byte]($v -band 255);$b[$i+1]=[byte](($v -shr 8) -band 255);$b[$i+2]=[byte](($v -shr 16) -band 255);$b[$i+3]=[byte]($v -shr 24)
}
function Read-AwField($s,[int]$count) {
  if ($count -ge 8 -and $count -le 12 -and ($s.Bits -shr $count) -ne 0) {
    [uint32]$bits=$s.Bits
    [uint32]$value=($script:AwReverse[[int]($bits -band 15)] -shl 4) -bor $script:AwReverse[[int](($bits -shr 4) -band 15)]
    if ($count -gt 8) {
      [uint32]$high=$bits -shr 8
      [uint32]$rev=($script:AwReverse[[int]($high -band 15)] -shl 4) -bor $script:AwReverse[[int](($high -shr 4) -band 15)]
      $value=($value -shl ($count-8)) -bor ($rev -shr (16-$count))
    }
    $s.Bits=[uint32]($bits -shr $count);return $value
  }
  [uint32]$value=0
  for ($k=0;$k -lt $count;$k++) {
    [uint32]$one=$s.Bits -band 1
    $s.Bits=[uint32]($s.Bits -shr 1)
    if ($s.Bits -eq 0) {
      if ($s.Cursor -lt 4) { throw 'Truncated ByteKiller bitstream' }
      $s.Cursor-=4;$s.Bits=Read-AwBe32 $s.Source $s.Cursor;$s.Crc=[uint32]($s.Crc -bxor $s.Bits)
      $one=$s.Bits -band 1;$s.Bits=[uint32](($s.Bits -shr 1) -bor [uint32]2147483648)
    }
    $value=($value -shl 1) -bor $one
  }
  return $value
}
function Expand-AwResource([byte[]]$source,[int]$size) {
  if ($source.Length -eq $size) { return ,$source }
  if ($source.Length -lt 12 -or ($source.Length % 4) -ne 0 -or (Read-AwBe32 $source ($source.Length-4)) -ne $size) { throw 'Invalid ByteKiller size' }
  $s=[pscustomobject]@{Source=$source;Cursor=$source.Length-12;Bits=[uint32]0;Crc=[uint32]0}
  $s.Bits=Read-AwBe32 $source $s.Cursor;$s.Crc=[uint32]((Read-AwBe32 $source ($source.Length-8)) -bxor $s.Bits)
  [byte[]]$out=New-Object byte[] $size
  $remain=$size
  while ($remain -gt 0) {
    $literal=$false;$distance=0
    if ((Read-AwField $s 1) -eq 0) {
      if ((Read-AwField $s 1) -eq 0) { $literal=$true;$count=(Read-AwField $s 3)+1 }
      else { $count=2;$distance=Read-AwField $s 8 }
    } else {
      $code=Read-AwField $s 2
      if ($code -eq 3) { $literal=$true;$count=(Read-AwField $s 8)+9 }
      elseif ($code -lt 2) { $count=$code+3;$distance=Read-AwField $s ($code+9) }
      else { $count=(Read-AwField $s 8)+1;$distance=Read-AwField $s 12 }
    }
    if ($count -gt $remain) { throw 'Invalid ByteKiller count' }
    if ($literal) {
      for ($j=0;$j -lt $count;$j++) { $remain--;$out[$remain]=[byte](Read-AwField $s 8) }
    } else {
      if ($distance -le 0 -or $distance -gt $size-$remain) { throw 'Invalid ByteKiller reference' }
      for ($j=0;$j -lt $count;$j++) { $remain--;$out[$remain]=$out[$remain+$distance] }
    }
  }
  if ($s.Crc -ne 0) { throw 'ByteKiller checksum mismatch' }
  return ,$out
}
function New-AnotherSoundCache([string]$dir) {
  [byte[]]$list=[IO.File]::ReadAllBytes((Join-Path $dir 'MEMLIST.BIN'))
  if ($list.Length -eq 0 -or $list.Length -gt 4096) { throw 'Invalid MEMLIST size' }
  $entries=New-Object 'Collections.Generic.List[int]';$done=$false
  for ($p=0;$p -lt $list.Length;$p+=20) {
    if ($list[$p] -eq 255) { $done=$true;break }
    if ($list.Length-$p -lt 20 -or $entries.Count -ge 150) { throw 'Invalid MEMLIST entries' }
    $entries.Add($p)
  }
  if (!$done -or !$entries.Count) { throw 'Missing MEMLIST terminator' }
  [byte[]]$records=New-Object byte[] ($entries.Count*12)
  $banks=@{};$payload=New-Object IO.MemoryStream;$sounds=0
  try {
    for ($id=0;$id -lt $entries.Count;$id++) {
      $p=$entries[$id];$kind=$list[$p+1];$bank=[int]$list[$p+7]
      [uint32]$offset=Read-AwBe32 $list ($p+8);$packed=Read-AwBe16 $list ($p+14);$size=Read-AwBe16 $list ($p+18)
      if ($packed -gt $size -or ([uint64]$offset+$packed) -gt [uint64]4294967295) { throw "Invalid resource $id" }
      if ($kind -ne 0 -or $bank -eq 0 -or $packed -eq 0 -or $size -eq 0) { continue }
      if (!$banks.ContainsKey($bank)) { $banks[$bank]=[IO.File]::ReadAllBytes((Join-Path $dir ('BANK{0:X2}' -f $bank))) }
      [byte[]]$source=New-Object byte[] $packed
      if (([uint64]$offset+$packed) -gt $banks[$bank].Length) { throw "Truncated BANK resource $id" }
      [Array]::Copy($banks[$bank],[int]$offset,$source,0,$packed)
      [byte[]]$raw=Expand-AwResource $source $size
      Set-AwLe32 $records ($id*12) ([uint32](24+$records.Length+$payload.Length))
      Set-AwLe32 $records ($id*12+4) (Get-AwFnv $source)
      Set-AwLe32 $records ($id*12+8) (Get-AwFnv $raw)
      $payload.Write($raw,0,$raw.Length);$sounds++
      if (($sounds % 16) -eq 0) { Write-Host "Prepared $sounds sounds..." }
    }
    [byte[]]$header=New-Object byte[] 24
    [Text.Encoding]::ASCII.GetBytes('AWC1').CopyTo($header,0)
    Set-AwLe32 $header 4 1;Set-AwLe32 $header 8 $entries.Count;Set-AwLe32 $header 12 $list.Length
    Set-AwLe32 $header 16 (Get-AwFnv $list);Set-AwLe32 $header 20 $records.Length
    $target=Join-Path $dir 'AWCACHE.BIN'
    $temporary=Join-Path $dir ('.awcache-' + [Guid]::NewGuid().ToString('N'))
    try {
      $f=New-Object IO.FileStream($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
      try { $f.Write($header,0,24);$f.Write($records,0,$records.Length);$payload.Position=0;$payload.CopyTo($f) } finally {$f.Dispose()}
      if ([IO.File]::Exists($target)) { [IO.File]::Replace($temporary,$target,[NullString]::Value) }
      else { [IO.File]::Move($temporary,$target) }
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
    return "Prepared AWCACHE.BIN: $sounds sounds, $($payload.Length) decoded bytes"
  } finally {$payload.Dispose()}
}
