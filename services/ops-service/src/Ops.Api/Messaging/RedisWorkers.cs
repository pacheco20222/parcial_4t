using System.Text.Json;
using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using Ops.Api.Auth;
using Ops.Api.Data;
using Ops.Api.Realtime;
using StackExchange.Redis;

namespace Ops.Api.Messaging;

public sealed class StreamWorker(IConnectionMultiplexer redis, IServiceScopeFactory scopes, IHubContext<LiveHub> hub, ILogger<StreamWorker> log) : BackgroundService
{
    private readonly string consumer = $"ops-{Guid.NewGuid():N}";
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var db = redis.GetDatabase();
                try { await db.StreamCreateConsumerGroupAsync("stream:point-status", "ops", "0-0", createStream: true); }
                catch (RedisServerException ex) when (ex.Message.Contains("BUSYGROUP", StringComparison.Ordinal)) { }
                // Reclaim on every poll as well as startup, so a recently crashed consumer cannot strand pending work.
                var cursor = "0-0";
                do
                {
                    var claimed = await db.StreamAutoClaimAsync("stream:point-status", "ops", consumer, 60000, cursor, count: 100);
                    foreach (var entry in claimed.ClaimedEntries) await Process(db, entry, stoppingToken);
                    cursor = claimed.NextStartId.ToString();
                } while (cursor != "0-0" && !stoppingToken.IsCancellationRequested);
                var entries = await db.StreamReadGroupAsync("stream:point-status", "ops", consumer, ">", count: 100);
                foreach (var entry in entries) await Process(db, entry, stoppingToken);
                await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception) { SecurityLog.Event(log, "stream.processing_failed"); await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken); }
        }
    }
    private async Task Process(IDatabase redisDb, StreamEntry entry, CancellationToken ct)
    {
        try
        {
            var data = entry.Values.FirstOrDefault(x => x.Name == "data").Value;
            if (data.IsNull || data.ToString().Length > 16384) throw new ArgumentException("Invalid event size.");
            var e = JsonSerializer.Deserialize<PointStatusEvent>(data.ToString(), Wire.Json) ?? throw new ArgumentException("Missing event.");
            using var scope = scopes.CreateScope();
            var changed = await scope.ServiceProvider.GetRequiredService<StatusHandler>().Handle(e, ct);
            if (changed)
                await hub.Clients.Group("public").SendAsync("pointStatus", new
                { pointId = e.PointId, status = e.Current, waterDepthCm = e.WaterDepthCm, capturedAt = e.OccurredAt }, ct);
            await redisDb.StreamAcknowledgeAsync("stream:point-status", "ops", entry.Id);
        }
        catch (Exception ex) when (ex is JsonException or ArgumentException)
        {
            // Poison message: retrying cannot fix it. Park it in a dead-letter stream for investigation, then ack.
            SecurityLog.Event(log, "stream.validation_failed");
            await redisDb.StreamAddAsync("stream:point-status:dlq", entry.Values, maxLength: 10000, useApproximateMaxLength: true);
            await redisDb.StreamAcknowledgeAsync("stream:point-status", "ops", entry.Id);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Transient failure (e.g. DB): leave pending for XAUTOCLAIM retry without blocking the other entries.
            log.LogError(ex, "{event}", "stream.processing_failed");
        }
    }
}
public sealed class OutboxWorker(IConnectionMultiplexer redis, IServiceScopeFactory scopes, ILogger<OutboxWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        var delaySeconds = 1;
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var scope = scopes.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<OpsDb>();
                var rows = await db.Outbox.OrderBy(x => x.CreatedAt).Take(100).ToListAsync(ct);
                delaySeconds = rows.Count == 0 ? 2 : 1; // idle poll stays short: work order events feed the live dashboard
                foreach (var row in rows)
                {
                    await redis.GetSubscriber().PublishAsync(RedisChannel.Literal("events:ops"), row.Payload);
                    db.Outbox.Remove(row); await db.SaveChangesAsync(ct);
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception ex)
            {
                log.LogError(ex, "{event}", "outbox.publish_failed");
                delaySeconds = Math.Min(Math.Max(delaySeconds * 2, 5), 30);
            }
            await Task.Delay(TimeSpan.FromSeconds(delaySeconds), ct);
        }
    }
}
public sealed class LiveWorker(IConnectionMultiplexer redis, IHubContext<LiveHub> hub, ILogger<LiveWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            ChannelMessageQueue? telemetry = null; ChannelMessageQueue? ops = null;
            try
            {
                var subscriber = redis.GetSubscriber();
                telemetry = await subscriber.SubscribeAsync(RedisChannel.Literal("events:telemetry"));
                ops = await subscriber.SubscribeAsync(RedisChannel.Literal("events:ops"));
                telemetry.OnMessage(async message => await Forward(message.Message.ToString(), true, ct));
                ops.OnMessage(async message => await Forward(message.Message.ToString(), false, ct));
                await Task.Delay(Timeout.Infinite, ct);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception) { SecurityLog.Event(log, "realtime.subscribe_failed"); }
            finally
            {
                if (telemetry != null) await telemetry.UnsubscribeAsync();
                if (ops != null) await ops.UnsubscribeAsync();
            }
            await Task.Delay(TimeSpan.FromSeconds(5), ct);
        }
    }

    private async Task Forward(string raw, bool telemetry, CancellationToken ct)
    {
        try
        {
            if (raw.Length > 65536) return;
            using var document = JsonDocument.Parse(raw); var root = document.RootElement;
            var type = root.GetProperty("type").GetString();
            if (telemetry && type == "telemetry.reading")
            {
                await hub.Clients.Group("public").SendAsync("pointStatus", new
                {
                    pointId = root.GetProperty("pointId").GetString(), status = root.GetProperty("status").GetString(),
                    waterDepthCm = root.GetProperty("waterDepthCm").Clone(), capturedAt = root.GetProperty("capturedAt").GetString()
                }, ct);
                await hub.Clients.Group("ops").SendAsync("reading", root.Clone(), ct);
            }
            else if (!telemetry)
            {
                var method = type switch
                {
                    "alert.opened" or "alert.closed" => "alert",
                    "workorder.created" or "workorder.updated" => "workOrder",
                    "report.created" or "report.updated" => "report", _ => null
                };
                if (method != null) await hub.Clients.Group("ops").SendAsync(method, root.GetProperty("data").Clone(), ct);
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
        catch (Exception) { SecurityLog.Event(log, "realtime.forward_failed"); }
    }
}
