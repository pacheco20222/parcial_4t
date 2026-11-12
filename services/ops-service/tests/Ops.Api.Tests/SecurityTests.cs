using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.Options;
using System.Net;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.IdentityModel.Tokens;
using Ops.Api.Auth;
using Ops.Api.Domain;

namespace Ops.Api.Tests;

public class SecurityTests
{
    [Theory]
    [InlineData(null, "172.30.30.10")]
    [InlineData("172.30.30.11", "172.30.30.11")]
    public async Task OnlyConfiguredGatewayCanForwardHeaders(string? configured, string expected)
    {
        await using var factory = new ApiFactory();
        await using var host = factory.WithWebHostBuilder(builder =>
        {
            if (configured != null) builder.UseSetting("Gateway:Ip", configured);
        });
        var options = host.Services.GetRequiredService<IOptions<ForwardedHeadersOptions>>();
        Assert.Empty(options.Value.KnownIPNetworks);
        Assert.Equal(IPAddress.Parse(expected), Assert.Single(options.Value.KnownProxies));
        foreach (var remote in new[] { expected, "172.30.30.99" })
        {
            var context = new DefaultHttpContext();
            context.Connection.RemoteIpAddress = IPAddress.Parse(remote);
            context.Request.Headers["X-Forwarded-For"] = "198.51.100.7";
            context.Request.Headers["X-Forwarded-Proto"] = "https";
            await new ForwardedHeadersMiddleware(_ => Task.CompletedTask,
                host.Services.GetRequiredService<ILoggerFactory>(), options).Invoke(context);
            Assert.Equal(remote == expected ? "198.51.100.7" : remote, context.Connection.RemoteIpAddress!.ToString());
            Assert.Equal(remote == expected ? "https" : "", context.Request.Scheme);
        }
    }
    public static JwtTokens Keys()
    {
        using var rsa = RSA.Create(2048); return new JwtTokens(rsa.ExportPkcs8PrivateKeyPem(), rsa.ExportSubjectPublicKeyInfoPem());
    }
    [Fact]
    public void JwtHasContractClaimsAndRs256Signature()
    {
        using var keys = Keys(); var user = new AppUser { Id = Guid.NewGuid(), Email = "operator@flood.local" };
        var token = keys.Issue(user, ["Operator"], "pwd");
        var principal = new JwtSecurityTokenHandler { MapInboundClaims = false }.ValidateToken(token, keys.Validation(), out var validated);
        Assert.Equal("RS256", ((JwtSecurityToken)validated).Header.Alg); Assert.True(principal.IsInRole("Operator"));
        Assert.Equal(user.Id.ToString(), principal.FindFirst("sub")!.Value); Assert.Equal("pwd", principal.FindFirst("amr")!.Value);
        Assert.InRange((validated.ValidTo - DateTime.UtcNow).TotalMinutes, 14.9, 15.1);
    }
    [Fact]
    public void PendingTokenCannotAuthorizeApi()
    {
        using var keys = Keys(); var raw = keys.Issue(new AppUser { Id = Guid.NewGuid(), Email = "a@b.local" }, ["Admin"], "pwd", true);
        Assert.Throws<SecurityTokenInvalidAudienceException>(() => new JwtSecurityTokenHandler().ValidateToken(raw, keys.Validation(), out _));
        Assert.False(keys.ValidatePending(raw).IsInRole("Admin"));
    }
    [Fact]
    public void OtherSigningKeyRejected()
    {
        using var keys = Keys(); using var other = Keys();
        var raw = keys.Issue(new AppUser { Email = "a@b.local" }, ["Admin"], "mfa");
        Assert.ThrowsAny<SecurityTokenException>(() => new JwtSecurityTokenHandler().ValidateToken(raw, other.Validation(), out _));
    }
    [Theory]
    [InlineData("Operator", "Operator", false, "pwd", true)] [InlineData("Operator", "Supervisor", false, "pwd", false)]
    [InlineData("Supervisor", "Operator", false, "pwd", true)] [InlineData("Admin", "Supervisor", false, "pwd", true)]
    [InlineData("Admin", "Operator", true, "pwd", false)] [InlineData("Admin", "Admin", true, "mfa", true)]
    [InlineData("Supervisor", "Supervisor", true, "pwd", false)] [InlineData("Operator", "Operator", true, "pwd", true)]
    public void HierarchyAndMfa(string role, string policy, bool enforce, string amr, bool expected)
    {
        var principal = new ClaimsPrincipal(new ClaimsIdentity([new Claim("role", role), new Claim("amr", amr)], "test", "sub", "role"));
        Assert.Equal(expected, Roles.Allows(principal, policy, enforce));
    }
    [Theory]
    [InlineData("POST", false, 403)] [InlineData("PATCH", false, 403)] [InlineData("PUT", false, 403)]
    [InlineData("DELETE", false, 403)] [InlineData("POST", true, 204)] [InlineData("GET", false, 204)]
    public async Task CsrfEnforced(string method, bool header, int status)
    {
        using var services = new ServiceCollection().AddLogging().AddProblemDetails().BuildServiceProvider();
        var http = new DefaultHttpContext { RequestServices = services }; http.Response.Body = new MemoryStream(); http.Request.Method = method;
        if (header) http.Request.Headers["X-Requested-With"] = "XMLHttpRequest";
        await new CsrfMiddleware(c => { c.Response.StatusCode = 204; return Task.CompletedTask; }).InvokeAsync(http, services.GetRequiredService<ILogger<CsrfMiddleware>>());
        Assert.Equal(status, http.Response.StatusCode);
    }
}
