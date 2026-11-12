using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Ops.Api.Data;
using Ops.Api.Domain;

namespace Ops.Api.Auth;

public static class AuthEndpoints
{
    private static readonly AppUser DummyUser = new();
    private static readonly string DummyHash = new PasswordHasher<AppUser>().HashPassword(DummyUser, Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)));
    public record Login(string Email, string Password);
    public record MfaCode(string Code);
    private static CookieOptions Cookie(string path, TimeSpan age) => new()
        { HttpOnly = true, Secure = true, SameSite = SameSiteMode.Strict, Path = path, MaxAge = age, IsEssential = true };
    public static string Hash(string raw) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(raw)));
    public static void MapAuth(this WebApplication app)
    {
        var g = app.MapGroup("/auth");
        g.MapPost("/login", async (Login input, UserManager<AppUser> users, SignInManager<AppUser> signin,
            JwtTokens jwt, OpsDb db, HttpContext http, ILoggerFactory logs, IPasswordHasher<AppUser> hasher) =>
        {
            var log = logs.CreateLogger("Auth");
            if (string.IsNullOrWhiteSpace(input.Email) || input.Email.Length > 254 || string.IsNullOrEmpty(input.Password) || input.Password.Length > 1024)
                return Results.BadRequest();
            var user = await users.FindByEmailAsync(input.Email);
            if (user is null) hasher.VerifyHashedPassword(DummyUser, DummyHash, input.Password);
            var result = user is null ? SignInResult.Failed : await signin.CheckPasswordSignInAsync(user, input.Password, true);
            if (!result.Succeeded)
            {
                SecurityLog.Event(log, result.IsLockedOut ? "auth.lockout" : "auth.login_failed", http, user?.Id.ToString());
                return Results.Unauthorized();
            }
            var roles = await users.GetRolesAsync(user!);
            if (await users.GetTwoFactorEnabledAsync(user!))
            {
                http.Response.Cookies.Append("flood_mfa", jwt.Issue(user!, [], "pwd", true), Cookie("/api/ops/auth", TimeSpan.FromMinutes(5)));
                return Results.Ok(new { mfaRequired = true });
            }
            await Issue(http, db, jwt, user!, roles, "pwd");
            SecurityLog.Event(log, "auth.login_success", http, user!.Id.ToString()); return Results.Ok(new { mfaRequired = false });
        }).RequireRateLimiting("login");
        g.MapPost("/refresh", async (HttpContext http, OpsDb db, UserManager<AppUser> users, JwtTokens jwt) =>
        {
            if (!http.Request.Cookies.TryGetValue("flood_rt", out var raw) || raw.Length > 256) return Results.Unauthorized();
            var old = await db.RefreshTokens.SingleOrDefaultAsync(x => x.Hash == Hash(raw));
            if (old is null) return Results.Unauthorized();
            if (old.Revoked != null)
            {
                await RevokeFamily(db, old.Family); Clear(http); return Results.Unauthorized();
            }
            if (old.Expires <= DateTimeOffset.UtcNow) { Clear(http); return Results.Unauthorized(); }
            var user = await users.FindByIdAsync(old.UserId.ToString());
            if (user is null || await users.IsLockedOutAsync(user)) return Results.Unauthorized();
            old.Revoked = DateTimeOffset.UtcNow; old.Version = Guid.NewGuid();
            var token = NewRefresh(); old.ReplacedBy = Hash(token);
            db.RefreshTokens.Add(TokenRow(token, user.Id, old.Amr, old.Family));
            try { await db.SaveChangesAsync(); }
            catch (DbUpdateConcurrencyException) { db.ChangeTracker.Clear(); await RevokeFamily(db, old.Family); Clear(http); return Results.Unauthorized(); }
            SetCookies(http, jwt.Issue(user, await users.GetRolesAsync(user), old.Amr), token);
            return Results.Ok();
        });
        g.MapPost("/logout", async (HttpContext http, OpsDb db) =>
        {
            if (http.Request.Cookies.TryGetValue("flood_rt", out var raw) && raw.Length <= 256)
            {
                var token = await db.RefreshTokens.FindAsync(Hash(raw));
                if (token != null) await RevokeFamily(db, token.Family);
            }
            Clear(http); return Results.NoContent();
        });
        g.MapGet("/me", async (HttpContext http, UserManager<AppUser> users) =>
        {
            var user = await users.FindByIdAsync(http.User.FindFirstValue("sub")!);
            return user == null ? Results.Unauthorized() : Results.Ok(new { user.Id, user.Email, roles = await users.GetRolesAsync(user), mfaEnabled = user.TwoFactorEnabled });
        }).RequireAuthorization();
        g.MapPost("/mfa/setup", async (HttpContext http, UserManager<AppUser> users) =>
        {
            var user = (await users.FindByIdAsync(http.User.FindFirstValue("sub")!))!;
            if (user.TwoFactorEnabled) return Results.Conflict(new { error = "MFA already enabled." });
            var key = await users.GetAuthenticatorKeyAsync(user);
            if (key == null) { await users.ResetAuthenticatorKeyAsync(user); key = await users.GetAuthenticatorKeyAsync(user); }
            return Results.Ok(new { otpauthUri = $"otpauth://totp/Flood:{Uri.EscapeDataString(user.Email!)}?secret={key}&issuer=Flood&digits=6" });
        }).RequireAuthorization();
        g.MapPost("/mfa/enable", async (MfaCode input, HttpContext http, UserManager<AppUser> users, OpsDb db) =>
        {
            var user = (await users.FindByIdAsync(http.User.FindFirstValue("sub")!))!;
            if (await users.IsLockedOutAsync(user)) return Results.Unauthorized();
            if (!ValidCode(input.Code) || !await users.VerifyTwoFactorTokenAsync(user, TokenOptions.DefaultAuthenticatorProvider, input.Code))
            { await users.AccessFailedAsync(user); SecurityLog.Event(http.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Auth"), "auth.mfa_failed", http); return Results.Unauthorized(); }
            await users.SetTwoFactorEnabledAsync(user, true); await users.ResetAccessFailedCountAsync(user);
            // Existing password-only refresh families must not survive enrollment.
            var active = await db.RefreshTokens.Where(x => x.UserId == user.Id && x.Revoked == null).ToListAsync();
            foreach (var token in active) { token.Revoked = DateTimeOffset.UtcNow; token.Version = Guid.NewGuid(); }
            await db.SaveChangesAsync(); return Results.Ok();
        }).RequireAuthorization().RequireRateLimiting("login");
        g.MapPost("/mfa/verify", async (MfaCode input, HttpContext http, UserManager<AppUser> users, OpsDb db, JwtTokens jwt, ILoggerFactory logs) =>
        {
            if (!http.Request.Cookies.TryGetValue("flood_mfa", out var pending) || pending.Length > 8192) return Results.Unauthorized();
            ClaimsPrincipal principal;
            try { principal = jwt.ValidatePending(pending); }
            catch (Exception e) when (e is SecurityTokenException or ArgumentException) { return Results.Unauthorized(); }
            var user = await users.FindByIdAsync(principal.FindFirstValue("sub")!);
            if (user == null || !user.TwoFactorEnabled || await users.IsLockedOutAsync(user)) return Results.Unauthorized();
            if (!ValidCode(input.Code) || !await users.VerifyTwoFactorTokenAsync(user, TokenOptions.DefaultAuthenticatorProvider, input.Code))
            {
                await users.AccessFailedAsync(user); SecurityLog.Event(logs.CreateLogger("Auth"), "auth.mfa_failed", http, user.Id.ToString()); return Results.Unauthorized();
            }
            await users.ResetAccessFailedCountAsync(user);
            http.Response.Cookies.Delete("flood_mfa", Cookie("/api/ops/auth", TimeSpan.Zero));
            await Issue(http, db, jwt, user, await users.GetRolesAsync(user), "mfa");
            SecurityLog.Event(logs.CreateLogger("Auth"), "auth.login_success", http, user!.Id.ToString()); return Results.Ok();
        }).RequireRateLimiting("mfa");
    }
    private static bool ValidCode(string? code) => code is { Length: 6 } && code.All(char.IsAsciiDigit);
    private static string NewRefresh() => Convert.ToBase64String(RandomNumberGenerator.GetBytes(48));
    private static RefreshToken TokenRow(string raw, Guid user, string amr, Guid family) => new()
        { Hash = Hash(raw), UserId = user, Amr = amr, Family = family, Expires = DateTimeOffset.UtcNow.AddDays(7) };
    private static async Task Issue(HttpContext http, OpsDb db, JwtTokens jwt, AppUser user, IEnumerable<string> roles, string amr)
    {
        var family = Guid.NewGuid(); var raw = NewRefresh();
        db.RefreshTokens.Add(TokenRow(raw, user.Id, amr, family)); await db.SaveChangesAsync();
        SetCookies(http, jwt.Issue(user, roles, amr), raw);
    }
    private static void SetCookies(HttpContext http, string access, string refresh)
    {
        http.Response.Headers.CacheControl = "no-store";
        http.Response.Cookies.Append("flood_at", access, Cookie("/", TimeSpan.FromMinutes(15)));
        http.Response.Cookies.Append("flood_rt", refresh, Cookie("/api/ops/auth", TimeSpan.FromDays(7)));
    }
    private static void Clear(HttpContext http)
    {
        http.Response.Cookies.Delete("flood_at", Cookie("/", TimeSpan.Zero));
        http.Response.Cookies.Delete("flood_rt", Cookie("/api/ops/auth", TimeSpan.Zero));
        http.Response.Cookies.Delete("flood_mfa", Cookie("/api/ops/auth", TimeSpan.Zero));
    }
    private static async Task RevokeFamily(OpsDb db, Guid family)
    {
        if (db.Database.IsRelational())
            await db.RefreshTokens.Where(x => x.Family == family && x.Revoked == null)
                .ExecuteUpdateAsync(s => s.SetProperty(x => x.Revoked, DateTimeOffset.UtcNow).SetProperty(x => x.Version, Guid.NewGuid()));
        else
        {
            foreach (var token in await db.RefreshTokens.Where(x => x.Family == family).ToListAsync())
            { token.Revoked = DateTimeOffset.UtcNow; token.Version = Guid.NewGuid(); }
            await db.SaveChangesAsync();
        }
    }
}
