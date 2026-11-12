using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.EntityFrameworkCore;
using Ops.Api.Data;
using Ops.Api.Domain;

namespace Ops.Api.Messaging;

public sealed record PointStatusEvent(Guid EventId, string Type, string PointId, string PointName, string Zone,
    string Previous, string Current, double? WaterDepthCm, DateTimeOffset OccurredAt, double? WatchThresholdCm = null, double? AlertThresholdCm = null);
public static class Wire
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
        { Converters = { new JsonStringEnumConverter(allowIntegerValues: false) } };
    public static void Enqueue(OpsDb db, string type, object data) => db.Outbox.Add(new OutboxMessage
        { Payload = JsonSerializer.Serialize(new { type, data }, Json) });
}
public sealed class StatusHandler(OpsDb db, Folios folios, IConfiguration config, ILogger<StatusHandler> log)
{
    public static Priority EventPriority(string status, double? depth, double threshold) => status switch
    {
        "Alert" => depth >= 1.5 * threshold ? Priority.Critical : Priority.High,
        "NoData" => Priority.Medium, _ => Priority.Low
    };
    public async Task<bool> Handle(PointStatusEvent e, CancellationToken ct = default)
    {
        if (e.EventId == Guid.Empty || e.Type != "point.status_changed" ||
            !ValidPoint(e.PointId) || string.IsNullOrWhiteSpace(e.PointName) || e.PointName.Length > 200 ||
            string.IsNullOrWhiteSpace(e.Zone) || e.Zone.Length > 100 ||
            e.Current is not ("Normal" or "Watch" or "Alert" or "NoData") ||
            e.Previous is not ("Normal" or "Watch" or "Alert" or "NoData") || e.OccurredAt == default ||
            e.OccurredAt.Offset != TimeSpan.Zero || e.WaterDepthCm is { } d && (!double.IsFinite(d) || d < 0 || d > 150) ||
            e.AlertThresholdCm is { } a && (!double.IsFinite(a) || a <= 0 || a > 150) ||
            e.WatchThresholdCm is { } w && (!double.IsFinite(w) || w <= 0 || w > 150) ||
            e.WatchThresholdCm is { } watch && e.AlertThresholdCm is { } alertThreshold && watch >= alertThreshold)
            throw new ArgumentException("Invalid point status event.");
        await using var tx = db.Database.IsRelational() ? await db.Database.BeginTransactionAsync(ct) : null;
        // One lock per point serializes processing across replicas, including duplicate delivery.
        if (db.Database.IsRelational())
            await db.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(hashtextextended({e.PointId}, 0))", ct);
        if (await db.ProcessedEvents.AnyAsync(x => x.EventId == e.EventId, ct)) return false;
        var open = await db.Alerts.Where(x => x.PointId == e.PointId && x.Status == AlertStatus.Open).ToListAsync(ct);
        if (e.Current == "Normal")
        {
            foreach (var alert in open)
            {
                alert.Status = AlertStatus.Closed; alert.ClosedAt = e.OccurredAt; Wire.Enqueue(db, "alert.closed", alert);
            }
        }
        else
        {
            var level = e.Current == "NoData" ? AlertLevel.DataGap : e.Current == "Alert" ? AlertLevel.Alert : AlertLevel.Watch;
            var alert = open.FirstOrDefault(x => level == AlertLevel.DataGap ? x.Level == AlertLevel.DataGap : x.Level != AlertLevel.DataGap);
            if (alert == null)
            {
                alert = new Alert { SourceEventId = e.EventId, PointId = e.PointId, PointName = e.PointName,
                    Zone = e.Zone, Level = level, OpenedAt = e.OccurredAt, DepthCm = e.WaterDepthCm,
                    Reason = e.Current == "NoData" ? "Telemetry unavailable" : "Water depth threshold exceeded" };
                db.Alerts.Add(alert); Wire.Enqueue(db, "alert.opened", alert);
            }
            else if (level == AlertLevel.Alert && alert.Level != AlertLevel.Alert)
            {
                alert.Level = level; alert.DepthCm = e.WaterDepthCm; Wire.Enqueue(db, "alert.opened", alert);
            }
            if (e.Current is "Alert" or "NoData" && !await db.WorkOrders.AnyAsync(x => x.AlertId == alert.Id, ct))
            {
                var threshold = e.AlertThresholdCm ?? config.GetValue<double?>($"Operations:AlertThresholds:{e.PointId}")
                    ?? config.GetValue("Operations:DefaultAlertThresholdCm", 30d);
                if (!double.IsFinite(threshold) || threshold <= 0) throw new InvalidOperationException("Invalid alert threshold configuration.");
                var priority = EventPriority(e.Current, e.WaterDepthCm, threshold);
                var order = new WorkOrder { Folio = await folios.Next(), AlertId = alert.Id, PointId = e.PointId,
                    Title = e.Current == "NoData" ? "Inspect device" : $"Flood response: {e.PointName}",
                    Priority = priority, CreatedAt = e.OccurredAt, SlaDueAt = e.OccurredAt + WorkOrder.Sla(priority) };
                db.WorkOrders.Add(order); Wire.Enqueue(db, "workorder.created", order);
            }
        }
        db.ProcessedEvents.Add(new ProcessedEvent { EventId = e.EventId, ProcessedAt = DateTimeOffset.UtcNow });
        await db.SaveChangesAsync(ct);
        if (tx != null) await tx.CommitAsync(ct);
        log.LogInformation("{event} {point_id}", "stream.event_processed", e.PointId);
        return true;
    }
    public static bool ValidPoint(string? id) => id is { Length: > 0 and <= 50 } && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_');
}
