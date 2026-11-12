using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Logging.Console;
using Microsoft.IdentityModel.Tokens;
using Npgsql;
using Ops.Api.Domain;
using StackExchange.Redis;

namespace Ops.Api.Auth;

public static class Secrets
{
    public static string Read(IConfiguration config, string name)
    {
        var path = config[name] ?? throw new InvalidOperationException($"Missing configuration: {name}");
        if (!Path.GetFullPath(path).StartsWith("/run/secrets/", StringComparison.Ordinal))
            throw new InvalidOperationException($"{name} must be a file under /run/secrets.");
        return File.ReadAllText(path).Trim();
    }
    public static string Database(IConfiguration c) => new NpgsqlConnectionStringBuilder
    {
        Host = c["Database:Host"] ?? "postgres", Port = c.GetValue("Database:Port", 5432),
        Database = c["Database:Name"] ?? "flood", Username = c["Database:User"] ?? "ops_svc",
        Password = Read(c, "Database:PasswordFile"), SearchPath = "ops", Timeout = 5, CommandTimeout = 15,
        IncludeErrorDetail = false, GssEncryptionMode = GssEncryptionMode.Disable
    }.ConnectionString;
    public static ConfigurationOptions Redis(IConfiguration c)
    {
        var options = new ConfigurationOptions { Password = Read(c, "Redis:PasswordFile"), AbortOnConnectFail = false,
            ConnectTimeout = 5000, SyncTimeout = 5000, AsyncTimeout = 5000 };
        options.EndPoints.Add(c["Redis:Host"] ?? "redis", c.GetValue("Redis:Port", 6379));
        return options;
    }
}
public sealed class JwtTokens : IDisposable
{
    private readonly RSA privateKey = RSA.Create();
    private readonly RSA publicKey = RSA.Create();
    public JwtTokens(IConfiguration c) : this(Secrets.Read(c, "Jwt:PrivateKeyFile"), Secrets.Read(c, "Jwt:PublicKeyFile")) { }
    public JwtTokens(string privatePem, string publicPem)
    {
        privateKey.ImportFromPem(privatePem); publicKey.ImportFromPem(publicPem);
        if (privateKey.KeySize < 2048 || !privateKey.ExportSubjectPublicKeyInfo().SequenceEqual(publicKey.ExportSubjectPublicKeyInfo()))
            throw new InvalidOperationException("JWT keys must match and use RSA >= 2048 bits.");
    }
    public TokenValidationParameters Validation(string audience = "flood-platform") => new()
    {
        ValidateIssuerSigningKey = true, IssuerSigningKey = new RsaSecurityKey(publicKey),
        ValidAlgorithms = [SecurityAlgorithms.RsaSha256], ValidateIssuer = true, ValidIssuer = "flood-ops",
        ValidateAudience = true, ValidAudience = audience, ValidateLifetime = true, RequireExpirationTime = true,
        ClockSkew = TimeSpan.FromSeconds(15), NameClaimType = "sub", RoleClaimType = "role"
    };
    public string Issue(AppUser user, IEnumerable<string> roles, string amr, bool pending = false)
    {
        var claims = new List<Claim> { new("sub", user.Id.ToString()), new("email", user.Email!), new("amr", amr),
            new("jti", Guid.NewGuid().ToString()) };
        if (!pending) claims.AddRange(roles.Select(role => new Claim("role", role)));
        return new JwtSecurityTokenHandler().WriteToken(new JwtSecurityToken("flood-ops", pending ? "flood-mfa" : "flood-platform",
            claims, DateTime.UtcNow, DateTime.UtcNow.AddMinutes(pending ? 5 : 15),
            new SigningCredentials(new RsaSecurityKey(privateKey), SecurityAlgorithms.RsaSha256)));
    }
    public ClaimsPrincipal ValidatePending(string token) => new JwtSecurityTokenHandler { MapInboundClaims = false }
        .ValidateToken(token, Validation("flood-mfa"), out _);
    public void Dispose() { privateKey.Dispose(); publicKey.Dispose(); }
}
public static class Roles
{
    public static readonly string[] All = ["Operator", "Supervisor", "Admin"];
    public static bool Supervisor(ClaimsPrincipal user) => user.IsInRole("Supervisor") || user.IsInRole("Admin");
    public static bool Allows(ClaimsPrincipal user, string policy, bool enforceMfa)
    {
        var role = policy switch
        {
            "Operator" => All.Any(user.IsInRole), "Supervisor" => Supervisor(user), "Admin" => user.IsInRole("Admin"), _ => false
        };
        return user.Identity?.IsAuthenticated == true && role &&
            (!enforceMfa || !Supervisor(user) || user.HasClaim("amr", "mfa"));
    }
    public static void Configure(AuthorizationOptions options, bool enforce)
    {
        foreach (var role in All) options.AddPolicy(role, p => p.RequireAssertion(c => Allows(c.User, role, enforce)));
    }
}
public sealed class CsrfMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context, ILogger<CsrfMiddleware> log)
    {
        if (HttpMethods.IsPost(context.Request.Method) || HttpMethods.IsPut(context.Request.Method) ||
            HttpMethods.IsPatch(context.Request.Method) || HttpMethods.IsDelete(context.Request.Method))
        {
            if (context.Request.Headers["X-Requested-With"] != "XMLHttpRequest")
            {
                SecurityLog.Event(log, "csrf.rejected", context);
                await Results.Problem(statusCode: 403, title: "CSRF header required.").ExecuteAsync(context); return;
            }
        }
        await next(context);
    }
}
public static class SecurityLog
{
    public static void Event(ILogger log, string name, HttpContext? context = null, string? user = null) =>
        log.LogInformation("{event} {client_ip} {user} {path}", name,
            context?.Connection.RemoteIpAddress?.ToString(), user ?? context?.User.FindFirstValue("sub"), context?.Request.Path.Value);
}
public sealed class FloodFormatter() : ConsoleFormatter("flood")
{
    public override void Write<TState>(in LogEntry<TState> entry, IExternalScopeProvider? scopes, TextWriter writer)
    {
        var fields = new Dictionary<string, object?> { ["ts"] = DateTimeOffset.UtcNow, ["level"] = entry.LogLevel.ToString(),
            ["service"] = "ops-service", ["event"] = "service.log", ["category"] = entry.Category };
        if (entry.State is IEnumerable<KeyValuePair<string, object?>> state)
            foreach (var pair in state)
                if (pair.Key is "event" or "client_ip" or "user" or "path" or "status" or "point_id") fields[pair.Key] = pair.Value;
        fields["msg"] = entry.Formatter(entry.State, entry.Exception);
        if (entry.Exception is { } error)
        {
            fields["error_type"] = error.GetType().Name;
            fields["exc"] = new { type = error.GetType().Name, message = error.Message, traceback = error.ToString() };
        }
        writer.WriteLine(JsonSerializer.Serialize(fields));
    }
}
