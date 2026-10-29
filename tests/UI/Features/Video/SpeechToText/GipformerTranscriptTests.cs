using System.Text.Json;
using Nikse.SubtitleEdit.Core.Common;
using Nikse.SubtitleEdit.Features.Video.SpeechToText;
using Nikse.SubtitleEdit.Features.Video.SpeechToText.Engines;

namespace UITests.Features.Video.SpeechToText;

/// <summary>
/// The caption-engine JSON-lines protocol, as a pure state machine: one attempt is one instance,
/// 100 % progress is not completion, an error/crash/malformed line is never "no speech", and a
/// valid empty result is silence rather than failure.
/// </summary>
public class GipformerTranscriptTests
{
    private static string InfoLine(double duration) =>
        JsonSerializer.Serialize(new { type = "info", engine = "sherpa-onnx", device = "cpu", duration, sampleRate = 16000 });

    private static string ProgressLine(double percent) => JsonSerializer.Serialize(new { type = "progress", percent });

    private static string ErrorLine(string message) => JsonSerializer.Serialize(new { type = "error", message });

    private static string ResultLine(double duration, params (string Text, double Start, double End)[] words)
    {
        var segments = new[]
        {
            new
            {
                start = 0.0,
                end = duration,
                words = words.Select(word => new { text = word.Text, start = word.Start, end = word.End, p = 0.93 }).ToArray(),
            },
        };

        return JsonSerializer.Serialize(new { type = "result", transcript = new { language = "vi", duration, segments } });
    }

    private static GipformerTranscript Transcript(params string[] lines)
    {
        var transcript = new GipformerTranscript();
        foreach (var line in lines)
        {
            transcript.HandleStdOutLine(line);
        }

        return transcript;
    }

    private static readonly (string, double, double)[] VietnameseSpeech =
    {
        ("Xin", 0.00, 0.30),
        ("chào,", 0.30, 0.70),
        ("tôi", 0.80, 1.00),
        ("tên", 1.00, 1.20),
        ("là", 1.20, 1.30),
        ("Nam.", 1.30, 1.80),
    };

    [Fact]
    public void FullRun_ZeroExitAndOneResult_BuildsCuesFromRealTimedWords()
    {
        var transcript = Transcript(InfoLine(3.0), ProgressLine(12.5), ProgressLine(99.9), ResultLine(3.0, VietnameseSpeech));

        Assert.Equal(99.9, transcript.ProgressPercent, 3);
        Assert.Equal("sherpa-onnx", transcript.Engine);
        Assert.Equal("cpu", transcript.Device);
        Assert.Equal("vi", transcript.Language);

        var status = transcript.TryFinalize(0, cancelled: false, out var subtitle, out var failure);

        Assert.Equal(GipformerFinalizeStatus.Succeeded, status);
        Assert.Null(failure);
        Assert.NotNull(subtitle);
        var cue = Assert.Single(subtitle!.Paragraphs);
        Assert.Equal("Xin chào, tôi tên là Nam.", cue.Text);
        Assert.Equal(0, cue.StartTime.TotalMilliseconds);
        Assert.Equal(1800, cue.EndTime.TotalMilliseconds);
    }

    [Fact]
    public void Progress100_IsNotCompletion()
    {
        var transcript = Transcript(InfoLine(1.0), ProgressLine(100));

        Assert.True(transcript.ReachedProgress100);

        var status = transcript.TryFinalize(0, cancelled: false, out var subtitle, out var failure);

        Assert.Equal(GipformerFinalizeStatus.Failed, status);
        Assert.Null(subtitle);
        Assert.Contains("no result", failure);
    }

    [Fact]
    public void Progress_IsClamped()
    {
        var transcript = Transcript(ProgressLine(140));

        Assert.Equal(100, transcript.ProgressPercent);
        Assert.True(transcript.ReachedProgress100);
    }

    [Fact]
    public void EmptyResult_IsSilence_NotFailure()
    {
        var transcript = Transcript(InfoLine(2.0), ResultLine(2.0));

        var status = transcript.TryFinalize(0, cancelled: false, out var subtitle, out var failure);

        Assert.Equal(GipformerFinalizeStatus.Succeeded, status);
        Assert.Null(failure);
        Assert.NotNull(subtitle);
        Assert.Empty(subtitle!.Paragraphs);
    }

    [Fact]
    public void ErrorMessage_FailsEvenWithAValidResult()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech), ErrorLine("model load failed"));

        var status = transcript.TryFinalize(0, cancelled: false, out var subtitle, out var failure);

        Assert.Equal(GipformerFinalizeStatus.Failed, status);
        Assert.Null(subtitle);
        Assert.Equal("model load failed", failure);
    }

    [Fact]
    public void NonZeroExit_FailsEvenWithAValidResult()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech));

        var status = transcript.TryFinalize(3, cancelled: false, out var subtitle, out var failure);

        Assert.Equal(GipformerFinalizeStatus.Failed, status);
        Assert.Null(subtitle);
        Assert.Contains("code 3", failure);
    }

    [Fact]
    public void UnreadableExitCode_Fails()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech));

        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(null, cancelled: false, out _, out var failure));
        Assert.Contains("exit code", failure);
    }

    [Fact]
    public void Cancelled_DiscardsWhateverArrived()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech));

        var status = transcript.TryFinalize(0, cancelled: true, out var subtitle, out var failure);

        Assert.Equal(GipformerFinalizeStatus.Cancelled, status);
        Assert.Null(subtitle);
        Assert.Null(failure);
    }

    [Fact]
    public void MalformedLine_IsAProtocolFailure()
    {
        var transcript = Transcript("{\"type\":\"result\",\"transcript\":");

        Assert.NotNull(transcript.ProtocolError);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out var subtitle, out _));
        Assert.Null(subtitle);
    }

    [Fact]
    public void SecondResult_IsAProtocolFailure()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech), ResultLine(3.0, VietnameseSpeech));

        Assert.Contains("more than one", transcript.ProtocolError);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out _, out _));
    }

    [Fact]
    public void ErrorWithoutMessage_IsAProtocolFailure()
    {
        var transcript = Transcript("{\"type\":\"error\"}");

        Assert.NotNull(transcript.ProtocolError);
    }

    [Fact]
    public void MessageWithoutType_IsAProtocolFailure()
    {
        var transcript = Transcript("{\"percent\":50}");

        Assert.NotNull(transcript.ProtocolError);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out _, out _));
    }

    [Fact]
    public void UnknownMessageType_IsIgnored()
    {
        var transcript = Transcript("{\"type\":\"warning\",\"message\":\"spinning up\"}", ResultLine(3.0, VietnameseSpeech));

        Assert.Null(transcript.ProtocolError);
        Assert.Equal(GipformerFinalizeStatus.Succeeded, transcript.TryFinalize(0, cancelled: false, out _, out _));
    }

    [Fact]
    public void ResultWithoutVietnamese_IsRejected()
    {
        var transcript = Transcript("{\"type\":\"result\",\"transcript\":{\"language\":\"en\",\"segments\":[]}}");

        Assert.NotNull(transcript.ProtocolError);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out _, out _));
    }

    [Theory]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\",\"segments\":[{\"words\":[{\"text\":\"a\",\"start\":-1,\"end\":1}]}]}}")]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\",\"segments\":[{\"words\":[{\"text\":\"a\",\"start\":2,\"end\":1}]}]}}")]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\",\"segments\":[{\"words\":[{\"text\":\"a\",\"start\":3,\"end\":4},{\"text\":\"b\",\"start\":1,\"end\":2}]}]}}")]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\",\"segments\":[{\"words\":[{\"text\":\" \",\"start\":0,\"end\":1}]}]}}")]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\",\"segments\":[{\"words\":[{\"start\":0,\"end\":1}]}]}}")]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\",\"segments\":[{\"noWords\":[]}]}}")]
    [InlineData("{\"type\":\"result\",\"transcript\":{\"language\":\"vi\"}}")]
    [InlineData("{\"type\":\"result\"}")]
    [InlineData("{\"type\":\"progress\"}")]
    [InlineData("{\"type\":\"info\",\"duration\":-2}")]
    public void UnusablePayload_IsAProtocolFailure(string line)
    {
        var transcript = Transcript(line);

        Assert.NotNull(transcript.ProtocolError);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out var subtitle, out _));
        Assert.Null(subtitle);
    }

    [Fact]
    public void Stderr_NeverCreatesAResult()
    {
        var transcript = new GipformerTranscript();
        transcript.HandleStdErrLine(ResultLine(3.0, VietnameseSpeech));
        transcript.HandleStdErrLine("Traceback (most recent call last):");

        Assert.Equal(0, transcript.ResultCount);
        Assert.Empty(transcript.Words);
        Assert.Contains("Traceback", transcript.StandardError);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out _, out _));
    }

    [Fact]
    public void Stderr_IsCapped()
    {
        var transcript = new GipformerTranscript();
        for (var i = 0; i < 2000; i++)
        {
            transcript.HandleStdErrLine(new string('x', 100));
        }

        Assert.InRange(transcript.StandardError.Length, 4000, 4100);
    }

    [Fact]
    public void Reset_ClearsAPreviousAttempt()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech), ProgressLine(100));
        transcript.HandleStdErrLine("old diagnostic");

        transcript.Reset();

        Assert.Equal(0, transcript.ResultCount);
        Assert.Empty(transcript.Words);
        Assert.Empty(transcript.StandardError);
        Assert.False(transcript.ReachedProgress100);
        Assert.Equal(GipformerFinalizeStatus.Failed, transcript.TryFinalize(0, cancelled: false, out _, out _));
    }

    [Fact]
    public void Words_KeepProtocolOrderAndTiming()
    {
        var transcript = Transcript(ResultLine(3.0, VietnameseSpeech));

        Assert.Equal(6, transcript.Words.Count);
        Assert.Equal("Xin", transcript.Words[0].Word);
        Assert.Equal(0.30, transcript.Words[0].EndSeconds, 3);
        Assert.Equal("Nam.", transcript.Words[5].Word);
        Assert.Equal(1.80, transcript.Words[5].EndSeconds, 3);
    }

    [Fact]
    public void LongWords_SplitAtTheLengthCap_AndStayOrdered()
    {
        var words = Enumerable.Range(0, 40)
            .Select(i => ($"từ{i}", i * 0.25, i * 0.25 + 0.24))
            .ToArray();
        var transcript = Transcript(ResultLine(10.0, words));

        Assert.Equal(GipformerFinalizeStatus.Succeeded, transcript.TryFinalize(0, cancelled: false, out var subtitle, out _));

        var paragraphs = subtitle!.Paragraphs;
        Assert.True(paragraphs.Count > 1);
        foreach (var paragraph in paragraphs)
        {
            Assert.True(paragraph.Text.Length <= TimedWordSegmenter.DefaultMaxCharsLatin, paragraph.Text);
            Assert.True(paragraph.EndTime.TotalMilliseconds >= paragraph.StartTime.TotalMilliseconds);
            Assert.DoesNotContain("  ", paragraph.Text);
        }

        for (var i = 1; i < paragraphs.Count; i++)
        {
            Assert.True(paragraphs[i].StartTime.TotalMilliseconds >= paragraphs[i - 1].EndTime.TotalMilliseconds);
        }
    }
}
