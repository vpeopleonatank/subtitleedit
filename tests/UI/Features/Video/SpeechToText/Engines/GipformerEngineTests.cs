using System.Text;
using System.Text.Json;
using Avalonia.Headless.XUnit;
using Nikse.SubtitleEdit.Features.Video.SpeechToText.Engines;
using Nikse.SubtitleEdit.UiLogic.AudioToText;

namespace UITests.Features.Video.SpeechToText.Engines;

/// <summary>
/// The Gipformer add-on is installed by hand, so the engine's only job before launch is a
/// structural readiness check plus the fixed argument surface: a half-extracted folder must be
/// reported as incomplete (with the file to replace) instead of failing minutes later inside the
/// sidecar, and no advanced parameter may override the Vietnamese-on-CPU contract.
/// </summary>
public class GipformerEngineTests : IDisposable
{
    private readonly List<string> _roots = new();

    public void Dispose()
    {
        foreach (var root in _roots)
        {
            try
            {
                Directory.Delete(root, recursive: true);
            }
            catch (IOException)
            {
                // A leftover temp folder is not worth failing a test run.
            }
        }
    }

    private sealed record AddonFixture(string Root, Dictionary<string, long> Sizes);

    private AddonFixture CreateCompleteAddon()
    {
        var root = Path.Combine(Path.GetTempPath(), "gipformer-addon-tests", Guid.NewGuid().ToString("N"));
        _roots.Add(root);
        Directory.CreateDirectory(root);

        var sizes = new Dictionary<string, long>(StringComparer.Ordinal);
        void Write(string relative, byte[] content)
        {
            var path = Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllBytes(path, content);
            sizes[relative] = content.Length;
        }

        Write("pack/model.json", PackManifest());
        foreach (var relative in GipformerEngine.RequiredPackFiles.Where(p => p != "pack/model.json"))
        {
            Write(relative, new byte[64]);
        }

        Write("runtime/caption-engine.exe", new byte[1024]);
        Write("runtime/_internal/python311.dll", new byte[256]);
        Write("licenses/THIRD-PARTY-NOTICES.md", new byte[32]);

        WriteManifest(root, sizes);

        return new AddonFixture(root, sizes);
    }

    private static byte[] PackManifest() =>
        Encoding.UTF8.GetBytes("{\"id\":\"gipformer1.5-vi\",\"engine\":\"sherpa-onnx\",\"languages\":[\"vi\"]}");

    private static void WriteManifest(
        string root,
        IReadOnlyDictionary<string, long> sizes,
        int formatVersion = 1,
        string os = "windows",
        string architecture = "x64",
        string addonId = GipformerEngine.AddonId,
        string engineId = GipformerEngine.EngineId,
        string packId = GipformerEngine.PackId,
        IReadOnlyDictionary<string, long>? extraFiles = null)
    {
        var files = new Dictionary<string, object>();
        foreach (var (path, size) in sizes)
        {
            files[path] = new { size };
        }

        if (extraFiles != null)
        {
            foreach (var (path, size) in extraFiles)
            {
                files[path] = new { size };
            }
        }

        var manifest = new
        {
            formatVersion,
            os,
            architecture,
            addonId,
            engineId,
            packId,
            version = "1.0.0",
            files,
        };

        File.WriteAllText(Path.Combine(root, GipformerEngine.ManifestFileName), JsonSerializer.Serialize(manifest));
    }

    [Fact]
    public void MissingFolder_IsNotInstalled()
    {
        var root = Path.Combine(Path.GetTempPath(), "gipformer-addon-tests", "absent-" + Guid.NewGuid().ToString("N"));
        _roots.Add(root);

        var result = new GipformerEngine().CheckInstallation(root);

        Assert.Equal(GipformerInstallStatus.NotInstalled, result.Status);
        Assert.False(result.IsReady);
    }

    [Fact]
    public void FolderWithoutManifest_IsNotInstalled()
    {
        var root = Path.Combine(Path.GetTempPath(), "gipformer-addon-tests", Guid.NewGuid().ToString("N"));
        _roots.Add(root);
        Directory.CreateDirectory(root);

        var result = new GipformerEngine().CheckInstallation(root);

        Assert.Equal(GipformerInstallStatus.NotInstalled, result.Status);
        Assert.Equal(GipformerEngine.ManifestFileName, result.Detail);
    }

    [Fact]
    public void UnparseableManifest_IsInvalid()
    {
        var fixture = CreateCompleteAddon();
        File.WriteAllText(Path.Combine(fixture.Root, GipformerEngine.ManifestFileName), "{not json");

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.InvalidManifest, result.Status);
    }

    [Fact]
    public void LaterFormatVersion_IsRefused()
    {
        var fixture = CreateCompleteAddon();
        WriteManifest(fixture.Root, fixture.Sizes, formatVersion: 2);

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.UnsupportedVersion, result.Status);
        Assert.Equal("2", result.Detail);
    }

    [Theory]
    [InlineData("linux", "x64")]
    [InlineData("windows", "arm64")]
    public void ForeignPlatform_IsInvalid(string os, string architecture)
    {
        var fixture = CreateCompleteAddon();
        WriteManifest(fixture.Root, fixture.Sizes, os: os, architecture: architecture);

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.InvalidManifest, result.Status);
        Assert.Equal("os/architecture", result.Detail);
    }

    [Fact]
    public void ForeignPackIdentity_IsInvalid()
    {
        var fixture = CreateCompleteAddon();
        WriteManifest(fixture.Root, fixture.Sizes, packId: "gipformer-other");

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.InvalidManifest, result.Status);
        Assert.Equal("identity", result.Detail);
    }

    [Fact]
    public void ManifestWithoutFileTable_IsInvalid()
    {
        var root = Path.Combine(Path.GetTempPath(), "gipformer-addon-tests", Guid.NewGuid().ToString("N"));
        _roots.Add(root);
        Directory.CreateDirectory(root);
        File.WriteAllText(
            Path.Combine(root, GipformerEngine.ManifestFileName),
            "{\"formatVersion\":1,\"os\":\"windows\",\"architecture\":\"x64\",\"addonId\":\"gipformer-vi\",\"engineId\":\"sherpa-onnx\",\"packId\":\"gipformer1.5-vi\"}");

        var result = new GipformerEngine().CheckInstallation(root);

        Assert.Equal(GipformerInstallStatus.InvalidManifest, result.Status);
        Assert.Equal("files", result.Detail);
    }

    [Fact]
    public void UnsafeManifestPath_IsInvalid()
    {
        var fixture = CreateCompleteAddon();
        WriteManifest(fixture.Root, fixture.Sizes, extraFiles: new Dictionary<string, long> { ["../escaped.dll"] = 10 });

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.InvalidManifest, result.Status);
        Assert.Equal("../escaped.dll", result.Detail);
    }

    [Theory]
    [InlineData("pack/model/joiner.onnx")]
    [InlineData("pack/punct/vocab.txt")]
    [InlineData("pack/silero_vad.onnx")]
    [InlineData("runtime/caption-engine.exe")]
    public void MissingRequiredFile_IsIncomplete_AndNamesIt(string relative)
    {
        var fixture = CreateCompleteAddon();
        File.Delete(Path.Combine(fixture.Root, relative.Replace('/', Path.DirectorySeparatorChar)));

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.Incomplete, result.Status);
        Assert.Equal(relative, result.Detail);
    }

    [Fact]
    public void EmptyRequiredFile_IsIncomplete()
    {
        var fixture = CreateCompleteAddon();
        File.WriteAllBytes(Path.Combine(fixture.Root, "pack", "model", "tokens.txt"), Array.Empty<byte>());

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.Incomplete, result.Status);
        Assert.Equal("pack/model/tokens.txt", result.Detail);
    }

    [Fact]
    public void TruncatedFile_IsIncomplete()
    {
        var fixture = CreateCompleteAddon();
        var path = Path.Combine(fixture.Root, "pack", "model", "encoder.onnx");
        File.WriteAllBytes(path, new byte[10]);

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.Incomplete, result.Status);
        Assert.Equal("pack/model/encoder.onnx", result.Detail);
    }

    [Fact]
    public void FrozenRuntimeWithoutInternalLibraries_IsIncomplete()
    {
        var fixture = CreateCompleteAddon();
        Directory.Delete(Path.Combine(fixture.Root, "runtime", GipformerEngine.InternalFolderName), recursive: true);

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.Incomplete, result.Status);
        Assert.Equal("runtime/_internal", result.Detail);
    }

    [Fact]
    public void PackManifestWithoutVietnamese_IsInvalid()
    {
        var fixture = CreateCompleteAddon();
        var packManifestPath = Path.Combine(fixture.Root, "pack", "model.json");
        var content = Encoding.UTF8.GetBytes("{\"id\":\"gipformer1.5-vi\",\"engine\":\"sherpa-onnx\",\"languages\":[\"en\"]}");
        File.WriteAllBytes(packManifestPath, content);

        // Keep the size in step with the manifest so the completeness check does not mask the
        // language check.
        var sizes = new Dictionary<string, long>(fixture.Sizes) { ["pack/model.json"] = content.Length };
        WriteManifest(fixture.Root, sizes);

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.Equal(GipformerInstallStatus.InvalidManifest, result.Status);
        Assert.Equal("pack/model.json", result.Detail);
    }

    [Fact]
    public void CompleteAddon_IsReady()
    {
        var fixture = CreateCompleteAddon();

        var result = new GipformerEngine().CheckInstallation(fixture.Root);

        Assert.True(result.IsReady, result.Detail);
    }

    [Fact]
    public void EngineMetadata_IsVietnameseCpuOnlyAndNeverDownloaded()
    {
        var engine = new GipformerEngine();

        Assert.Equal(WhisperChoice.Gipformer, engine.Choice);
        Assert.Equal("Gipformer — Vietnamese", engine.Name);
        Assert.False(engine.CanBeDownloaded());
        Assert.False(engine.DownloadsOwnModels);
        Assert.False(engine.SupportsCustomModels);
        Assert.Equal(string.Empty, engine.Url);
        Assert.Equal(GipformerEngine.IsSupportedPlatform, OperatingSystem.IsWindows() && Environment.Is64BitProcess);

        var language = Assert.Single(engine.Languages);
        Assert.Equal("vi", language.Code);

        var model = Assert.Single(engine.Models);
        Assert.Equal(GipformerEngine.PackId, model.Name);
        Assert.True(model.TranscribeOnly);
    }

    [Fact]
    public void AddonRoot_IsUnderTheDataFolder()
    {
        var dataFolder = Path.Combine(Path.GetTempPath(), "data-" + Guid.NewGuid().ToString("N"));

        var root = new GipformerEngine().GetAddonRoot(dataFolder);

        Assert.Equal(Path.Combine(dataFolder, "SpeechToText", "Gipformer"), root);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("--vad off")]
    [InlineData("--threads 8")]
    [InlineData("--vad on --threads 2")]
    [InlineData("--vad=off --threads=4")]
    [InlineData("--threads \"6\"")]
    public void SupportedAdvancedParameters_AreAccepted(string? parameters)
    {
        Assert.True(GipformerEngine.TryParseAdvancedArguments(parameters, out _, out var error), error);
        Assert.Equal(string.Empty, error);
    }

    [Fact]
    public void SupportedAdvancedParameters_AreParsedWithoutQuotes()
    {
        Assert.True(GipformerEngine.TryParseAdvancedArguments("--threads \"6\" --vad off", out var arguments, out _));

        Assert.Equal(new[] { "--threads", "6", "--vad", "off" }, arguments);
    }

    [Theory]
    [InlineData("--device cpu", "--device")]
    [InlineData("--language vi", "--language")]
    [InlineData("--model-dir C:/other", "--model-dir")]
    [InlineData("--input other.wav", "--input")]
    [InlineData("--compute-type int8", "--compute-type")]
    [InlineData("--temperature 0.2", "--temperature")]
    [InlineData("positions.wav", "positions.wav")]
    [InlineData("--vad", "--vad")]
    [InlineData("--threads", "--threads")]
    [InlineData("--threads 0", "0")]
    [InlineData("--vad maybe", "maybe")]
    public void ReservedUnknownOrMalformedParameters_AreRejected(string parameters, string expected)
    {
        Assert.False(GipformerEngine.TryParseAdvancedArguments(parameters, out _, out var error));
        Assert.Equal(expected, error);
    }

    [Fact]
    public void UnterminatedQuote_IsRejected()
    {
        Assert.False(GipformerEngine.TryParseAdvancedArguments("--threads \"4", out _, out var error));
        Assert.Equal("unterminated quote", error);
    }

    [AvaloniaFact]
    public async Task HelpText_IsEmbeddedAndExplainsTheManualInstall()
    {
        var help = await new GipformerEngine().GetHelpText();

        Assert.Contains("Gipformer", help);
        Assert.Contains("[Data Folder]/SpeechToText/", help);
        Assert.Contains("addon.json", help);
        Assert.Contains("--threads", help);
    }
}
