using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Ops.Api.Data;
using Ops.Api.Auth;
using Ops.Api.Domain;

namespace Ops.Api.Tests;

public class AuthFlowTests
{
    private static async Task<(AppUser User, string Password)> Seed(ApiFactory factory)
    {
        using var scope = factory.Services.CreateScope();
        var manager = scope.ServiceProvider.GetRequiredService<UserManager<AppUser>>();
        var roles = scope.ServiceProvider.GetRequiredService<RoleManager<IdentityRole<Guid>>>();
        await roles.CreateAsync(new IdentityRole<Guid>("Supervisor"));
        var user = new AppUser { Id = Guid.NewGuid(), Email = "supervisor@flood.local", UserName = "supervisor@flood.local" };
        var password = "Aa1!" + Guid.NewGuid().ToString("N");
        Assert.True((await manager.CreateAsync(user, password)).Succeeded);
        Assert.True((await manager.AddToRoleAsync(user, "Supervisor")).Succeeded);
        return (user, password);
    }
    private static string Cookie(HttpResponseMessage response, string name) => response.Headers.GetValues("Set-Cookie")
        .Single(c => c.StartsWith(name + "=", StringComparison.Ordinal)).Split(';')[0];
    private static void Cookies(HttpClient client, params string[] cookies)
    { client.DefaultRequestHeaders.Remove("Cookie"); if (cookies.Length > 0) client.DefaultRequestHeaders.Add("Cookie", string.Join("; ", cookies)); }
    [Fact]
    public async Task LoginRefreshReuseRevokesFamily()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client(); var (user, password) = await Seed(factory);
        var login = await client.PostAsJsonAsync("/auth/login", new { user.Email, password }); Assert.Equal(HttpStatusCode.OK, login.StatusCode);
        var old = Cookie(login, "flood_rt"); Cookies(client, old);
        var refreshed = await client.PostAsync("/auth/refresh", null); Assert.Equal(HttpStatusCode.OK, refreshed.StatusCode);
        var next = Cookie(refreshed, "flood_rt"); Assert.NotEqual(old, next);
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<OpsDb>();
            Assert.Equal(2, await db.RefreshTokens.CountAsync());
            Assert.DoesNotContain(old.Split('=')[1], (await db.RefreshTokens.ToListAsync()).Select(x => x.Hash));
        }
        Cookies(client, old); Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsync("/auth/refresh", null)).StatusCode);
        Cookies(client, next); Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsync("/auth/refresh", null)).StatusCode);
        foreach (var cookie in login.Headers.GetValues("Set-Cookie"))
        { Assert.Contains("secure", cookie, StringComparison.OrdinalIgnoreCase); Assert.Contains("httponly", cookie, StringComparison.OrdinalIgnoreCase); Assert.Contains("samesite=strict", cookie, StringComparison.OrdinalIgnoreCase); }
    }
    [Fact]
    public async Task FiveFailuresLockAccountForFifteenMinutes()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client(); var (user, password) = await Seed(factory);
        for (var i = 0; i < 5; i++)
            Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsJsonAsync("/auth/login", new { user.Email, password = "incorrect" })).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsJsonAsync("/auth/login", new { user.Email, password })).StatusCode);
        using var scope = factory.Services.CreateScope(); var stored = await scope.ServiceProvider.GetRequiredService<UserManager<AppUser>>().FindByIdAsync(user.Id.ToString());
        Assert.InRange((stored!.LockoutEnd!.Value - DateTimeOffset.UtcNow).TotalMinutes, 14, 15);
    }
    [Fact]
    public async Task LogoutRevokesRefreshAndMeReadsCookie()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client(); var (user, password) = await Seed(factory);
        var login = await client.PostAsJsonAsync("/auth/login", new { user.Email, password });
        var refresh = Cookie(login, "flood_rt"); Cookies(client, Cookie(login, "flood_at"), refresh);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/auth/me")).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await client.PostAsync("/auth/logout", null)).StatusCode);
        Cookies(client, refresh); Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsync("/auth/refresh", null)).StatusCode);
    }
    [Fact]
    public async Task MfaSetupEnableAndPendingLogin()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client(); var (user, password) = await Seed(factory);
        var login = await client.PostAsJsonAsync("/auth/login", new { user.Email, password }); Cookies(client, Cookie(login, "flood_at"));
        var setup = await client.PostAsync("/auth/mfa/setup", null); Assert.Equal(HttpStatusCode.OK, setup.StatusCode);
        var uri = (await setup.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("otpauthUri").GetString()!;
        var secret = uri.Split("secret=")[1].Split('&')[0]; var code = Totp(secret);
        Assert.Equal(HttpStatusCode.OK, (await client.PostAsJsonAsync("/auth/mfa/enable", new { code })).StatusCode);
        Cookies(client); var pending = await client.PostAsJsonAsync("/auth/login", new { user.Email, password });
        Assert.True((await pending.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("mfaRequired").GetBoolean());
        Assert.DoesNotContain(pending.Headers.GetValues("Set-Cookie"), c => c.StartsWith("flood_at="));
        Cookies(client, Cookie(pending, "flood_mfa"));
        var complete = await client.PostAsJsonAsync("/auth/mfa/verify", new { code = Totp(secret) }); Assert.Equal(HttpStatusCode.OK, complete.StatusCode);
        var jwt = new System.IdentityModel.Tokens.Jwt.JwtSecurityTokenHandler().ReadJwtToken(Cookie(complete, "flood_at")[9..]);
        Assert.Contains(jwt.Claims, c => c.Type == "amr" && c.Value == "mfa");
    }
    [Fact]
    public async Task PasswordLoginCannotResetMfaAttemptLimit()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client();
        var (user, password) = await Seed(factory);
        string secret;
        using (var scope = factory.Services.CreateScope())
        {
            var users = scope.ServiceProvider.GetRequiredService<UserManager<AppUser>>();
            var stored = (await users.FindByIdAsync(user.Id.ToString()))!;
            Assert.True((await users.ResetAuthenticatorKeyAsync(stored)).Succeeded);
            secret = (await users.GetAuthenticatorKeyAsync(stored))!;
            Assert.True((await users.SetTwoFactorEnabledAsync(stored, true)).Succeeded);
        }
        for (var i = 0; i < 5; i++)
        {
            Cookies(client);
            var login = await client.PostAsJsonAsync("/auth/login", new { user.Email, password });
            Assert.Equal(HttpStatusCode.OK, login.StatusCode);
            Cookies(client, Cookie(login, "flood_mfa"));
            var response = await client.PostAsJsonAsync("/auth/mfa/verify", new { code = "invalid" });
            Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
            Assert.False(response.Headers.TryGetValues("Set-Cookie", out _));
        }
        // Isolate the MFA limiter from Identity lockout: even a reset and fresh
        // password login cannot replenish the per-subject verification budget.
        using (var scope = factory.Services.CreateScope())
        {
            var users = scope.ServiceProvider.GetRequiredService<UserManager<AppUser>>();
            var stored = (await users.FindByIdAsync(user.Id.ToString()))!;
            await users.SetLockoutEndDateAsync(stored, null);
            await users.ResetAccessFailedCountAsync(stored);
        }
        Cookies(client);
        var renewed = await client.PostAsJsonAsync("/auth/login", new { user.Email, password });
        Assert.Equal(HttpStatusCode.OK, renewed.StatusCode);
        Cookies(client, Cookie(renewed, "flood_mfa"));
        var blocked = await client.PostAsJsonAsync("/auth/mfa/verify", new { code = Totp(secret) });
        Assert.Equal(HttpStatusCode.TooManyRequests, blocked.StatusCode);
        Assert.False(blocked.Headers.TryGetValues("Set-Cookie", out _));
    }
    [Fact]
    public async Task UnknownUserStillVerifiesPasswordHash()
    {
        var hasher = new RecordingHasher();
        await using var factory = new ApiFactory();
        await using var configured = factory.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddScoped<IPasswordHasher<AppUser>>(_ => hasher)));
        using var client = configured.CreateClient();
        client.DefaultRequestHeaders.Add("X-Requested-With", "XMLHttpRequest");
        var response = await client.PostAsJsonAsync("/auth/login", new { email = "absent@flood.local", password = "incorrect" });
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal(1, hasher.Verifications);
    }
    private sealed class RecordingHasher : IPasswordHasher<AppUser>
    {
        private readonly PasswordHasher<AppUser> inner = new();
        public int Verifications { get; private set; }
        public string HashPassword(AppUser user, string password) => inner.HashPassword(user, password);
        public PasswordVerificationResult VerifyHashedPassword(AppUser user, string hash, string password)
        { Verifications++; return inner.VerifyHashedPassword(user, hash, password); }
    }
    private static string Totp(string base32)
    {
        const string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
        var bytes = new List<byte>(); var bits = 0; var value = 0;
        foreach (var c in base32.TrimEnd('='))
        {
            value = (value << 5) | alphabet.IndexOf(c); bits += 5;
            if (bits >= 8) { bits -= 8; bytes.Add((byte)(value >> bits)); }
        }
        var counter = BitConverter.GetBytes(DateTimeOffset.UtcNow.ToUnixTimeSeconds() / 30);
        if (BitConverter.IsLittleEndian) Array.Reverse(counter);
        var hash = HMACSHA1.HashData(bytes.ToArray(), counter); var offset = hash[^1] & 15;
        var number = ((hash[offset] & 127) << 24) | (hash[offset + 1] << 16) | (hash[offset + 2] << 8) | hash[offset + 3];
        return (number % 1000000).ToString("D6");
    }
}
