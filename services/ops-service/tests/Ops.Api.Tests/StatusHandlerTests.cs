using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Ops.Api.Data;
using Ops.Api.Domain;
using Ops.Api.Messaging;

namespace Ops.Api.Tests;

public class StatusHandlerTests
{
    private static OpsDb Db() => new(new DbContextOptionsBuilder<OpsDb>().UseInMemoryDatabase(Guid.NewGuid().ToString()).Options);
    private static PointStatusEvent Event(string status, double? depth = null) => new(Guid.NewGuid(), "point.status_changed", "P01", "Punto simulado P01", "Centro", "Normal", status, depth, DateTimeOffset.UtcNow);
    private static StatusHandler Handler(OpsDb db) => new(db, new Folios(db), new ConfigurationBuilder().Build(), NullLogger<StatusHandler>.Instance);
    [Fact]
    public async Task DuplicateEventDoesNotDuplicateEffects()
    {
        await using var db = Db(); var handler = Handler(db); var e = Event("Alert", 45);
        Assert.True(await handler.Handle(e)); Assert.False(await handler.Handle(e));
        Assert.Single(db.Alerts); Assert.Single(db.WorkOrders); Assert.Single(db.ProcessedEvents); Assert.Equal(2, db.Outbox.Count());
        Assert.Equal(Priority.Critical, db.WorkOrders.Single().Priority);
    }
    [Fact]
    public async Task WatchEscalatesAndNormalClosesAlertsLeavingOrders()
    {
        await using var db = Db(); var h = Handler(db);
        await h.Handle(Event("Watch", 15)); Assert.Empty(db.WorkOrders);
        await h.Handle(Event("Alert", 31)); Assert.Single(db.Alerts); Assert.Equal(AlertLevel.Alert, db.Alerts.Single().Level);
        await h.Handle(Event("Normal", 0)); Assert.Equal(AlertStatus.Closed, db.Alerts.Single().Status);
        Assert.Equal(OrderStatus.Open, db.WorkOrders.Single().Status);
    }
    [Fact]
    public async Task NoDataCreatesInspectionAndKeepsMissingDepth()
    {
        await using var db = Db(); await Handler(db).Handle(Event("NoData"));
        Assert.Null(db.Alerts.Single().DepthCm); Assert.Equal(AlertLevel.DataGap, db.Alerts.Single().Level);
        Assert.Equal(Priority.Medium, db.WorkOrders.Single().Priority); Assert.Equal("Inspect device", db.WorkOrders.Single().Title);
    }
    [Fact]
    public async Task RepeatedAlertStatusDoesNotCreateSecondOrder()
    {
        await using var db = Db(); var h = Handler(db); await h.Handle(Event("Alert", 31)); await h.Handle(Event("Alert", 32));
        Assert.Single(db.Alerts); Assert.Single(db.WorkOrders); Assert.Equal(2, db.ProcessedEvents.Count());
    }
    [Fact]
    public async Task InvalidEventWritesNothing()
    {
        await using var db = Db(); await Assert.ThrowsAsync<ArgumentException>(() => Handler(db).Handle(Event("Wrong")));
        Assert.Empty(db.Alerts); Assert.Empty(db.ProcessedEvents); Assert.Empty(db.Outbox);
    }
    [Theory]
    [InlineData(20.0, 30.0, Priority.Critical)]
    [InlineData(40.0, 45.0, Priority.High)]
    [InlineData(null, 45.0, Priority.Critical)]
    public async Task EventThresholdOverridesConfiguredFallback(double? threshold, double depth, Priority expected)
    {
        await using var db = Db();
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Operations:DefaultAlertThresholdCm"] = "30"
        }).Build();
        var handler = new StatusHandler(db, new Folios(db), config, NullLogger<StatusHandler>.Instance);
        var json = System.Text.Json.JsonSerializer.Serialize(new
        {
            eventId = Guid.NewGuid(), type = "point.status_changed", pointId = "P01", pointName = "Simulado",
            zone = "Centro", previous = "Normal", current = "Alert", waterDepthCm = depth,
            occurredAt = DateTimeOffset.UtcNow, watchThresholdCm = 15, alertThresholdCm = threshold
        });
        var e = System.Text.Json.JsonSerializer.Deserialize<PointStatusEvent>(json, Wire.Json)!;
        await handler.Handle(e);
        Assert.Equal(expected, db.WorkOrders.Single().Priority);
        Assert.Equal(e.OccurredAt + WorkOrder.Sla(expected), db.WorkOrders.Single().SlaDueAt);
    }
    [Theory]
    [InlineData(0)] [InlineData(-1)] [InlineData(151)]
    public async Task InvalidEventThresholdRejectedBeforeWrites(double threshold)
    {
        await using var db = Db();
        var json = System.Text.Json.JsonSerializer.Serialize(new
        {
            eventId = Guid.NewGuid(), type = "point.status_changed", pointId = "P01", pointName = "Simulado",
            zone = "Centro", previous = "Normal", current = "Alert", waterDepthCm = 45,
            occurredAt = DateTimeOffset.UtcNow, alertThresholdCm = threshold
        });
        var e = System.Text.Json.JsonSerializer.Deserialize<PointStatusEvent>(json, Wire.Json)!;
        await Assert.ThrowsAsync<ArgumentException>(() => Handler(db).Handle(e));
        Assert.Empty(db.Alerts); Assert.Empty(db.WorkOrders); Assert.Empty(db.ProcessedEvents);
    }
}
