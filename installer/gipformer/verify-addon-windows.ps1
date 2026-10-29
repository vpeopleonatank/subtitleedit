#requires -Version 5.1
<#
.SYNOPSIS
  Verifies a built Gipformer Vietnamese add-on ZIP against its build receipt and manifest, then
  exercises the frozen runtime's protocol.

.DESCRIPTION
  Extracts the archive into a scratch folder and checks, without any Python or CaptionHelper
  dependency (so the same script works on a clean Windows x64 machine):

    1. ZIP SHA-256 matches the recorded build receipt.
    2. addon.json bytes match the receipt, and its identity/format/platform fields are the ones
       this add-on is allowed to declare.
    3. Every manifest path is relative, slash-separated and free of '.', '..' or drive/rooted
       segments; the payload has no unlisted file and every listed file matches size and SHA-256.
    4. Every native Windows binary in runtime/ (exe, dll, pyd) is AMD64.
    5. The runtime answers --help; wrong language, missing manifest, missing pack file and a
       truncated pack each fail with a structured JSON error and a nonzero exit - never with a
       Python ImportError.

  These are build/transfer-drift checks. They do not authenticate the archive: a party that
  replaces both the ZIP and the receipt defeats them.

.PARAMETER Zip
  The add-on archive (root is Gipformer/).
.PARAMETER Receipt
  Build receipt beside the archive; defaults to <Zip>.receipt.txt.
.PARAMETER ExtractDir
  Scratch folder to extract into; defaults to a new folder under the system temp directory.
.PARAMETER SmokeWav
  Optional 16 kHz (or any) audio file for a real-pack transcription smoke: the run must exit 0,
  emit exactly one final result after progress, and return finite, ordered, nonnegative times.
.PARAMETER RequireAccents
  With -SmokeWav: also require at least one Vietnamese accented letter in the transcript.
.PARAMETER KeepExtract
  Do not delete the scratch extraction folder at the end (useful when inspecting a failure).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Zip,
  [string]$Receipt,
  [string]$ExtractDir,
  [string]$SmokeWav,
  [switch]$RequireAccents,
  [switch]$KeepExtract
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

$failures = New-Object System.Collections.Generic.List[string]
$checks = 0

function Check {
  param([bool]$Condition, [string]$Message)
  $script:checks++
  if ($Condition) {
    Write-Host "  ok   $Message"
  } else {
    Write-Host "  FAIL $Message" -ForegroundColor Red
    $script:failures.Add($Message)
  }
}

function Get-Sha256([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  try {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash($stream) } finally { $sha.Dispose() }
  } finally {
    $stream.Dispose()
  }
  return -join ($hash | ForEach-Object { $_.ToString('x2') })
}

function Get-PeMachine([string]$Path) {
  $bytes = [IO.File]::ReadAllBytes($Path)
  if ($bytes.Length -lt 64) { return 0 }
  $peOffset = [BitConverter]::ToInt32($bytes, 0x3C)
  if ($peOffset -le 0 -or $peOffset + 6 -ge $bytes.Length) { return 0 }
  if ($bytes[$peOffset] -ne 0x50 -or $bytes[$peOffset + 1] -ne 0x45) { return 0 }
  return [BitConverter]::ToUInt16($bytes, $peOffset + 4)
}

function Invoke-Engine([string]$Exe, [string[]]$EngineArgs, [int]$TimeoutSeconds = 120) {
  $quoted = ($EngineArgs | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join ' '
  $info = New-Object System.Diagnostics.ProcessStartInfo
  $info.FileName = $Exe
  $info.Arguments = $quoted
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  # Same setup the app uses: hidden console, UTF-8 protocol stream.
  $info.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
  $info.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
  $info.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $info
  [void]$process.Start()
  $stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $stderrTask = $process.StandardError.ReadToEndAsync()
  if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    try { $process.Kill() } catch { }
    return @{ ExitCode = -1; TimedOut = $true; StdOut = ''; StdErr = "timed out after $TimeoutSeconds s" }
  }
  $process.WaitForExit()
  $out = $stdoutTask.Result
  $err = $stderrTask.Result
  $code = $process.ExitCode
  $process.Dispose()
  return @{ ExitCode = $code; TimedOut = $false; StdOut = $out; StdErr = $err }
}

function Get-JsonLines([string]$Text) {
  foreach ($line in ($Text -split "`r?`n")) {
    $trimmed = $line.Trim()
    if ($trimmed.Length -gt 0) { $trimmed }
  }
}

function New-SilentWav([string]$Path, [int]$Seconds = 1) {
  $samples = $Seconds * 16000 * 2
  $bytes = New-Object byte[] (44 + $samples)
  [Text.Encoding]::ASCII.GetBytes('RIFF').CopyTo($bytes, 0)
  [BitConverter]::GetBytes([int](36 + $samples)).CopyTo($bytes, 4)
  [Text.Encoding]::ASCII.GetBytes('WAVEfmt ').CopyTo($bytes, 8)
  [BitConverter]::GetBytes([int]16).CopyTo($bytes, 16)
  [BitConverter]::GetBytes([int16]1).CopyTo($bytes, 20)
  [BitConverter]::GetBytes([int16]1).CopyTo($bytes, 22)
  [BitConverter]::GetBytes([int]16000).CopyTo($bytes, 24)
  [BitConverter]::GetBytes([int]32000).CopyTo($bytes, 28)
  [BitConverter]::GetBytes([int16]2).CopyTo($bytes, 32)
  [BitConverter]::GetBytes([int16]16).CopyTo($bytes, 34)
  [Text.Encoding]::ASCII.GetBytes('data').CopyTo($bytes, 36)
  [BitConverter]::GetBytes([int]$samples).CopyTo($bytes, 40)
  [IO.File]::WriteAllBytes($Path, $bytes)
}

$Zip = (Resolve-Path $Zip).Path
if (-not $Receipt) { $Receipt = "$Zip.receipt.txt" }
if (-not (Test-Path $Receipt)) { throw "Build receipt not found: $Receipt" }
$receiptValues = @{}
foreach ($line in (Get-Content -LiteralPath $Receipt -Encoding UTF8)) {
  if ($line -match '^\s*([A-Za-z0-9._-]+)\s*:\s*(.*)$') { $receiptValues[$Matches[1]] = $Matches[2].Trim() }
}

$ownExtract = $false
if (-not $ExtractDir) {
  $ExtractDir = Join-Path ([IO.Path]::GetTempPath()) ('gipformer-addon-verify-' + [Guid]::NewGuid().ToString('N'))
  $ownExtract = $true
}
$ExtractDir = [IO.Path]::GetFullPath($ExtractDir)
if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

Write-Host "Gipformer add-on verification"
Write-Host "  archive: $Zip"

try {
  Write-Host "Archive and receipt"
  Check ($receiptValues.ContainsKey('zip-sha256')) 'receipt records the archive SHA-256'
  $zipHash = Get-Sha256 $Zip
  Check ($receiptValues['zip-sha256'] -eq $zipHash) "archive SHA-256 matches receipt ($zipHash)"

  [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $ExtractDir)
  $addonRoot = Join-Path $ExtractDir 'Gipformer'
  $manifestPath = Join-Path $addonRoot 'addon.json'
  Check (Test-Path $manifestPath -PathType Leaf) 'archive root contains exactly Gipformer/addon.json'
  if (-not (Test-Path $manifestPath -PathType Leaf)) { throw 'addon.json missing; cannot continue' }

  $manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
  $manifestHash = Get-Sha256 $manifestPath
  Check ($receiptValues['manifest-sha256'] -eq $manifestHash) "addon.json SHA-256 matches receipt ($manifestHash)"
  Check ($manifestBytes.Length -eq [int]$receiptValues['manifest-bytes']) 'addon.json size matches receipt'

  Write-Host "Manifest identity"
  $manifest = [IO.File]::ReadAllText($manifestPath, [Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
  Check ($manifest.formatVersion -eq 1) 'formatVersion is 1'
  Check ($manifest.os -eq 'windows') 'os is windows'
  Check ($manifest.architecture -eq 'x64') 'architecture is x64'
  Check ($manifest.engineId -eq 'sherpa-onnx') 'engineId is sherpa-onnx'
  Check ($manifest.packId -eq 'gipformer1.5-vi') 'packId is gipformer1.5-vi'
  Check ($manifest.addonId -eq 'gipformer-vi') 'addonId is gipformer-vi'
  Check (($manifest.languages -contains 'vi') -and ($manifest.languages.Count -eq 1)) 'languages is exactly [vi]'

  Write-Host "Packaged file map"
  $listed = New-Object System.Collections.Generic.HashSet[string]
  $badPaths = New-Object System.Collections.Generic.List[string]
  $payloadCount = 0
  $mismatches = New-Object System.Collections.Generic.List[string]
  foreach ($entry in $manifest.files.PSObject.Properties) {
    $payloadCount++
    $relative = $entry.Name
    $segments = $relative -split '/'
    $bad = $relative.StartsWith('/') -or $relative.Contains('\') -or $relative.Contains(':') -or
           [IO.Path]::IsPathRooted($relative) -or ($segments -contains '.') -or ($segments -contains '') -or
           ($segments -contains '..') -or $relative.StartsWith('Gipformer/')
    if ($bad) { $badPaths.Add($relative) }
    [void]$listed.Add($relative)
    $path = Join-Path $addonRoot ($relative -replace '/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path $path -PathType Leaf)) {
      $mismatches.Add("$relative (missing)")
      continue
    }
    $length = (Get-Item -LiteralPath $path).Length
    if ($length -ne [long]$entry.Value.size) { $mismatches.Add("$relative (size $length)") ; continue }
    if ((Get-Sha256 $path) -ne $entry.Value.sha256) { $mismatches.Add("$relative (sha256)") }
  }
  Check ($badPaths.Count -eq 0) 'every manifest path is a safe relative path'
  if ($badPaths.Count -gt 0) { $badPaths | ForEach-Object { Write-Host "       bad path: $_" -ForegroundColor Red } }
  Check ($mismatches.Count -eq 0) "every listed payload file matches size and SHA-256 ($payloadCount files)"
  if ($mismatches.Count -gt 0) { $mismatches | Select-Object -First 10 | ForEach-Object { Write-Host "       $_" -ForegroundColor Red } }
  Check ($receiptValues['payload-files'] -eq "$payloadCount") 'receipt payload file count matches the manifest'
  Check ($manifest.files.PSObject.Properties.Name -notcontains 'addon.json') 'manifest does not list itself'

  $unlisted = New-Object System.Collections.Generic.List[string]
  Get-ChildItem -LiteralPath $addonRoot -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($addonRoot.Length + 1) -replace '\\', '/'
    if ($relative -ne 'addon.json' -and -not $listed.Contains($relative)) { $unlisted.Add($relative) }
  }
  Check ($unlisted.Count -eq 0) 'payload contains no unlisted file'
  if ($unlisted.Count -gt 0) { $unlisted | Select-Object -First 10 | ForEach-Object { Write-Host "       unlisted: $_" -ForegroundColor Red } }

  foreach ($required in @('runtime/caption-engine.exe', 'runtime/_internal', 'pack/model.json', 'pack/model/encoder.onnx',
                          'pack/model/decoder.onnx', 'pack/model/joiner.onnx', 'pack/model/tokens.txt',
                          'pack/punct/vibert-capu.int8.onnx', 'pack/punct/vocab.txt',
                          'pack/punct/vocabulary/labels.txt', 'pack/silero_vad.onnx',
                          'pack/NOTICE.md', 'pack/model/LICENSE', 'pack/punct/ATTRIBUTION.md', 'BUILD-INFO.txt')) {
    Check (Test-Path (Join-Path $addonRoot ($required -replace '/', [IO.Path]::DirectorySeparatorChar))) "required entry present: $required"
  }

  Write-Host "Native architecture"
  $runtimeDir = Join-Path $addonRoot 'runtime'
  $nonX64 = New-Object System.Collections.Generic.List[string]
  $nativeCount = 0
  $nativeExtensions = @('.exe', '.dll', '.pyd')
  foreach ($nativeFile in @(Get-ChildItem -LiteralPath $runtimeDir -Recurse -File | Where-Object { $nativeExtensions -contains $_.Extension.ToLowerInvariant() })) {
    $nativeCount++
    $machine = Get-PeMachine $nativeFile.FullName
    if ($machine -ne 0x8664) { $nonX64.Add(('{0} (0x{1:X4})' -f $nativeFile.Name, $machine)) }
  }
  Check ($nonX64.Count -eq 0) "every native runtime binary is AMD64 ($nativeCount files)"
  if ($nonX64.Count -gt 0) { $nonX64 | Select-Object -First 5 | ForEach-Object { Write-Host "       $_" -ForegroundColor Red } }
  $cuda = @(Get-ChildItem -LiteralPath $runtimeDir -Recurse -File | Where-Object { $_.Name -match '^(cublas|cudnn)' -and $_.Extension -eq '.dll' })
  Check ($cuda.Count -eq 0) 'no CUDA runtime libraries shipped'
  $leaked = @(Get-ChildItem -LiteralPath $runtimeDir -Recurse -File | Where-Object { $_.Name -match '^(encoder|decoder|joiner)\.onnx$|^vibert-capu.*\.onnx$|^tokens\.txt$' })
  Check ($leaked.Count -eq 0) 'no model files leaked into runtime/'

  Write-Host "Protocol"
  $exe = Join-Path $runtimeDir 'caption-engine.exe'
  $pack = Join-Path $addonRoot 'pack'
  $scratch = Join-Path $ExtractDir '_smoke'
  New-Item -ItemType Directory -Force -Path $scratch | Out-Null
  $silence = Join-Path $scratch 'silence.wav'
  New-SilentWav $silence 1

  $help = Invoke-Engine $exe @('--help') 60
  Check ($help.ExitCode -eq 0) "--help exits 0 (got $($help.ExitCode))"
  Check ($help.StdOut -match '--model-dir') '--help documents --model-dir'
  Check ($help.StdOut -notmatch 'ImportError|ModuleNotFoundError|Traceback') '--help shows no import/loader crash'

  $wrongLanguage = Invoke-Engine $exe @('--model-dir', $pack, '--input', $silence, '--language', 'en', '--device', 'cpu') 120
  $wrongJson = Get-JsonLines $wrongLanguage.StdOut | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } }
  Check ($wrongLanguage.ExitCode -ne 0) "wrong language exits nonzero (got $($wrongLanguage.ExitCode))"
  Check (@($wrongJson | Where-Object { $_.type -eq 'error' }).Count -eq 1) 'wrong language emits one structured error'
  Check ($wrongLanguage.StdErr -notmatch 'ImportError|ModuleNotFoundError') 'wrong language is not an import crash'

  $noManifest = Join-Path $scratch 'pack-no-manifest'
  Copy-Item -Recurse -Force $pack $noManifest
  Remove-Item -Force (Join-Path $noManifest 'model.json')
  $missingManifest = Invoke-Engine $exe @('--model-dir', $noManifest, '--input', $silence, '--language', 'vi') 120
  Check ($missingManifest.ExitCode -ne 0) 'missing model.json exits nonzero'
  Check ($missingManifest.StdOut -match 'model.json') 'missing model.json names the missing manifest'

  $truncated = Join-Path $scratch 'pack-truncated'
  Copy-Item -Recurse -Force $pack $truncated
  Remove-Item -Force (Join-Path $truncated 'model/joiner.onnx')
  $missingFile = Invoke-Engine $exe @('--model-dir', $truncated, '--input', $silence, '--language', 'vi') 120
  Check ($missingFile.ExitCode -ne 0) 'incomplete pack exits nonzero'
  Check ($missingFile.StdOut -match 'Model pack is incomplete: missing model/joiner.onnx') 'incomplete pack names the missing model file'

  if ($SmokeWav) {
    Write-Host "Real-pack transcription"
    Check (Test-Path $SmokeWav -PathType Leaf) "smoke audio exists: $SmokeWav"
    $run = Invoke-Engine $exe @('--model-dir', $pack, '--input', $SmokeWav, '--language', 'vi', '--device', 'cpu', '--vad', 'on') 1800
    $messages = @()
    $protocolErrors = New-Object System.Collections.Generic.List[string]
    foreach ($line in (Get-JsonLines $run.StdOut)) {
      try { $messages += , ($line | ConvertFrom-Json -ErrorAction Stop) }
      catch { $protocolErrors.Add($line) }
    }
    Check ($run.ExitCode -eq 0) "real-pack run exits 0 (got $($run.ExitCode))"
    Check ($protocolErrors.Count -eq 0) 'every stdout line is a JSON object'
    Check (@($messages | Where-Object { $_.type -eq 'info' }).Count -eq 1) 'exactly one info message'
    Check (@($messages | Where-Object { $_.type -eq 'result' }).Count -eq 1) 'exactly one final result'
    Check (@($messages | Where-Object { $_.type -eq 'progress' -and $_.percent -eq 100 }).Count -ge 1) 'progress reaches 100 before the result'
    Check (@($messages | Where-Object { $_.type -eq 'error' }).Count -eq 0) 'no error message'
    Check ($run.StdErr -notmatch '"type"\s*:\s*"result"') 'stderr cannot carry a result'
    $result = $messages | Where-Object { $_.type -eq 'result' } | Select-Object -First 1
    if ($result) {
      Check ($result.transcript.language -eq 'vi') 'result language is vi'
      $words = @()
      foreach ($segment in $result.transcript.segments) { foreach ($word in $segment.words) { $words += $word } }
      Check ($words.Count -gt 0) "transcript has timed words ($($words.Count))"
      $badTime = @($words | Where-Object { $null -eq $_.start -or $null -eq $_.end -or $_.start -lt 0 -or $_.end -lt $_.start -or [double]::IsNaN($_.start) -or [double]::IsNaN($_.end) -or [double]::IsInfinity($_.start) -or [double]::IsInfinity($_.end) })
      Check ($badTime.Count -eq 0) 'every word has finite, nonnegative start and end >= start'
      $ordered = $true
      $previous = -1.0
      foreach ($word in $words) { if ($word.start -lt $previous) { $ordered = $false; break }; $previous = $word.start }
      Check $ordered 'word starts are nondecreasing in emitted order'
      $empty = @($words | Where-Object { -not $_.text -or $_.text.Trim().Length -eq 0 })
      Check ($empty.Count -eq 0) 'no empty word text'
      if ($RequireAccents) {
        $joined = ($words | ForEach-Object { $_.text }) -join ' '
        # Non-ASCII letters in a vi-only transcript are the Vietnamese diacritics.
        Check ($joined -match '[^\x00-\x7F]') 'transcript contains accented (non-ASCII) Vietnamese letters'
        Check ($joined -match '[.,!?]') 'transcript contains punctuation'
      }
    }
  }
} catch {
  Write-Host "  FAIL unexpected error: $($_.Exception.Message)" -ForegroundColor Red
  $failures.Add($_.Exception.Message)
} finally {
  if (-not $KeepExtract -and $ownExtract) { Remove-Item -Recurse -Force $ExtractDir -ErrorAction SilentlyContinue }
}

Write-Host ""
if ($failures.Count -gt 0) {
  Write-Host ("Verification FAILED: {0} of {1} checks" -f $failures.Count, $checks) -ForegroundColor Red
  exit 1
}
Write-Host ("Verification passed: {0} checks" -f $checks) -ForegroundColor Green
exit 0
