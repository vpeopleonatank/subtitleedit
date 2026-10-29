using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using Nikse.SubtitleEdit.Core.Common;
using Nikse.SubtitleEdit.Features.Video.SpeechToText.Engines;

namespace Nikse.SubtitleEdit.Features.Video.SpeechToText;

/// <summary>How one Gipformer attempt ended. Only <see cref="Succeeded"/> may reach the editor.</summary>
public enum GipformerFinalizeStatus
{
    Succeeded,
    Failed,
    Cancelled,
}

/// <summary>
/// Parse/completion state for exactly one caption-engine attempt.
///
/// The sidecar writes UTF-8 newline-delimited JSON to <c>stdout</c> (<c>info</c>, <c>progress</c>,
/// <c>result</c>, <c>error</c>) and diagnostics to <c>stderr</c>; 100 % progress is not completion,
/// and an exit code of 0 without a result is a failure, not silence. A successful empty transcript
/// (a silent clip) is a real result with zero words.
///
/// One instance belongs to one <c>Process</c> and is replaced - never reused - for the next job, so
/// a late line from an old process cannot leak into the next clip.
/// </summary>
public sealed class GipformerTranscript
{
    private const int MaxDiagnosticChars = 4000;
    private const int MaxOffendingLineChars = 200;

    private readonly StringBuilder _stderr = new();
    private List<TimedWord> _words = new();

    /// <summary>Engine name from the <c>info</c> message (e.g. <c>sherpa-onnx</c>).</summary>
    public string Engine { get; private set; } = string.Empty;

    /// <summary>Device from the <c>info</c> message; the add-on only ever runs CPU.</summary>
    public string Device { get; private set; } = string.Empty;

    /// <summary>Media duration of the processed audio, from <c>info</c> or the final result.</summary>
    public double DurationSeconds { get; private set; }

    /// <summary>Language reported by the final result; must be <c>vi</c>.</summary>
    public string Language { get; private set; } = string.Empty;

    /// <summary>Last progress percentage reported, clamped to 0..100.</summary>
    public double ProgressPercent { get; private set; }

    public bool ReachedProgress100 { get; private set; }

    /// <summary>Explicit <c>{"type":"error"}</c> message from the engine, if any.</summary>
    public string? EngineErrorMessage { get; private set; }

    /// <summary>Malformed/duplicate protocol data; a protocol failure is never treated as success.</summary>
    public string? ProtocolError { get; private set; }

    public int ResultCount { get; private set; }

    public bool HasFailure => ProtocolError != null || EngineErrorMessage != null;

    /// <summary>Timed words of the single accepted result (empty for a silent clip).</summary>
    public IReadOnlyList<TimedWord> Words => _words;

    /// <summary>Captured stderr, capped; diagnostics only, never a result source.</summary>
    public string StandardError => _stderr.ToString();

    public void Reset()
    {
        _stderr.Clear();
        _words = new List<TimedWord>();
        Engine = string.Empty;
        Device = string.Empty;
        DurationSeconds = 0;
        Language = string.Empty;
        ProgressPercent = 0;
        ReachedProgress100 = false;
        EngineErrorMessage = null;
        ProtocolError = null;
        ResultCount = 0;
    }

    /// <summary>
    /// Feeds one stdout line. Never throws: every problem becomes <see cref="ProtocolError"/> so the
    /// run fails visibly instead of reporting a partial transcript as success.
    /// </summary>
    public void HandleStdOutLine(string? line)
    {
        if (line == null || line.Length == 0)
        {
            return;
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(line);
        }
        catch (JsonException)
        {
            SetProtocolError("malformed output line", line);
            return;
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("type", out var typeProperty) ||
                typeProperty.ValueKind != JsonValueKind.String)
            {
                SetProtocolError("message without a type", line);
                return;
            }

            switch (typeProperty.GetString())
            {
                case "info":
                    HandleInfo(root);
                    break;
                case "progress":
                    HandleProgress(root, line);
                    break;
                case "result":
                    HandleResult(root, line);
                    break;
                case "error":
                    HandleError(root, line);
                    break;
                default:
                    // A well-formed message from a newer sidecar is ignored, not a failure.
                    break;
            }
        }
    }

    /// <summary>
    /// Feeds one stderr line. Kept only for diagnostics: stderr can never create or modify a result,
    /// so JSON-looking text there has no effect.
    /// </summary>
    public void HandleStdErrLine(string? line)
    {
        if (string.IsNullOrWhiteSpace(line) || _stderr.Length >= MaxDiagnosticChars)
        {
            return;
        }

        if (_stderr.Length > 0)
        {
            _stderr.Append('\n');
        }

        _stderr.Append(line.Length > MaxDiagnosticChars ? line[..MaxDiagnosticChars] : line);
    }

    private void HandleInfo(JsonElement root)
    {
        if (!TryReadFiniteNumber(root, "duration", out var duration) || duration < 0)
        {
            SetProtocolError("info without a usable duration", root.GetRawText());
            return;
        }

        DurationSeconds = duration;
        if (root.TryGetProperty("engine", out var engine) && engine.ValueKind == JsonValueKind.String)
        {
            Engine = engine.GetString() ?? string.Empty;
        }

        if (root.TryGetProperty("device", out var device) && device.ValueKind == JsonValueKind.String)
        {
            Device = device.GetString() ?? string.Empty;
        }
    }

    private void HandleProgress(JsonElement root, string line)
    {
        if (!TryReadFiniteNumber(root, "percent", out var percent))
        {
            SetProtocolError("progress without a usable percent", line);
            return;
        }

        ProgressPercent = Math.Clamp(percent, 0, 100);
        if (ProgressPercent >= 100)
        {
            ReachedProgress100 = true;
        }
    }

    private void HandleError(JsonElement root, string line)
    {
        if (!root.TryGetProperty("message", out var message) ||
            message.ValueKind != JsonValueKind.String ||
            string.IsNullOrWhiteSpace(message.GetString()))
        {
            SetProtocolError("error without a message", line);
            return;
        }

        EngineErrorMessage ??= message.GetString()!.Trim();
    }

    private void HandleResult(JsonElement root, string line)
    {
        if (ResultCount > 0)
        {
            SetProtocolError("more than one final result", line);
            return;
        }

        if (!root.TryGetProperty("transcript", out var transcript) || transcript.ValueKind != JsonValueKind.Object)
        {
            SetProtocolError("result without a transcript", line);
            return;
        }

        var language = transcript.TryGetProperty("language", out var languageProperty) &&
                       languageProperty.ValueKind == JsonValueKind.String
            ? languageProperty.GetString()
            : null;
        if (language != GipformerEngine.LanguageCode)
        {
            SetProtocolError("result for an unsupported language", line);
            return;
        }

        if (!transcript.TryGetProperty("segments", out var segments) || segments.ValueKind != JsonValueKind.Array)
        {
            SetProtocolError("result without segments", line);
            return;
        }

        if (transcript.TryGetProperty("duration", out var durationProperty) &&
            durationProperty.ValueKind == JsonValueKind.Number &&
            durationProperty.TryGetDouble(out var duration) &&
            double.IsFinite(duration) &&
            duration >= 0)
        {
            DurationSeconds = duration;
        }

        var words = new List<TimedWord>();
        var previousStart = -1.0;
        foreach (var segment in segments.EnumerateArray())
        {
            if (segment.ValueKind != JsonValueKind.Object ||
                !segment.TryGetProperty("words", out var segmentWords) ||
                segmentWords.ValueKind != JsonValueKind.Array)
            {
                SetProtocolError("segment without words", line);
                return;
            }

            foreach (var word in segmentWords.EnumerateArray())
            {
                if (word.ValueKind != JsonValueKind.Object ||
                    !word.TryGetProperty("text", out var textProperty) ||
                    textProperty.ValueKind != JsonValueKind.String ||
                    string.IsNullOrWhiteSpace(textProperty.GetString()))
                {
                    SetProtocolError("word without text", line);
                    return;
                }

                if (!TryReadFiniteNumber(word, "start", out var start) ||
                    !TryReadFiniteNumber(word, "end", out var end) ||
                    start < 0 ||
                    end < start)
                {
                    SetProtocolError("word with unusable timing", line);
                    return;
                }

                if (start < previousStart)
                {
                    SetProtocolError("out-of-order word timing", line);
                    return;
                }

                previousStart = start;
                words.Add(new TimedWord(textProperty.GetString()!, start, end));
            }
        }

        _words = words;
        Language = language!;
        ResultCount = 1;
    }

    private static bool TryReadFiniteNumber(JsonElement element, string name, out double value)
    {
        value = 0;
        return element.TryGetProperty(name, out var property) &&
               property.ValueKind == JsonValueKind.Number &&
               property.TryGetDouble(out value) &&
               double.IsFinite(value);
    }

    private void SetProtocolError(string message, string offendingLine)
    {
        if (ProtocolError != null)
        {
            return;
        }

        var snippet = offendingLine.Length > MaxOffendingLineChars
            ? offendingLine[..MaxOffendingLineChars] + "…"
            : offendingLine;
        ProtocolError = $"{message}: {snippet}";
    }

    /// <summary>
    /// Single finalization point for one attempt. Call only after the process has exited and both
    /// redirected streams reached EOF; the outcome is a pure function of the collected state.
    ///
    /// Precedence: a cancelled/closed attempt discards whatever arrived; otherwise any protocol or
    /// engine error, then a nonzero/unknown exit code, then a missing result each fail; only
    /// exactly one valid result with a zero exit succeeds (an empty word list is silence, not a failure).
    /// </summary>
    public GipformerFinalizeStatus TryFinalize(int? exitCode, bool cancelled, out Subtitle? subtitle, out string? failure)
    {
        subtitle = null;
        failure = null;

        if (cancelled)
        {
            return GipformerFinalizeStatus.Cancelled;
        }

        if (ProtocolError != null)
        {
            failure = $"Unexpected engine output ({ProtocolError})";
            return GipformerFinalizeStatus.Failed;
        }

        if (EngineErrorMessage != null)
        {
            failure = EngineErrorMessage;
            return GipformerFinalizeStatus.Failed;
        }

        if (exitCode is not 0)
        {
            failure = exitCode.HasValue
                ? $"The engine exited with code {exitCode.Value} (0x{(uint)exitCode.Value:X8}) before reporting a result"
                : "The engine exit code could not be read";
            return GipformerFinalizeStatus.Failed;
        }

        if (ResultCount == 0)
        {
            failure = "The engine exited successfully but reported no result";
            return GipformerFinalizeStatus.Failed;
        }

        subtitle = BuildSubtitle();
        return GipformerFinalizeStatus.Succeeded;
    }

    /// <summary>
    /// Builds cues from the accepted timed words with the shared segmenter; may be empty (silence).
    /// Timings stay relative to the given audio - clip offsets are added by the caller once.
    /// </summary>
    public Subtitle BuildSubtitle(int maxCharsLatin = TimedWordSegmenter.DefaultMaxCharsLatin)
    {
        return TimedWordSegmenter.BuildSubtitle(_words, maxCharsLatin, TimedWordSegmenter.DefaultMaxCharsCjk);
    }
}
