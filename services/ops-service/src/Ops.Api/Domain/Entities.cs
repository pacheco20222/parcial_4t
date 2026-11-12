using Microsoft.AspNetCore.Identity;

namespace Ops.Api.Domain;

public enum AlertLevel { Watch, Alert, DataGap }
public enum AlertStatus { Open, Closed }
public enum OrderStatus { Open, Assigned, InProgress, Resolved, Closed, Cancelled }
public enum Priority { Low, Medium, High, Critical }
public enum ReportCategory { Encharcamiento, CalleIntransitable, DrenajeTapado, Otro }
public enum ReportStatus { Pending, Validated, Rejected }
public sealed class AppUser : IdentityUser<Guid> { }
public sealed class Alert
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid SourceEventId { get; set; }
    public string PointId { get; set; } = "";
    public string PointName { get; set; } = "";
    public string Zone { get; set; } = "";
    public AlertLevel Level { get; set; }
    public AlertStatus Status { get; set; }
    public DateTimeOffset OpenedAt { get; set; }
    public DateTimeOffset? ClosedAt { get; set; }
    public string Reason { get; set; } = "";
    public double? DepthCm { get; set; }
}
public sealed class WorkOrder
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Folio { get; set; } = "";
    public Guid? AlertId { get; set; }
    public Guid? CitizenReportId { get; set; }
    public string PointId { get; set; } = "";
    public string Title { get; set; } = "";
    public OrderStatus Status { get; set; }
    public Priority Priority { get; set; }
    public Guid? CrewId { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset SlaDueAt { get; set; }
    public DateTimeOffset? AssignedAt { get; set; }
    public DateTimeOffset? OnSiteAt { get; set; }
    public DateTimeOffset? ResolvedAt { get; set; }
    public DateTimeOffset? ClosedAt { get; set; }
    public string? CancelReason { get; set; }
    public Guid Version { get; set; } = Guid.NewGuid();
    public bool IsOverdue(DateTimeOffset now) => now > SlaDueAt && Status is not (OrderStatus.Resolved or OrderStatus.Closed or OrderStatus.Cancelled);
    public static TimeSpan Sla(Priority priority) => priority switch
    {
        Priority.Critical => TimeSpan.FromMinutes(30), Priority.High => TimeSpan.FromHours(2),
        Priority.Medium => TimeSpan.FromHours(8), Priority.Low => TimeSpan.FromHours(24),
        _ => throw new ArgumentException("Invalid priority.")
    };
    public void Assign(Guid crewId, bool supervisor, DateTimeOffset now)
    {
        if (!supervisor) throw new UnauthorizedAccessException();
        if (Status != OrderStatus.Open || crewId == Guid.Empty) throw new ArgumentException("Only open orders can be assigned to a crew.");
        CrewId = crewId; Status = OrderStatus.Assigned; AssignedAt = now; Version = Guid.NewGuid();
    }
    public void Transition(OrderStatus target, bool supervisor, string? reason, DateTimeOffset now)
    {
        if (target is OrderStatus.Closed or OrderStatus.Cancelled && !supervisor) throw new UnauthorizedAccessException();
        var allowed = (Status, target) is (OrderStatus.Assigned, OrderStatus.InProgress)
            or (OrderStatus.InProgress, OrderStatus.Resolved) or (OrderStatus.Resolved, OrderStatus.Closed)
            or (OrderStatus.Open, OrderStatus.Cancelled);
        if (!allowed) throw new ArgumentException("Invalid work order transition.");
        if (target == OrderStatus.Cancelled && (string.IsNullOrWhiteSpace(reason) || reason.Length > 500))
            throw new ArgumentException("Cancellation requires a reason of at most 500 characters.");
        Status = target; Version = Guid.NewGuid();
        if (target == OrderStatus.InProgress) OnSiteAt = now;
        if (target == OrderStatus.Resolved) ResolvedAt = now;
        if (target == OrderStatus.Closed) ClosedAt = now;
        if (target == OrderStatus.Cancelled) CancelReason = reason!.Trim();
    }
}
public sealed class Crew
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Name { get; set; } = "";
    public string Zone { get; set; } = "";
    public bool Available { get; set; } = true;
}
public sealed class CitizenReport
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Folio { get; set; } = "";
    public string? PointId { get; set; }
    public ReportCategory Category { get; set; }
    public string Description { get; set; } = "";
    public ReportStatus Status { get; set; }
    public DateTimeOffset ReportedAt { get; set; }
    public Guid? LinkedWorkOrderId { get; set; }
}
public sealed class AuditLog
{
    public long Id { get; set; }
    public Guid? UserId { get; set; }
    public string Action { get; set; } = "";
    public string Entity { get; set; } = "";
    public DateTimeOffset At { get; set; }
    public string Ip { get; set; } = "";
}
public sealed class RefreshToken
{
    public string Hash { get; set; } = "";
    public Guid UserId { get; set; }
    public DateTimeOffset Expires { get; set; }
    public DateTimeOffset? Revoked { get; set; }
    public string? ReplacedBy { get; set; }
    public Guid Family { get; set; }
    public string Amr { get; set; } = "pwd";
    public Guid Version { get; set; } = Guid.NewGuid();
}
public sealed class ProcessedEvent
{
    public Guid EventId { get; set; }
    public DateTimeOffset ProcessedAt { get; set; }
}
// Durable publication after business commit. A crash may duplicate delivery, never lose it.
public sealed class OutboxMessage
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Payload { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
