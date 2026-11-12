using System.Net;
using System.Security.Claims;
using Microsoft.IdentityModel.Tokens;
using System.Text.Json.Serialization;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Console;
using Ops.Api.Auth;
using Ops.Api.Data;
using Ops.Api.Domain;
using Ops.Api.Features.Operations;
using Ops.Api.Messaging;
using Ops.Api.Realtime;
using StackExchange.Redis;

if (args.Contains("--healthcheck"))
{
    try
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
        Environment.ExitCode = (await client.GetAsync("http://127.0.0.1:8080/healthz")).IsSuccessStatusCode ? 0 : 1;
    }
    catch { Environment.ExitCode = 1; }
    return;
}
var builder = WebApplication.CreateBuilder(args);
var testing = builder.Environment.IsEnvironment("Testing");
builder.WebHost.ConfigureKestrel(k => { k.AddServerHeader = false; k.Limits.MaxRequestBodySize = 32768; });
builder.WebHost.UseUrls("http://0.0.0.0:8080");
builder.Logging.ClearProviders();
builder.Logging.AddFilter("Microsoft.EntityFrameworkCore.Database.Command", LogLevel.Warning);
builder.Logging.AddJsonConsole();
builder.Logging.AddConsoleFormatter<FloodFormatter, ConsoleFormatterOptions>();
builder.Services.Configure<ConsoleLoggerOptions>(o => o.FormatterName = "flood");
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.Converters.Add(new JsonStringEnumConverter(allowIntegerValues: false)));
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    o.KnownIPNetworks.Clear(); o.KnownProxies.Clear();
    o.KnownProxies.Add(IPAddress.Parse(builder.Configuration["Gateway:Ip"] ?? "172.30.30.10")); o.ForwardLimit = 1;
});
if (!testing)
{
    builder.Services.AddDbContext<OpsDb>(o => o.EnableSensitiveDataLogging(false).UseNpgsql(Secrets.Database(builder.Configuration),
        n => n.MigrationsHistoryTable("__EFMigrationsHistory", "ops")));
    var redisOptions = Secrets.Redis(builder.Configuration);
    builder.Services.AddSingleton<IConnectionMultiplexer>(_ => ConnectionMultiplexer.Connect(redisOptions));
    builder.Services.AddSignalR().AddStackExchangeRedis(o => o.Configuration = redisOptions);
    builder.Services.AddHostedService<StreamWorker>(); builder.Services.AddHostedService<OutboxWorker>(); builder.Services.AddHostedService<LiveWorker>();
}
else builder.Services.AddSignalR(); // Test host supplies DB and RSA keys; production always requires secret files.
builder.Services.AddSingleton<JwtTokens>();
builder.Services.AddScoped<Folios>(); builder.Services.AddScoped<StatusHandler>();
// Only authenticator tokens are exposed; no disk-backed data-protection keys are needed.
builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
builder.Services.AddIdentityCore<AppUser>(o =>
{
    o.Password.RequiredLength = 12; o.User.RequireUniqueEmail = true;
    o.Lockout.MaxFailedAccessAttempts = 5; o.Lockout.DefaultLockoutTimeSpan = TimeSpan.FromMinutes(15);
}).AddRoles<IdentityRole<Guid>>().AddEntityFrameworkStores<OpsDb>().AddSignInManager().AddDefaultTokenProviders();
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer();
builder.Services.AddOptions<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme).Configure<JwtTokens>((o, jwt) =>
{
    o.MapInboundClaims = false; o.TokenValidationParameters = jwt.Validation();
    o.Events = new JwtBearerEvents
    {
        OnMessageReceived = c => { c.Token = c.Request.Cookies["flood_at"]; return Task.CompletedTask; },
        OnAuthenticationFailed = c => { SecurityLog.Event(c.HttpContext.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Auth"), "auth.jwt_rejected", c.HttpContext); return Task.CompletedTask; }
    };
});
builder.Services.AddAuthorization(o => Roles.Configure(o, builder.Configuration.GetValue("Security:EnforceMfa", false)));
builder.Services.AddProblemDetails();
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = 429;
    o.OnRejected = async (context, ct) =>
    {
        SecurityLog.Event(context.HttpContext.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("RateLimit"), "ratelimit.hit", context.HttpContext);
        if (context.HttpContext.Request.Path == "/auth/mfa/verify")
            SecurityLog.Event(context.HttpContext.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Auth"), "auth.lockout", context.HttpContext, MfaSubject(context.HttpContext));
        await Results.Problem(statusCode: 429, title: "Too many requests.").ExecuteAsync(context.HttpContext);
    };
    o.AddPolicy("login", context => RateLimitPartition.GetFixedWindowLimiter(context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = 10, Window = TimeSpan.FromMinutes(5), QueueLimit = 0 }));
    o.AddPolicy("mfa", context => RateLimitPartition.GetFixedWindowLimiter(
        MfaSubject(context) ?? $"invalid:{context.Connection.RemoteIpAddress}",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = 5, Window = TimeSpan.FromMinutes(15), QueueLimit = 0 }));
    o.AddPolicy("reports", context => RateLimitPartition.GetFixedWindowLimiter(context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = 5, Window = TimeSpan.FromMinutes(10), QueueLimit = 0 }));
});
var app = builder.Build();
app.UseForwardedHeaders();
app.UseExceptionHandler(handler => handler.Run(async context =>
{
    var error = context.Features.Get<Microsoft.AspNetCore.Diagnostics.IExceptionHandlerFeature>()?.Error;
    var status = error switch { DbUpdateConcurrencyException => 409, ArgumentException => 400, BadHttpRequestException => 400, UnauthorizedAccessException => 403, _ => 500 };
    SecurityLog.Event(context.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Errors"), "request.failed", context);
    await Results.Problem(statusCode: status, title: status switch { 409 => "Record changed. Reload and retry.", 400 => "Invalid request.", 403 => "Forbidden.", _ => "Request failed." }).ExecuteAsync(context);
}));
app.UseStatusCodePages(async c => await Results.Problem(statusCode: c.HttpContext.Response.StatusCode).ExecuteAsync(c.HttpContext));
app.UseMiddleware<HubOriginMiddleware>();
app.UseRouting(); app.UseAuthentication(); app.UseMiddleware<CsrfMiddleware>(); app.UseRateLimiter(); app.UseAuthorization();
app.Use(async (context, next) =>
{
    if (context.Request.Path.StartsWithSegments("/auth")) context.Response.Headers.CacheControl = "no-store";
    await next(context);
});
app.MapAuth(); app.MapOperations();
app.MapHub<LiveHub>("/hubs/live", o => o.CloseOnAuthenticationExpiration = true);
app.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));
app.MapGet("/readyz", async (OpsDb db, IServiceProvider services, CancellationToken ct) =>
{
    try
    {
        if (!await db.Database.CanConnectAsync(ct)) return Results.StatusCode(503);
        await services.GetRequiredService<IConnectionMultiplexer>().GetDatabase().PingAsync();
        return Results.Ok(new { status = "ready" });
    }
    catch { return Results.StatusCode(503); }
});
if (!testing)
{
    using var scope = app.Services.CreateScope();
    await scope.ServiceProvider.GetRequiredService<OpsDb>().Database.MigrateAsync();
    await Seeder.Seed(scope.ServiceProvider, app.Configuration);
}
app.Run();

static string? MfaSubject(HttpContext context)
{
    if (!context.Request.Cookies.TryGetValue("flood_mfa", out var pending) || pending.Length > 8192) return null;
    try { return context.RequestServices.GetRequiredService<JwtTokens>().ValidatePending(pending).FindFirstValue("sub"); }
    catch (Exception e) when (e is SecurityTokenException or ArgumentException) { return null; }
}
public partial class Program { }
