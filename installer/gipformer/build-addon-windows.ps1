#requires -Version 5.1
<#
.SYNOPSIS
  Builds the Gipformer - Vietnamese add-on ZIP for Subtitle Edit on Windows x64 (CPU only).

.DESCRIPTION
  Frozen-runtime build only; nothing here touches the Subtitle Edit solution or the CaptionHelper
  checkout. Steps:

    1. Verify the interpreter and build venv are CPython 3.11, 64-bit, win32/AMD64.
    2. Install the build environment exclusively from installer/gipformer/requirements-win.lock.txt
       with --require-hashes --only-binary=:all: (no unpinned PyInstaller/hooks install).
    3. Verify the prepared model pack against the pinned upstream revisions/hashes from the
       vendored prepare_model.py and write its canonical pack/model.json.
    4. Freeze the caption engine with the relocated spec (same dependency collection as
       CaptionHelper), then reject CUDA libraries, model files and any non-AMD64 PE.
    5. Assemble <stage>/Gipformer/{addon.json,runtime,pack,licenses,BUILD-INFO.txt}, list every
       payload file with size/SHA-256 (addon.json excluded from its own map), and zip it.
    6. Write the external build receipt (<Output>.receipt.txt) with the ZIP and addon.json hashes,
       then run verify-addon-windows.ps1 on the finished archive.

  The archive is a private, not release-cleared artifact: CaptionHelper's source permission and the
  bundled FFmpeg codec obligations are unresolved (see licenses/THIRD-PARTY-NOTICES.md).

.PARAMETER Python
  CPython 3.11 x64 interpreter used to create the build venv.
.PARAMETER ModelPack
  Prepared sherpa-onnx pack folder (model/, punct/, silero_vad.onnx, NOTICE.md). Its model.json is
  rewritten canonically; the pack itself is never modified outside that file.
.PARAMETER Output
  Output ZIP path. Default: <repo>/x64/gipformer-addon-build/gipformer-vi-win-x64.zip
.PARAMETER VenvDir
  Build venv folder. Default: <repo>/x64/gipformer-addon-build/venv
.PARAMETER WorkDir
  Staging/build folder (cleared on every run). Default: <repo>/x64/gipformer-addon-build/work
.PARAMETER SkipInstall
  Reuse the venv without running the hash-locked pip install.
.PARAMETER SkipVerify
  Do not run verify-addon-windows.ps1 on the finished archive.
.PARAMETER SmokeWav
  Optional audio file passed to the verifier for a real-pack transcription smoke.
#>
[CmdletBinding()]
param(
  [string]$Python = 'python',
  [Parameter(Mandatory = $true)][string]$ModelPack,
  [string]$Output,
  [string]$VenvDir,
  [string]$WorkDir,
  [switch]$SkipInstall,
  [switch]$SkipVerify,
  [string]$SmokeWav
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

$AddonVersion = '1.0.0'
$AddonId = 'gipformer-vi'
$PackId = 'gipformer1.5-vi'
$EngineId = 'sherpa-onnx'

$addonRoot = $PSScriptRoot                                  # <repo>/installer/gipformer
$repoRoot = Split-Path -Parent (Split-Path -Parent $addonRoot)
$engineDir = Join-Path $addonRoot 'engine'
$lockFile = Join-Path $addonRoot 'requirements-win.lock.txt'
$packManifestTool = Join-Path $addonRoot 'make_pack_manifest.py'
$verifier = Join-Path $addonRoot 'verify-addon-windows.ps1'
$staticLicenses = Join-Path $addonRoot 'licenses'

if (-not $Output) { $Output = Join-Path $repoRoot 'x64/gipformer-addon-build/gipformer-vi-win-x64.zip' }
if (-not $VenvDir) { $VenvDir = Join-Path $repoRoot 'x64/gipformer-addon-build/venv' }
if (-not $WorkDir) { $WorkDir = Join-Path $repoRoot 'x64/gipformer-addon-build/work' }
$Output = [IO.Path]::GetFullPath($Output)
$VenvDir = [IO.Path]::GetFullPath($VenvDir)
$WorkDir = [IO.Path]::GetFullPath($WorkDir)
$ModelPack = (Resolve-Path $ModelPack).Path

function Invoke-Checked {
  param([string]$File, [string[]]$Arguments)
  & $File @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$File exited with code $LASTEXITCODE ($($Arguments -join ' '))" }
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

function Assert-Python311X64([string]$Interpreter) {
  $probe = & $Interpreter -c "import sys,platform,struct;print(sys.version.split()[0]);print(struct.calcsize('P')*8);print(platform.machine());print(sys.platform)"
  if ($LASTEXITCODE -ne 0) { throw "Could not run $Interpreter" }
  if ($probe[0] -notmatch '^3\.11\.') { throw "Python 3.11 is required (found $($probe[0])): $Interpreter" }
  if ($probe[1] -ne '64') { throw "64-bit Python is required (found $($probe[1])-bit): $Interpreter" }
  if ($probe[2] -ne 'AMD64') { throw "AMD64/x64 Python is required (found $($probe[2])): $Interpreter" }
  if ($probe[3] -ne 'win32') { throw "Windows Python is required (found $($probe[3])): $Interpreter" }
  return $probe[0]
}

# --- 1. Interpreter and venv -------------------------------------------------------------
Write-Host "== Interpreter"
$pythonVersion = Assert-Python311X64 $Python
Write-Host "   Python $pythonVersion x64"

$venvPython = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Host "   creating venv $VenvDir"
  Invoke-Checked $Python @('-m', 'venv', $VenvDir)
}
[void](Assert-Python311X64 $venvPython)

# --- 2. Locked build environment ---------------------------------------------------------
if (-not $SkipInstall) {
  Write-Host "== Installing locked build dependencies"
  Invoke-Checked $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '--require-hashes',
    '--only-binary=:all:', '-r', $lockFile)
} else {
  Write-Host "== Reusing existing build environment (-SkipInstall)"
}

$lockVersions = @{}
foreach ($line in (Get-Content -LiteralPath $lockFile -Encoding UTF8)) {
  if ($line -match '^\s*([A-Za-z0-9._-]+)==([^\s\\]+)') { $lockVersions[$Matches[1].ToLowerInvariant()] = $Matches[2] }
}
function Get-LockedVersion([string]$Name) {
  if ($lockVersions.ContainsKey($Name.ToLowerInvariant())) { return $lockVersions[$Name.ToLowerInvariant()] }
  return 'not in lock'
}

# --- 3. Model pack -----------------------------------------------------------------------
Write-Host "== Verifying model pack"
$packLabel = (& $venvPython $packManifestTool --pack $ModelPack | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Model pack verification failed: $packLabel" }
Write-Host "   $packLabel"

# --- 4. Frozen runtime -------------------------------------------------------------------
Write-Host "== Building frozen runtime"
if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
$pyiDist = Join-Path $WorkDir 'pyi-dist'
$pyiBuild = Join-Path $WorkDir 'pyi-build'
New-Item -ItemType Directory -Force -Path $pyiDist, $pyiBuild | Out-Null

Push-Location $engineDir
try {
  Invoke-Checked $venvPython @('-m', 'PyInstaller', (Join-Path $engineDir 'caption_engine.spec'), '--noconfirm',
    '--clean', '--distpath', $pyiDist, '--workpath', $pyiBuild)
} finally {
  Pop-Location
}

$frozenDir = Join-Path $pyiDist 'caption-engine'
$frozenExe = Join-Path $frozenDir 'caption-engine.exe'
if (-not (Test-Path $frozenExe)) { throw "Build finished but $frozenExe is missing" }

$nativeExtensions = @('.exe', '.dll', '.pyd')
$nativeFiles = @(Get-ChildItem -LiteralPath $frozenDir -Recurse -File | Where-Object { $nativeExtensions -contains $_.Extension.ToLowerInvariant() })
$nonX64 = New-Object System.Collections.Generic.List[string]
foreach ($nativeFile in $nativeFiles) {
  $machine = Get-PeMachine $nativeFile.FullName
  if ($machine -ne 0x8664) { $nonX64.Add(('{0} (0x{1:X4})' -f $nativeFile.Name, $machine)) }
}
if ($nonX64.Count -gt 0) { throw "Non-AMD64 binaries in the frozen runtime: $($nonX64 -join ', ')" }
$cuda = @(Get-ChildItem -LiteralPath $frozenDir -Recurse -File | Where-Object { $_.Name -match '^(cublas|cudnn)' -and $_.Extension -eq '.dll' })
if ($cuda.Count -gt 0) { throw "CUDA DLLs leaked into the runtime: $(($cuda | ForEach-Object { $_.Name }) -join ', ')" }
$leaked = @(Get-ChildItem -LiteralPath $frozenDir -Recurse -File | Where-Object { $_.Name -match '^(encoder|decoder|joiner)\.onnx$|^vibert-capu.*\.onnx$|^tokens\.txt$' })
if ($leaked.Count -gt 0) { throw "Model files leaked into the runtime: $(($leaked | ForEach-Object { $_.Name }) -join ', ')" }
Write-Host ("   runtime: {0:N0} MiB, {1} native binaries, all AMD64" -f ((Get-ChildItem -LiteralPath $frozenDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), $nativeFiles.Count)

# --- 5. Assemble the add-on tree ---------------------------------------------------------
Write-Host "== Staging add-on layout"
$stage = Join-Path $WorkDir 'stage'
$stageAddon = Join-Path $stage 'Gipformer'
$runtimeTarget = Join-Path $stageAddon 'runtime'
$packTarget = Join-Path $stageAddon 'pack'
$licensesTarget = Join-Path $stageAddon 'licenses'
New-Item -ItemType Directory -Force -Path $runtimeTarget, $packTarget, $licensesTarget | Out-Null

Copy-Item -Path (Join-Path $frozenDir '*') -Destination $runtimeTarget -Recurse -Force
foreach ($entry in Get-ChildItem -LiteralPath $ModelPack -Force) {
  if ($entry.Name -eq 'model.json') { continue }
  Copy-Item -LiteralPath $entry.FullName -Destination $packTarget -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $ModelPack 'model.json') -Destination (Join-Path $packTarget 'model.json') -Force

# License texts taken from the installed distributions; components without a shipped text are
# listed in THIRD-PARTY-NOTICES.md so the gap is visible instead of silently absent.
$licensePackages = [ordered]@{
  'faster-whisper'   = 'faster_whisper-1.2.1'
  'ctranslate2'      = 'ctranslate2-4.8.2'
  'pyav-ffmpeg'      = 'av-18.1.0'
  'onnxruntime'      = 'onnxruntime-1.31.0'
  'sherpa-onnx'      = 'sherpa_onnx-1.13.8'
  'sherpa-onnx-core' = 'sherpa_onnx_core-1.13.8'
  'numpy'            = 'numpy-2.4.6'
  'tokenizers'       = 'tokenizers-0.23.3'
  'pyinstaller'      = 'pyinstaller-6.22.3'
}
$sitePackages = Join-Path $VenvDir 'Lib\site-packages'
foreach ($component in $licensePackages.Keys) {
  $distInfo = Get-ChildItem -LiteralPath $sitePackages -Directory -Filter "$($licensePackages[$component]).dist-info" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $distInfo) { Write-Warning "License source missing for $component ($($licensePackages[$component]))"; continue }
  $componentDir = Join-Path $licensesTarget $component
  New-Item -ItemType Directory -Force -Path $componentDir | Out-Null
  Get-ChildItem -LiteralPath $distInfo.FullName -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE)' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $componentDir -Force
  }
  $licensesSub = Join-Path $distInfo.FullName 'licenses'
  if (Test-Path $licensesSub) { Copy-Item -Path (Join-Path $licensesSub '*') -Destination $componentDir -Recurse -Force }
}
# CPython itself: the interpreter's LICENSE.txt.
$pythonLicense = Join-Path (Split-Path -Parent $Python) 'LICENSE.txt'
$pythonDir = Join-Path $licensesTarget 'python'
New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null
if (Test-Path $pythonLicense) {
  Copy-Item -LiteralPath $pythonLicense -Destination $pythonDir -Force
} else {
  Write-Warning "Python LICENSE.txt not found next to $Python"
}
if (Test-Path $staticLicenses) {
  Copy-Item -Path (Join-Path $staticLicenses '*') -Destination $licensesTarget -Recurse -Force
}

$builtUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$buildInfo = @(
  'Gipformer - Vietnamese add-on for Subtitle Edit',
  '',
  "addon: $AddonId $AddonVersion",
  "built-utc: $builtUtc",
  'platform: windows x64 (CPU only)',
  'distribution: private / not release-cleared - see licenses/THIRD-PARTY-NOTICES.md',
  '',
  "python: $pythonVersion (64-bit)",
  "pyinstaller: $(Get-LockedVersion 'pyinstaller')",
  "onnxruntime: $(Get-LockedVersion 'onnxruntime')",
  "sherpa-onnx: $(Get-LockedVersion 'sherpa-onnx') (sherpa-onnx-core $(Get-LockedVersion 'sherpa-onnx-core'))",
  "faster-whisper: $(Get-LockedVersion 'faster-whisper') (ctranslate2 $(Get-LockedVersion 'ctranslate2'))",
  "pyav: $(Get-LockedVersion 'av')",
  "numpy: $(Get-LockedVersion 'numpy')",
  "tokenizers: $(Get-LockedVersion 'tokenizers')",
  '',
  "pack: $PackId",
  "pack-source: $packLabel",
  'engine-source: CaptionHelper snapshot; see addon.json -> source'
) -join [Environment]::NewLine
[IO.File]::WriteAllText((Join-Path $stageAddon 'BUILD-INFO.txt'), $buildInfo + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))

# Source provenance in the manifest: digests of the snapshotted engine files, no machine paths.
$sourceFiles = [ordered]@{}
Get-ChildItem -LiteralPath $engineDir -Recurse -File | Where-Object { $_.Extension -in '.py', '.spec' } | Sort-Object FullName | ForEach-Object {
  $relative = 'engine/' + ($_.FullName.Substring($engineDir.Length + 1) -replace '\\', '/')
  $sourceFiles[$relative] = Get-Sha256 $_.FullName
}
$captionHelperCommit = '95eeed679638044d44826f630cb4c98d69e1e224'

$files = [ordered]@{}
Get-ChildItem -LiteralPath $stageAddon -Recurse -File | Sort-Object FullName | ForEach-Object {
  $relative = $_.FullName.Substring($stageAddon.Length + 1) -replace '\\', '/'
  if ($relative -eq 'addon.json') { return }
  $files[$relative] = [ordered]@{ size = $_.Length; sha256 = (Get-Sha256 $_.FullName) }
}

$manifest = [ordered]@{
  formatVersion = 1
  addonId = $AddonId
  addonVersion = $AddonVersion
  os = 'windows'
  architecture = 'x64'
  engineId = $EngineId
  packId = $PackId
  languages = @('vi')
  runtime = [ordered]@{ folder = 'runtime'; executable = 'runtime/caption-engine.exe' }
  packFolder = 'pack'
  source = [ordered]@{
    captionhelperCommit = $captionHelperCommit
    captionhelperSourceFiles = $sourceFiles
  }
  files = $files
}
$manifestPath = Join-Path $stageAddon 'addon.json'
$manifestJson = $manifest | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($manifestPath, $manifestJson + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
Write-Host ("   {0} payload files, addon.json lists them (manifest itself excluded)" -f $files.Count)

# --- 6. Archive + receipt ----------------------------------------------------------------
Write-Host "== Creating archive"
$outputDir = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
if (Test-Path $Output) { Remove-Item -Force $Output }
[IO.Compression.ZipFile]::CreateFromDirectory($stage, $Output, [IO.Compression.CompressionLevel]::Optimal, $false)

$receipt = $Output + '.receipt.txt'
$receiptText = @(
  'format: 1',
  "addon: $AddonId",
  "addon-version: $AddonVersion",
  "zip: $(Split-Path -Leaf $Output)",
  "zip-sha256: $(Get-Sha256 $Output)",
  'manifest: Gipformer/addon.json',
  "manifest-sha256: $(Get-Sha256 $manifestPath)",
  "manifest-bytes: $((Get-Item -LiteralPath $manifestPath).Length)",
  "payload-files: $($files.Count)",
  "built-utc: $builtUtc",
  'distribution: private/not-release-cleared',
  "verification: powershell -NoProfile -ExecutionPolicy Bypass -File installer/gipformer/verify-addon-windows.ps1 -Zip <zip> -Receipt <receipt>"
) -join [Environment]::NewLine
[IO.File]::WriteAllText($receipt, $receiptText + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))

Write-Host ("   ZIP   : {0} ({1:N1} MiB)" -f $Output, ((Get-Item $Output).Length / 1MB))
Write-Host ("   SHA256: {0}" -f (Get-Sha256 $Output))
Write-Host ("   receipt: {0}" -f $receipt)

if (-not $SkipVerify) {
  Write-Host "== Verifying the finished archive"
  $verifyArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $verifier, '-Zip', $Output, '-Receipt', $receipt,
                  '-ExtractDir', (Join-Path $WorkDir 'verify-extract'))
  if ($SmokeWav) { $verifyArgs += @('-SmokeWav', $SmokeWav) }
  & powershell @verifyArgs
  if ($LASTEXITCODE -ne 0) { throw "Archive verification failed (exit $LASTEXITCODE)" }
}

Write-Host "Build complete: $Output"
