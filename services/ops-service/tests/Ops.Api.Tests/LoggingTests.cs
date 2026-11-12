using System.Text.Json;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Ops.Api.Auth;

namespace Ops.Api.Tests;

public class LoggingTests
{
    [Fact]
    public void FrameworkMessageAndExceptionAreRendered()
    {
        Exception error;
        try { throw new InvalidOperationException("Library failure", new ArgumentException("Invalid input")); }
        catch (InvalidOperationException ex) { error = ex; }
        var entry = new LogEntry<string>(LogLevel.Error, "Library", new EventId(1), "request 42 failed", error,
            (state, _) => state);
        using var writer = new StringWriter();
        new FloodFormatter().Write(entry, null, writer);
        using var document = JsonDocument.Parse(writer.ToString());
        var root = document.RootElement;
        Assert.Equal("request 42 failed", root.GetProperty("msg").GetString());
        Assert.Equal("service.log", root.GetProperty("event").GetString());
        Assert.Equal("Library", root.GetProperty("category").GetString());
        var exc = root.GetProperty("exc");
        Assert.Equal("InvalidOperationException", exc.GetProperty("type").GetString());
        Assert.Equal("Library failure", exc.GetProperty("message").GetString());
        Assert.Contains("Invalid input", exc.GetProperty("traceback").GetString());
        Assert.Contains(nameof(FrameworkMessageAndExceptionAreRendered), exc.GetProperty("traceback").GetString());
    }
    [Fact]
    public void StructuredContextAndEventArePreserved()
    {
        var state = new List<KeyValuePair<string, object?>>
        {
            new("event", "stream.event_processed"), new("point_id", "P01"), new("password", "must-be-omitted")
        };
        var entry = new LogEntry<List<KeyValuePair<string, object?>>>(LogLevel.Information, "Ops", new EventId(),
            state, null, (_, _) => "stream.event_processed P01");
        using var writer = new StringWriter();
        new FloodFormatter().Write(entry, null, writer);
        using var document = JsonDocument.Parse(writer.ToString());
        var root = document.RootElement;
        Assert.Equal("stream.event_processed", root.GetProperty("event").GetString());
        Assert.Equal("P01", root.GetProperty("point_id").GetString());
        Assert.Equal("stream.event_processed P01", root.GetProperty("msg").GetString());
        Assert.False(root.TryGetProperty("exc", out _));
        Assert.DoesNotContain("must-be-omitted", writer.ToString());
    }
}
