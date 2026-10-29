using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia.Platform;
using Nikse.SubtitleEdit.Logic.Config;
using Nikse.SubtitleEdit.UiLogic.AudioToText;

namespace Nikse.SubtitleEdit.Features.Video.SpeechToText.Engines;

/// <summary>Why a Gipformer add-on folder is (not) usable.</summary>
public enum GipformerInstallStatus
{
    /// <summary>No add-on folder or no addon.json: the user has not extracted the archive yet.</summary>
    NotInstalled,

    /// <summary>The manifest is there but a required runtime/pack file is missing or empty.</summary>
    Incomplete,

    /// <summary>The manifest declares a format/version this build does not understand.</summary>
    UnsupportedVersion,

    /// <summary>The manifest exists but is malformed, declares another platform/identity or has unsafe paths.</summary>
    InvalidManifest,

    Ready,
}

/// <summary>
/// Result of the cheap structural add-on check. <see cref="Detail"/> is a slash-separated relative
/// path or field name for the first problem found - suitable for a localized message, never shown raw.
/// </summary>
public sealed record GipformerInstallResult(GipformerInstallStatus Status, string Detail = "")
{
    public static GipformerInstallResult Ready { get; } = new(GipformerInstallStatus.Ready);

    public bool IsReady => Status == GipformerInstallStatus.Ready;
}

/// <summary>
/// Gipformer - Vietnamese: a manually installed local add-on (Windows x64, CPU only) built from
/// CaptionHelper's sherpa-onnx pipeline. The archive's contents live under
/// <c>[Data Folder]/SpeechToText/Gipformer</c>; nothing here downloads, imports or installs it.
///
/// Readiness is structural (identity, required files present and non-empty, sizes match the
/// manifest). Full SHA-256 verification belongs to the archive build/verification tooling, and
/// co-delivered hashes cannot authenticate a package someone replaced - see the add-on's
/// licenses/THIRD-PARTY-NOTICES.md.
/// </summary>
public class GipformerEngine : ISpeechToTextEngine
{
    public const string AddonFolderName = "Gipformer";
    public const string ManifestFileName = "addon.json";
    public const string PackFolderName = "pack";
    public const string ExecutableRelativePath = "runtime/caption-engine.exe";
    public const string InternalFolderName = "_internal";
    public const string AddonId = "gipformer-vi";
    public const string PackId = "gipformer1.5-vi";
    public const string EngineId = "sherpa-onnx";
    public const string LanguageCode = "vi";

    /// <summary>The only manifest format this build understands; anything else is refused, not guessed at.</summary>
    public const int SupportedManifestFormatVersion = 1;

    private const string HelpTextAssetName = "GipformerVietnamese.txt";

    /// <summary>Pack files the frozen sherpa-onnx backend needs; empty or renamed files make it fail at load.</summary>
    public static IReadOnlyList<string> RequiredPackFiles { get; } = new[]
    {
        "pack/model.json",
        "pack/model/encoder.onnx",
        "pack/model/decoder.onnx",
        "pack/model/joiner.onnx",
        "pack/model/tokens.txt",
        "pack/punct/vibert-capu.int8.onnx",
        "pack/punct/vocab.txt",
        "pack/punct/vocabulary/labels.txt",
        "pack/silero_vad.onnx",
    };

    /// <summary>
    /// Flags Subtitle Edit owns for this engine. Letting advanced parameters repeat them could
    /// redirect the input/pack or break the Vietnamese-only CPU contract, so they are refused.
    /// </summary>
    private static readonly string[] ReservedFlags =
    {
        "--model-dir", "--input", "--language", "--device", "--start", "--end",
        "--compute-type", "--detect-among", "--zh-script",
    };

    public static string StaticName => "Gipformer — Vietnamese";
    public string Name => StaticName;
    public string Choice => WhisperChoice.Gipformer;

    /// <summary>No product page exists for this private local add-on; the help asset explains installation.</summary>
    public string Url => string.Empty;

    public List<WhisperLanguage> Languages => new() { new WhisperLanguage(LanguageCode, "vietnamese") };

    public List<WhisperModel> Models => new()
    {
        new WhisperModel
        {
            Name = PackId,
            // The pack ships inside the add-on (ASR + punctuation + VAD, 387 MB); shown in the
            // model dropdown so the size is not mistaken for a download.
            Size = "387 MB",
            TranscribeOnly = true,
        },
    };

    public string Extension => string.Empty;
    public string UnpackSkipFolder => string.Empty;

    /// <summary>True only where an x64 Windows build of the add-on can run; other platforms hide the engine.</summary>
    public static bool IsSupportedPlatform =>
        OperatingSystem.IsWindows() && RuntimeInformation.ProcessArchitecture == Architecture.X64;

    public string CommandLineParameter
    {
        get => Se.Settings.Tools.AudioToText.CommandLineParameterGipformer;
        set => Se.Settings.Tools.AudioToText.CommandLineParameterGipformer = value;
    }

    public string GetAddonRoot(string? dataFolder = null)
    {
        var speechToTextFolder = string.IsNullOrEmpty(dataFolder)
            ? Se.SpeechToTextFolder
            : Path.Combine(dataFolder, "SpeechToText");
        return Path.Combine(speechToTextFolder, AddonFolderName);
    }

    public string GetAndCreateWhisperFolder()
    {
        var folder = GetAddonRoot();
        Directory.CreateDirectory(folder);
        return folder;
    }

    /// <summary>The pack is shipped inside the add-on; this never creates or downloads anything.</summary>
    public string GetAndCreateWhisperModelFolder(WhisperModel? whisperModel) => Path.Combine(GetAndCreateWhisperFolder(), PackFolderName);

    public string GetExecutable() => Path.Combine(GetAndCreateWhisperFolder(), "runtime", "caption-engine.exe");

    public string GetExecutableFileName() => "caption-engine.exe";

    /// <summary>Executable, <c>_internal</c> native tree and the full pack are required; no hashing here.</summary>
    public bool IsEngineInstalled() => CheckInstallation().IsReady;

    public bool IsModelInstalled(WhisperModel model) => CheckInstallation().IsReady;

    public bool CanBeDownloaded() => false;

    public bool DownloadsOwnModels => false;

    public bool SupportsCustomModels => false;

    /// <summary>Absolute pack folder, passed to the sidecar as <c>--model-dir</c>.</summary>
    public string GetModelForCmdLine(string modelName) => Path.Combine(GetAndCreateWhisperFolder(), PackFolderName);

    public string GetWhisperModelDownloadFileName(WhisperModel whisperModel, string url) => throw new NotSupportedException();

    public async Task<string> GetHelpText()
    {
        // Explicit asset name: the display name contains a dash and a space, so deriving the
        // resource from it (as the whisper engines do) would not match the embedded file.
        var uri = new Uri($"avares://SubtitleEdit/Assets/SpeechToText/{HelpTextAssetName}");
        await using var stream = AssetLoader.Open(uri);
        using var reader = new StreamReader(stream);
        return await reader.ReadToEndAsync();
    }

    /// <summary>
    /// Structural readiness check. Pass <paramref name="addonRoot"/> to check an isolated folder
    /// (tests, or a scratch extraction); the default is the real data folder. Cheap enough to run
    /// on every engine-picker render: it stats the required files and reads the two small
    /// manifests, and never hashes the multi-hundred-MB payload.
    /// </summary>
    public GipformerInstallResult CheckInstallation(string? addonRoot = null)
    {
        var root = addonRoot ?? GetAddonRoot();
        if (!Directory.Exists(root))
        {
            return new GipformerInstallResult(GipformerInstallStatus.NotInstalled);
        }

        var manifestPath = Path.Combine(root, ManifestFileName);
        if (!File.Exists(manifestPath))
        {
            return new GipformerInstallResult(GipformerInstallStatus.NotInstalled, ManifestFileName);
        }

        if (!TryReadManifest(manifestPath, out var manifest, out var manifestError))
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, manifestError);
        }

        if (!TryReadInt(manifest, "formatVersion", out var formatVersion) ||
            formatVersion != SupportedManifestFormatVersion)
        {
            return new GipformerInstallResult(
                GipformerInstallStatus.UnsupportedVersion,
                TryReadInt(manifest, "formatVersion", out var declared) ? declared.ToString() : "formatVersion");
        }

        if (ReadString(manifest, "os") != "windows" || ReadString(manifest, "architecture") != "x64")
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, "os/architecture");
        }

        if (ReadString(manifest, "addonId") != AddonId ||
            ReadString(manifest, "engineId") != EngineId ||
            ReadString(manifest, "packId") != PackId)
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, "identity");
        }

        if (!manifest.TryGetProperty("files", out var files) || files.ValueKind != JsonValueKind.Object)
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, "files");
        }

        foreach (var entry in files.EnumerateObject())
        {
            if (!IsSafeRelativePath(entry.Name))
            {
                return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, entry.Name);
            }
        }

        foreach (var required in RequiredAddonFiles())
        {
            if (!files.TryGetProperty(required, out var fileEntry) ||
                fileEntry.ValueKind != JsonValueKind.Object ||
                !TryReadLong(fileEntry, "size", out var declaredSize))
            {
                return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, required);
            }

            var fullPath = Path.Combine(root, required.Replace('/', Path.DirectorySeparatorChar));
            if (!File.Exists(fullPath))
            {
                return new GipformerInstallResult(GipformerInstallStatus.Incomplete, required);
            }

            var actualSize = new FileInfo(fullPath).Length;
            if (actualSize <= 0)
            {
                return new GipformerInstallResult(GipformerInstallStatus.Incomplete, required);
            }

            // Size drift catches a truncated copy or a partially replaced installation without
            // hashing the whole payload; the value comes from the package's own manifest, so it is
            // a completeness check, not authentication.
            if (actualSize != declaredSize)
            {
                return new GipformerInstallResult(GipformerInstallStatus.Incomplete, required);
            }
        }

        var internalFolder = Path.Combine(root, "runtime", InternalFolderName);
        if (!Directory.Exists(internalFolder))
        {
            return new GipformerInstallResult(GipformerInstallStatus.Incomplete, $"runtime/{InternalFolderName}");
        }

        if (!EnumerateTopLevel(internalFolder, "*.dll").Any())
        {
            return new GipformerInstallResult(GipformerInstallStatus.Incomplete, $"runtime/{InternalFolderName}");
        }

        var packManifestPath = Path.Combine(root, "pack", "model.json");
        if (!TryReadManifest(packManifestPath, out var packManifest, out var packError))
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, packError);
        }

        if (ReadString(packManifest, "id") != PackId || ReadString(packManifest, "engine") != EngineId)
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, "pack/model.json");
        }

        if (!packManifest.TryGetProperty("languages", out var languages) ||
            languages.ValueKind != JsonValueKind.Array ||
            !languages.EnumerateArray().Any(p => p.ValueKind == JsonValueKind.String && p.GetString() == LanguageCode))
        {
            return new GipformerInstallResult(GipformerInstallStatus.InvalidManifest, "pack/model.json");
        }

        return GipformerInstallResult.Ready;
    }

    private static IEnumerable<string> RequiredAddonFiles()
    {
        yield return ExecutableRelativePath;
        yield return "pack/model.json";
        foreach (var packFile in RequiredPackFiles.Where(p => p != "pack/model.json"))
        {
            yield return packFile;
        }
    }

    private static IEnumerable<string> EnumerateTopLevel(string folder, string pattern)
    {
        try
        {
            return Directory.EnumerateFiles(folder, pattern, SearchOption.TopDirectoryOnly);
        }
        catch (IOException)
        {
            return Array.Empty<string>();
        }
        catch (UnauthorizedAccessException)
        {
            return Array.Empty<string>();
        }
    }

    private static bool TryReadManifest(string path, out JsonElement manifest, out string error)
    {
        manifest = default;
        error = string.Empty;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllBytes(path));
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                error = Path.GetFileName(path);
                return false;
            }

            // Clone so the element survives the JsonDocument's disposal.
            manifest = document.RootElement.Clone();
            return true;
        }
        catch (Exception exception) when (exception is JsonException or IOException or UnauthorizedAccessException)
        {
            error = Path.GetFileName(path);
            return false;
        }
    }

    private static string? ReadString(JsonElement element, string name)
    {
        return element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    private static bool TryReadInt(JsonElement element, string name, out int value)
    {
        value = 0;
        return element.TryGetProperty(name, out var property) &&
               property.ValueKind == JsonValueKind.Number &&
               property.TryGetInt32(out value);
    }

    private static bool TryReadLong(JsonElement element, string name, out long value)
    {
        value = 0;
        return element.TryGetProperty(name, out var property) &&
               property.ValueKind == JsonValueKind.Number &&
               property.TryGetInt64(out value);
    }

    /// <summary>
    /// Slash-separated relative path below the add-on root: no rooted paths, no drive letters, no
    /// empty/'.'/'..' segments. Manifest paths are only ever used to locate packaged files, never
    /// to pick the executable, but a traversing entry still means the package is not the one we built.
    /// </summary>
    public static bool IsSafeRelativePath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || path.Contains('\\') || path.Contains(':'))
        {
            return false;
        }

        if (path.StartsWith('/') || Path.IsPathRooted(path))
        {
            return false;
        }

        foreach (var segment in path.Split('/'))
        {
            if (segment.Length == 0 || segment == "." || segment == "..")
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Parses the advanced-parameters string into process arguments using Windows quoting rules
    /// (<c>"</c> groups, <c>\"</c> escapes). Returns false with a user-facing reason when the text
    /// is unterminated, repeats a reserved flag or names a flag the sidecar does not accept - an
    /// invalid parameter must never be silently ignored or shell-executed.
    /// </summary>
    public static bool TryParseAdvancedArguments(string? parameters, out List<string> arguments, out string error)
    {
        arguments = new List<string>();
        error = string.Empty;
        if (string.IsNullOrWhiteSpace(parameters))
        {
            return true;
        }

        var current = new StringBuilder();
        var inQuotes = false;
        var hasToken = false;

        for (var i = 0; i < parameters.Length; i++)
        {
            var c = parameters[i];
            if (c == '"')
            {
                inQuotes = !inQuotes;
                hasToken = true;
                continue;
            }

            if (!inQuotes && char.IsWhiteSpace(c))
            {
                if (hasToken)
                {
                    arguments.Add(current.ToString());
                    current.Clear();
                    hasToken = false;
                }

                continue;
            }

            if (c == '\\' && i + 1 < parameters.Length && (parameters[i + 1] == '"' || parameters[i + 1] == '\\'))
            {
                current.Append(parameters[i + 1]);
                hasToken = true;
                i++;
                continue;
            }

            current.Append(c);
            hasToken = true;
        }

        if (inQuotes)
        {
            error = "unterminated quote";
            return false;
        }

        if (hasToken)
        {
            arguments.Add(current.ToString());
        }

        for (var i = 0; i < arguments.Count; i++)
        {
            var token = arguments[i];
            if (!token.StartsWith("--", StringComparison.Ordinal))
            {
                error = token;
                return false;
            }

            var flag = token;
            string? inlineValue = null;
            var equalsIndex = token.IndexOf('=');
            if (equalsIndex > 0)
            {
                flag = token[..equalsIndex];
                inlineValue = token[(equalsIndex + 1)..];
            }

            if (ReservedFlags.Contains(flag, StringComparer.Ordinal))
            {
                error = flag;
                return false;
            }

            switch (flag)
            {
                case "--vad":
                case "--threads":
                    break;
                default:
                    error = flag;
                    return false;
            }

            if (inlineValue != null)
            {
                if (!IsValidValue(flag, inlineValue, out error))
                {
                    return false;
                }

                continue;
            }

            if (i + 1 >= arguments.Count)
            {
                error = flag;
                return false;
            }

            var value = arguments[++i];
            if (!IsValidValue(flag, value, out error))
            {
                return false;
            }
        }

        return true;
    }

    private static bool IsValidValue(string flag, string value, out string error)
    {
        error = string.Empty;
        if (flag == "--vad")
        {
            if (value is "on" or "off")
            {
                return true;
            }

            error = value;
            return false;
        }

        if (int.TryParse(value, out var threads) && threads >= 1)
        {
            return true;
        }

        error = value;
        return false;
    }

    public override string ToString() => Name;
}
