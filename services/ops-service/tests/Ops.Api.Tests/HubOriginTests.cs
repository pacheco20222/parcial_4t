using Microsoft.AspNetCore.Http;
using Ops.Api.Realtime;

namespace Ops.Api.Tests;

public class HubOriginTests
{
    [Theory]
    [InlineData("/hubs/live", null, true)]
    [InlineData("/hubs/live", "https://localhost:8443", true)]
    [InlineData("/hubs/live/negotiate", "https://LOCALHOST:8443", true)]
    [InlineData("/hubs/live", "https://attacker.local:8443", false)]
    [InlineData("/hubs/live/negotiate", "https://attacker.local:8443", false)]
    [InlineData("/hubs/live", "http://localhost:8443", false)]
    [InlineData("/hubs/live", "https://localhost", false)]
    [InlineData("/hubs/live", "null", false)]
    [InlineData("/hubs/live", "", false)]
    [InlineData("/hubs/live", "https://localhost:8443/path", false)]
    [InlineData("/hubs/live", "https://user@localhost:8443", false)]
    [InlineData("/hubs/live", "https://localhost:8443?x=1", false)]
    [InlineData("/hubs/live", "https://localhost:8443#x", false)]
    [InlineData("/healthz", "https://attacker.local", true)]
    public async Task EnforcesSameOriginForAllHubTransports(string path, string? origin, bool allowed)
    {
        var context = new DefaultHttpContext();
        context.Request.Scheme = "https"; context.Request.Host = new HostString("localhost", 8443);
        context.Request.Path = path;
        if (origin != null) context.Request.Headers.Origin = origin;
        var called = false;
        var middleware = new HubOriginMiddleware(_ => { called = true; return Task.CompletedTask; });
        await middleware.InvokeAsync(context);
        Assert.Equal(allowed, called);
        Assert.Equal(allowed ? 200 : 403, context.Response.StatusCode);
    }
    [Fact]
    public async Task RejectsMultipleOrigins()
    {
        var context = new DefaultHttpContext(); context.Request.Path = "/hubs/live";
        context.Request.Scheme = "https"; context.Request.Host = new HostString("localhost");
        context.Request.Headers.Origin = new[] { "https://localhost", "https://attacker.local" };
        await new HubOriginMiddleware(_ => throw new Exception("Must reject")).InvokeAsync(context);
        Assert.Equal(403, context.Response.StatusCode);
    }
    [Fact]
    public async Task AcceptsExplicitDefaultPort()
    {
        var context = new DefaultHttpContext(); context.Request.Path = "/hubs/live";
        context.Request.Scheme = "https"; context.Request.Host = new HostString("localhost");
        context.Request.Headers.Origin = "https://localhost:443";
        var called = false;
        await new HubOriginMiddleware(_ => { called = true; return Task.CompletedTask; }).InvokeAsync(context);
        Assert.True(called);
    }
}
