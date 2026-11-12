using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Ops.Api.Auth;
using Ops.Api.Data;
using Ops.Api.Domain;

namespace Ops.Api.Tests;

public sealed class ApiFactory : WebApplicationFactory<Program>
{
    private readonly string dbName = Guid.NewGuid().ToString();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.UseSetting("hostBuilder:reloadConfigOnChange", "false");
        builder.UseContentRoot(Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../src/Ops.Api")));
        builder.ConfigureServices(services =>
        {
            services.AddDbContext<OpsDb>(o => o.UseInMemoryDatabase(dbName));
            services.RemoveAll<JwtTokens>(); services.AddSingleton(_ => SecurityTests.Keys());
        });
    }
    public HttpClient Client(string? role = null)
    {
        var client = CreateClient(new WebApplicationFactoryClientOptions { BaseAddress = new Uri("https://localhost"), HandleCookies = false });
        client.DefaultRequestHeaders.Add("X-Requested-With", "XMLHttpRequest");
        if (role != null)
        {
            var token = Services.GetRequiredService<JwtTokens>().Issue(new AppUser { Id = Guid.NewGuid(), Email = "test@flood.local" }, [role], "pwd");
            client.DefaultRequestHeaders.Add("Cookie", $"flood_at={token}");
        }
        return client;
    }
}
public class ApiTests
{
    [Theory]
    [InlineData(null, "/work-orders", 401)] [InlineData("Operator", "/work-orders", 200)]
    [InlineData("Operator", "/users", 403)] [InlineData("Supervisor", "/audit", 403)]
    [InlineData("Admin", "/users", 200)] [InlineData("Admin", "/audit", 200)]
    [InlineData("Operator", "/crews", 403)] [InlineData("Supervisor", "/crews", 200)]
    public async Task RolePolicies(string? role, string path, int expected)
    {
        await using var factory = new ApiFactory(); using var client = factory.Client(role);
        Assert.Equal(expected, (int)(await client.GetAsync(path)).StatusCode);
    }
    [Fact]
    public async Task CitizenReportValidationAndPrivacyResponse()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client();
        var bad = await client.PostAsJsonAsync("/public/reports", new { category = "Otro", description = new string('x', 501) });
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
        var good = await client.PostAsJsonAsync("/public/reports", new { category = "DrenajeTapado", description = "Drenaje obstruido", pointId = "P01" });
        Assert.Equal(HttpStatusCode.Created, good.StatusCode);
        var json = await good.Content.ReadFromJsonAsync<JsonElement>(); Assert.StartsWith("RC-", json.GetProperty("folio").GetString());
        Assert.False(json.TryGetProperty("description", out _));
    }
    [Fact]
    public async Task UnsafeAuthEndpointRequiresCsrf()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client(); client.DefaultRequestHeaders.Remove("X-Requested-With");
        Assert.Equal(HttpStatusCode.Forbidden, (await client.PostAsJsonAsync("/auth/login", new { email = "test@flood.local", password = "unused" })).StatusCode);
    }
    [Fact]
    public async Task OrderLifecycleAndStaleVersion()
    {
        await using var factory = new ApiFactory(); using var supervisor = factory.Client("Supervisor"); using var op = factory.Client("Operator");
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<OpsDb>();
        var crew = new Crew { Name = "Centro", Zone = "Centro" }; db.Crews.Add(crew); await db.SaveChangesAsync();
        var created = await supervisor.PostAsJsonAsync("/work-orders", new { pointId = "P01", title = "Inspeccionar drenaje", priority = "High" });
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var order = (await created.Content.ReadFromJsonAsync<WorkOrder>(Ops.Api.Messaging.Wire.Json))!;
        var assigned = await supervisor.PatchAsJsonAsync($"/work-orders/{order.Id}/assign", new { crewId = crew.Id, version = order.Version });
        Assert.Equal(HttpStatusCode.OK, assigned.StatusCode);
        var stale = await op.PatchAsJsonAsync($"/work-orders/{order.Id}/transition", new { status = "InProgress", version = order.Version });
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        order = (await assigned.Content.ReadFromJsonAsync<WorkOrder>(Ops.Api.Messaging.Wire.Json))!;
        Assert.Equal(HttpStatusCode.OK, (await op.PatchAsJsonAsync($"/work-orders/{order.Id}/transition", new { status = "InProgress", version = order.Version })).StatusCode);
    }
    [Fact]
    public async Task PublicRateLimitAndLiveness()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client();
        for (var i = 0; i < 5; i++) Assert.Equal(HttpStatusCode.Created, (await client.PostAsJsonAsync("/public/reports", new { category = "Otro", description = "Agua" })).StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, (await client.PostAsJsonAsync("/public/reports", new { category = "Otro", description = "Agua" })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/healthz")).StatusCode);
    }
}

public class OperationsFlowTests
{
    [Fact]
    public async Task ReportsValidateLinkAndAudit()
    {
        await using var factory = new ApiFactory(); using var citizen = factory.Client();
        using var op = factory.Client("Operator"); using var supervisor = factory.Client("Supervisor"); using var admin = factory.Client("Admin");
        var submitted = await citizen.PostAsJsonAsync("/public/reports", new { pointId = "P01", category = "Otro", description = "Agua en calle" });
        var reportId = (await submitted.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetGuid();
        Assert.Equal(HttpStatusCode.Conflict, (await op.PatchAsJsonAsync($"/reports/{reportId}/link", new { workOrderId = Guid.NewGuid() })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await op.PatchAsync($"/reports/{reportId}/validate", null)).StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, (await op.PatchAsync($"/reports/{reportId}/reject", null)).StatusCode);
        var created = await supervisor.PostAsJsonAsync("/work-orders", new { pointId = "P01", title = "Desazolvar", priority = "Medium" });
        var orderId = (await created.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetGuid();
        Assert.Equal(HttpStatusCode.OK, (await op.PatchAsJsonAsync($"/reports/{reportId}/link", new { workOrderId = orderId })).StatusCode);
        var audit = await admin.GetFromJsonAsync<JsonElement[]>("/audit");
        Assert.Contains(audit!, x => x.GetProperty("action").GetString() == "report_validate");
        Assert.Contains(audit!, x => x.GetProperty("action").GetString() == "report_link");
    }
    [Fact]
    public async Task KpisExcludeResolvedOrdersAndMeasureResponse()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client("Operator");
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<OpsDb>();
        var now = DateTimeOffset.UtcNow;
        var alert = new Alert { PointId = "P01", Level = AlertLevel.Alert, OpenedAt = now.AddMinutes(-45) };
        db.Alerts.Add(alert);
        db.WorkOrders.Add(new WorkOrder { Folio = "OT-test1", Priority = Priority.High, AlertId = alert.Id, SlaDueAt = now.AddMinutes(-1), OnSiteAt = now.AddMinutes(-15), Status = OrderStatus.InProgress });
        db.WorkOrders.Add(new WorkOrder { Folio = "OT-test2", Priority = Priority.Critical, SlaDueAt = now.AddMinutes(-1), Status = OrderStatus.Resolved });
        await db.SaveChangesAsync();
        var response = await client.GetAsync("/kpis"); Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, json.GetProperty("openOrders").GetInt32()); Assert.Equal(1, json.GetProperty("overdue").GetInt32());
        Assert.Equal(30, json.GetProperty("avgMinutesAlertToOnSiteLast7Days").GetDouble());
    }
    [Fact]
    public async Task ListsBoundedAndFiltersApplied()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client("Operator");
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<OpsDb>();
        for (var i = 0; i < 110; i++) db.Alerts.Add(new Alert { SourceEventId = Guid.NewGuid(), PointId = "P01", Level = AlertLevel.Watch, OpenedAt = DateTimeOffset.UtcNow });
        db.Alerts.Add(new Alert { SourceEventId = Guid.NewGuid(), PointId = "P02", Status = AlertStatus.Closed }); await db.SaveChangesAsync();
        Assert.Equal(100, (await client.GetFromJsonAsync<JsonElement[]>("/alerts?limit=500"))!.Length);
        var filtered = await client.GetFromJsonAsync<JsonElement[]>("/alerts?pointId=P02&status=Closed"); Assert.Single(filtered!);
        Assert.Equal("P02", filtered![0].GetProperty("pointId").GetString());
    }
    [Fact]
    public async Task EmptyKpisKeepResponseTimeUnknown()
    {
        await using var factory = new ApiFactory(); using var client = factory.Client("Operator");
        var response = await client.GetAsync("/kpis"); Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>(); Assert.Equal(0, json.GetProperty("openOrders").GetInt32());
        Assert.Equal(JsonValueKind.Null, json.GetProperty("avgMinutesAlertToOnSiteLast7Days").ValueKind);
    }
}
