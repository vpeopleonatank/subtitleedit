using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.LogicalTree;
using Nikse.SubtitleEdit.Features.Video.SpeechToText;
using Nikse.SubtitleEdit.Features.Video.SpeechToText.Engines;
using Nikse.SubtitleEdit.Logic;
using Nikse.SubtitleEdit.Logic.Config;
using Nikse.SubtitleEdit.Logic.Media;
using Nikse.SubtitleEdit.UiLogic.AudioToText;

namespace UITests.Features.Video.SpeechToText;

/// <summary>
/// Gipformer is Vietnamese-only and manual-install only, so the engine row has to hide what it
/// cannot do (translation, model download, website) without disturbing the other engines: the
/// saved choice, model and advanced parameters survive a round trip through it.
/// </summary>
public class SpeechToTextGipformerSelectionTests : IDisposable
{
    private sealed class NullServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }

    private readonly SettingsScope _scope;

    public SpeechToTextGipformerSelectionTests()
    {
        _scope = new SettingsScope(
            "Tools.AudioToText.WhisperChoice",
            "Tools.AudioToText.WhisperModel",
            "Tools.AudioToText.WhisperLanguageCode",
            "Tools.AudioToText.CommandLineParameterGipformer",
            "Tools.AudioToText.CommandLineParameterCpp");
    }

    public void Dispose() => _scope.Dispose();

    private static SpeechToTextViewModel CreateViewModel() =>
        new(new WindowService(new NullServiceProvider()), new FileHelper(), new FolderHelper());

    /// <summary>
    /// The window binds the combo box's SelectionChanged to <see cref="SpeechToTextViewModel.OnEngineChanged"/>;
    /// setting the property alone does not save or rebuild anything, so tests go through both.
    /// </summary>
    private static void Select(SpeechToTextViewModel vm, ISpeechToTextEngine engine)
    {
        vm.SelectedEngine = engine;
        vm.OnEngineChanged(vm, null!);
    }

    [AvaloniaFact]
    public void SelectingGipformer_PinsVietnameseAndHidesUnsupportedActions()
    {
        var vm = CreateViewModel();
        vm.DoTranslateToEnglish = true;
        vm.SelectedLanguage = vm.Languages.First(l => l.Code != GipformerEngine.LanguageCode);

        Select(vm, vm.Engines.OfType<GipformerEngine>().Single());

        Assert.Equal(WhisperChoice.Gipformer, Se.Settings.Tools.AudioToText.WhisperChoice);
        var language = Assert.Single(vm.Languages);
        Assert.Equal(GipformerEngine.LanguageCode, language.Code);
        Assert.Equal(GipformerEngine.LanguageCode, vm.SelectedLanguage?.Code);

        Assert.False(vm.IsTranslateVisible);
        Assert.False(vm.DoTranslateToEnglish);
        Assert.False(vm.IsModelDownloadVisible);
        Assert.False(vm.IsEngineDownloadButtonVisible);
        Assert.False(vm.IsEngineSettingsButtonVisible);
        Assert.False(vm.IsEngineWebsiteButtonVisible);
        Assert.True(vm.IsModelSelectionVisible);
        Assert.True(vm.IsLanguageSelectionVisible);

        var model = Assert.Single(vm.Models);
        Assert.Equal(GipformerEngine.PackId, model.Model.Name);
    }

    [AvaloniaFact]
    public void SelectingGipformer_StaysSelectableAfterARestart()
    {
        var vm = CreateViewModel();
        Select(vm, vm.Engines.OfType<GipformerEngine>().Single());

        var reopened = CreateViewModel();

        Assert.IsType<GipformerEngine>(reopened.SelectedEngine);
        Assert.Equal(GipformerEngine.LanguageCode, reopened.SelectedLanguage?.Code);
    }

    [AvaloniaFact]
    public void SwitchingAwayAndBack_KeepsPerEngineParametersAndRestoresCapabilities()
    {
        var vm = CreateViewModel();
        var whisperCpp = vm.Engines.OfType<WhisperCppEngine>().Single();
        var gipformer = vm.Engines.OfType<GipformerEngine>().Single();

        // The advanced-settings dialog writes SelectedEngine.CommandLineParameter itself; the
        // main window only mirrors the active engine's value.
        Select(vm, whisperCpp);
        vm.Parameters = "--custom-whisper-flag";
        whisperCpp.CommandLineParameter = vm.Parameters;

        Select(vm, gipformer);
        Assert.Equal(string.Empty, vm.Parameters);
        vm.Parameters = "--vad off --threads 4";
        gipformer.CommandLineParameter = vm.Parameters;

        Select(vm, whisperCpp);

        Assert.Equal("--custom-whisper-flag", vm.Parameters);
        Assert.True(vm.IsTranslateVisible);
        Assert.True(vm.IsModelDownloadVisible);
        Assert.True(vm.Languages.Count > 1);

        Select(vm, gipformer);

        Assert.Equal("--vad off --threads 4", vm.Parameters);
        Assert.Equal("--vad off --threads 4", Se.Settings.Tools.AudioToText.CommandLineParameterGipformer);
        Assert.Equal("--custom-whisper-flag", Se.Settings.Tools.AudioToText.CommandLineParameterCpp);
    }

    [AvaloniaFact]
    public void Window_ShowsTheInstallHintAndHidesTheWebsiteButton()
    {
        var vm = CreateViewModel();
        var gipformer = vm.Engines.OfType<GipformerEngine>().Single();
        if (gipformer.CheckInstallation().IsReady)
        {
            return;
        }

        var window = new SpeechToTextWindow(vm);
        try
        {
            Select(vm, gipformer);
            window.Show();
            Avalonia.Threading.Dispatcher.UIThread.RunJobs();

            var hint = window.GetLogicalDescendants()
                .OfType<TextBlock>()
                .Single(t => t.Text == vm.EngineLocalInstallHint);
            Assert.True(hint.IsVisible);
            Assert.Contains("SpeechToText", hint.Text!);

            var buttons = window.GetLogicalDescendants().OfType<Button>().Where(b => b.Command is not null).ToList();
            Assert.DoesNotContain(buttons, b => b.Command == vm.ShowWebLinkCommand && b.IsVisible);
        }
        finally
        {
            window.Close();
        }
    }

    [AvaloniaFact]
    public void EngineStatus_WithoutAnAddon_ShowsTheExtractionFolder()
    {
        var vm = CreateViewModel();
        var gipformer = vm.Engines.OfType<GipformerEngine>().Single();

        // The test host has no Gipformer add-on in its data folder. Guard against a developer
        // machine that does, so the assertion stays about the message, not the machine.
        if (gipformer.CheckInstallation().IsReady)
        {
            return;
        }

        Select(vm, gipformer);

        Assert.True(vm.IsEngineLocalInstallHintVisible);
        Assert.Contains(gipformer.GetAddonRoot(), vm.EngineLocalInstallHint);
        Assert.Contains("Gipformer", vm.EngineLocalInstallHint);
    }
}
