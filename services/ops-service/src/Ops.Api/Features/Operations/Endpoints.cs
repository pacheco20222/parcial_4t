using System.Security.Claims;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Ops.Api.Auth;
using Ops.Api.Data;
using Ops.Api.Domain;
using Ops.Api.Messaging;

namespace Ops.Api.Features.Operations;

public static class Endpoints
{
    public record ReportInput(string? PointId, ReportCategory Category, string Description);
    public record OrderInput(string PointId, string Title, Priority Priority);
    public record AssignInput(Guid CrewId, Guid Version);
    public record TransitionInput(OrderStatus Status, Guid Version, string? Reason);
    public record LinkInput(Guid WorkOrderId);
    public record CrewInput(string Name, string Zone);
    public record UserInput(string Email, string Password, string Role);
    public record AlertInput(AlertStatus Status);
    private static int Size(int? limit) => Math.Clamp(limit ?? 50, 1, 100);
    private static int Offset(int? offset) => Math.Clamp(offset ?? 0, 0, 100000);
    private static bool Text(string? value, int max) => !string.IsNullOrWhiteSpace(value) && value.Length <= max;
    private static Guid? UserId(HttpContext http) => Guid.TryParse(http.User.FindFirstValue("sub"), out var id) ? id : null;
    private static void Audit(OpsDb db, HttpContext http, string action, Guid id)
    {
        db.Audit.Add(new AuditLog { UserId = UserId(http), Action = action, Entity = id.ToString(),
            At = DateTimeOffset.UtcNow, Ip = http.Connection.RemoteIpAddress?.ToString() ?? "" });
        SecurityLog.Event(http.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("Audit"), $"audit.{action}", http);
    }
    public static void MapOperations(this WebApplication app)
    {
        app.MapPost("/public/reports", async (ReportInput input, OpsDb db, Folios folios) =>
        {
            if (!Text(input.Description, 500) || !Enum.IsDefined(input.Category) || input.PointId != null && !StatusHandler.ValidPoint(input.PointId))
                return Results.BadRequest(new { error = "Valid category, optional pointId, and description (1–500 characters) required. Do not include personal data." });
            var report = new CitizenReport { Folio = await folios.Next(true), PointId = input.PointId,
                Category = input.Category, Description = input.Description.Trim(), ReportedAt = DateTimeOffset.UtcNow };
            db.Reports.Add(report); Wire.Enqueue(db, "report.created", report); await db.SaveChangesAsync();
            return Results.Created($"/reports/{report.Id}", new { report.Id, report.Folio, report.Status });
        }).RequireRateLimiting("reports");
        var alerts = app.MapGroup("/alerts").RequireAuthorization("Operator");
        alerts.MapGet("/", async (OpsDb db, AlertStatus? status, string? pointId, int? limit, int? offset) =>
        {
            if (status.HasValue && !Enum.IsDefined(status.Value)) return Results.BadRequest();
            var q = db.Alerts.AsNoTracking();
            if (status != null) q = q.Where(x => x.Status == status);
            if (pointId != null) q = q.Where(x => x.PointId == pointId);
            return Results.Ok(await q.OrderByDescending(x => x.OpenedAt).ThenBy(x => x.Id).Skip(Offset(offset)).Take(Size(limit)).ToListAsync());
        });
        alerts.MapGet("/{id:guid}", async (Guid id, OpsDb db) => await db.Alerts.AsNoTracking().SingleOrDefaultAsync(x => x.Id == id) is { } row ? Results.Ok(row) : Results.NotFound());
        alerts.MapPatch("/{id:guid}", async (Guid id, AlertInput input, OpsDb db, HttpContext http) =>
        {
            var row = await db.Alerts.FindAsync(id); if (row == null) return Results.NotFound();
            if (input.Status != AlertStatus.Closed || row.Status != AlertStatus.Open) return Results.BadRequest();
            row.Status = AlertStatus.Closed; row.ClosedAt = DateTimeOffset.UtcNow;
            Audit(db, http, "alert_close", id); Wire.Enqueue(db, "alert.closed", row); await db.SaveChangesAsync(); return Results.Ok(row);
        });
        var orders = app.MapGroup("/work-orders").RequireAuthorization("Operator");
        orders.MapGet("/", async (OpsDb db, OrderStatus? status, Priority? priority, string? pointId, Guid? crewId, bool? overdue, int? limit, int? offset) =>
        {
            if (status.HasValue && !Enum.IsDefined(status.Value) || priority.HasValue && !Enum.IsDefined(priority.Value)) return Results.BadRequest();
            var q = db.WorkOrders.AsNoTracking(); var now = DateTimeOffset.UtcNow;
            if (status != null) q = q.Where(x => x.Status == status);
            if (priority != null) q = q.Where(x => x.Priority == priority);
            if (pointId != null) q = q.Where(x => x.PointId == pointId);
            if (crewId != null) q = q.Where(x => x.CrewId == crewId);
            if (overdue.HasValue) q = overdue.Value
                ? q.Where(x => now > x.SlaDueAt && x.Status != OrderStatus.Resolved && x.Status != OrderStatus.Closed && x.Status != OrderStatus.Cancelled)
                : q.Where(x => now <= x.SlaDueAt || x.Status == OrderStatus.Resolved || x.Status == OrderStatus.Closed || x.Status == OrderStatus.Cancelled);
            return Results.Ok(await q.OrderByDescending(x => x.CreatedAt).ThenBy(x => x.Id).Skip(Offset(offset)).Take(Size(limit)).ToListAsync());
        });
        orders.MapGet("/{id:guid}", async (Guid id, OpsDb db) => await db.WorkOrders.AsNoTracking().SingleOrDefaultAsync(x => x.Id == id) is { } row ? Results.Ok(row) : Results.NotFound());
        orders.MapPost("/", async (OrderInput input, OpsDb db, Folios folios, HttpContext http) =>
        {
            if (!StatusHandler.ValidPoint(input.PointId) || !Text(input.Title, 200) || !Enum.IsDefined(input.Priority)) return Results.BadRequest();
            var now = DateTimeOffset.UtcNow;
            var order = new WorkOrder { Folio = await folios.Next(), PointId = input.PointId, Title = input.Title.Trim(),
                Priority = input.Priority, CreatedAt = now, SlaDueAt = now + WorkOrder.Sla(input.Priority) };
            db.WorkOrders.Add(order); Audit(db, http, "workorder_create", order.Id); Wire.Enqueue(db, "workorder.created", order);
            await db.SaveChangesAsync(); return Results.Created($"/work-orders/{order.Id}", order);
        }).RequireAuthorization("Supervisor");
        orders.MapPatch("/{id:guid}/assign", async (Guid id, AssignInput input, OpsDb db, HttpContext http) =>
        {
            var order = await db.WorkOrders.FindAsync(id); if (order == null) return Results.NotFound();
            if (order.Version != input.Version) return Results.Conflict(new { error = "Order changed. Reload before updating." });
            if (!await db.Crews.AnyAsync(x => x.Id == input.CrewId && x.Available)) return Results.BadRequest(new { error = "Available crew required." });
            order.Assign(input.CrewId, true, DateTimeOffset.UtcNow);
            Audit(db, http, "workorder_assign", id); Wire.Enqueue(db, "workorder.updated", order); await db.SaveChangesAsync(); return Results.Ok(order);
        }).RequireAuthorization("Supervisor");
        orders.MapPatch("/{id:guid}/transition", async (Guid id, TransitionInput input, OpsDb db, HttpContext http) =>
        {
            var order = await db.WorkOrders.FindAsync(id); if (order == null) return Results.NotFound();
            if (order.Version != input.Version) return Results.Conflict(new { error = "Order changed. Reload before updating." });
            if (input.Status is OrderStatus.Closed or OrderStatus.Cancelled && !Roles.Supervisor(http.User)) return Results.Forbid();
            order.Transition(input.Status, Roles.Supervisor(http.User), input.Reason, DateTimeOffset.UtcNow);
            Audit(db, http, input.Status == OrderStatus.Cancelled ? "workorder_cancel" : "workorder_transition", id);
            Wire.Enqueue(db, "workorder.updated", order); await db.SaveChangesAsync(); return Results.Ok(order);
        });
        var reports = app.MapGroup("/reports").RequireAuthorization("Operator");
        reports.MapGet("/", async (OpsDb db, ReportStatus? status, string? pointId, int? limit, int? offset) =>
        {
            if (status.HasValue && !Enum.IsDefined(status.Value)) return Results.BadRequest();
            var q = db.Reports.AsNoTracking(); if (status != null) q = q.Where(x => x.Status == status);
            if (pointId != null) q = q.Where(x => x.PointId == pointId);
            return Results.Ok(await q.OrderByDescending(x => x.ReportedAt).ThenBy(x => x.Id).Skip(Offset(offset)).Take(Size(limit)).ToListAsync());
        });
        reports.MapGet("/{id:guid}", async (Guid id, OpsDb db) => await db.Reports.AsNoTracking().SingleOrDefaultAsync(x => x.Id == id) is { } row ? Results.Ok(row) : Results.NotFound());
        reports.MapPatch("/{id:guid}/validate", async (Guid id, OpsDb db, HttpContext http) => await ReviewReport(id, ReportStatus.Validated, db, http));
        reports.MapPatch("/{id:guid}/reject", async (Guid id, OpsDb db, HttpContext http) => await ReviewReport(id, ReportStatus.Rejected, db, http));
        reports.MapPatch("/{id:guid}/link", async (Guid id, LinkInput input, OpsDb db, HttpContext http) =>
        {
            var report = await db.Reports.FindAsync(id); if (report == null) return Results.NotFound();
            if (report.Status != ReportStatus.Validated || report.LinkedWorkOrderId != null) return Results.Conflict();
            var order = await db.WorkOrders.FindAsync(input.WorkOrderId);
            if (order == null || report.PointId != null && report.PointId != order.PointId) return Results.BadRequest();
            report.LinkedWorkOrderId = input.WorkOrderId; Audit(db, http, "report_link", id);
            Wire.Enqueue(db, "report.updated", report); await db.SaveChangesAsync(); return Results.Ok(report);
        });
        var crews = app.MapGroup("/crews").RequireAuthorization("Supervisor");
        crews.MapGet("/", async (OpsDb db, int? limit, int? offset) => Results.Ok(await db.Crews.AsNoTracking().OrderBy(x => x.Name).ThenBy(x => x.Id).Skip(Offset(offset)).Take(Size(limit)).ToListAsync()));
        crews.MapPost("/", async (CrewInput input, OpsDb db, HttpContext http) =>
        {
            if (!Text(input.Name, 100) || !Text(input.Zone, 100)) return Results.BadRequest();
            var crew = new Crew { Name = input.Name.Trim(), Zone = input.Zone.Trim() }; db.Crews.Add(crew);
            Audit(db, http, "crew_create", crew.Id); await db.SaveChangesAsync(); return Results.Created($"/crews/{crew.Id}", crew);
        });
        app.MapGet("/kpis", Kpis).RequireAuthorization("Operator");
        var users = app.MapGroup("/users").RequireAuthorization("Admin");
        users.MapGet("/", async (OpsDb db, int? limit, int? offset) =>
        {
            var page = await db.Users.AsNoTracking().OrderBy(x => x.Email).Skip(Offset(offset)).Take(Size(limit))
                .Select(x => new { x.Id, x.Email, mfaEnabled = x.TwoFactorEnabled }).ToListAsync();
            var ids = page.Select(x => x.Id).ToArray();
            var roles = await (from ur in db.UserRoles join r in db.Roles on ur.RoleId equals r.Id
                where ids.Contains(ur.UserId) select new { ur.UserId, r.Name }).ToListAsync();
            return Results.Ok(page.Select(x => new { x.Id, x.Email, x.mfaEnabled, roles = roles.Where(r => r.UserId == x.Id).Select(r => r.Name) }));
        });
        users.MapPost("/", async (UserInput input, UserManager<AppUser> manager, OpsDb db, HttpContext http) =>
        {
            if (!Roles.All.Contains(input.Role) || !Text(input.Email, 254) || !System.Net.Mail.MailAddress.TryCreate(input.Email, out var email)
                || email.Address != input.Email || input.Password is not { Length: >= 12 and <= 1024 }) return Results.BadRequest();
            await using var tx = db.Database.IsRelational() ? await db.Database.BeginTransactionAsync() : null;
            var user = new AppUser { Id = Guid.NewGuid(), UserName = input.Email, Email = input.Email };
            var result = await manager.CreateAsync(user, input.Password);
            if (!result.Succeeded) return Results.BadRequest(new { errors = result.Errors.Select(x => x.Code) });
            var role = await manager.AddToRoleAsync(user, input.Role);
            if (!role.Succeeded) throw new InvalidOperationException("Unable to assign role.");
            Audit(db, http, "user_create", user.Id); await db.SaveChangesAsync(); if (tx != null) await tx.CommitAsync();
            return Results.Created($"/users/{user.Id}", new { user.Id, user.Email, role = input.Role });
        });
        app.MapGet("/audit", async (OpsDb db, int? limit, int? offset) => Results.Ok(await db.Audit.AsNoTracking()
            .OrderByDescending(x => x.At).ThenByDescending(x => x.Id).Skip(Offset(offset)).Take(Size(limit)).ToListAsync())).RequireAuthorization("Admin");
    }
    private static async Task<IResult> ReviewReport(Guid id, ReportStatus status, OpsDb db, HttpContext http)
    {
        var report = await db.Reports.FindAsync(id); if (report == null) return Results.NotFound();
        if (report.Status != ReportStatus.Pending) return Results.Conflict();
        report.Status = status; Audit(db, http, status == ReportStatus.Validated ? "report_validate" : "report_reject", id);
        Wire.Enqueue(db, "report.updated", report); await db.SaveChangesAsync(); return Results.Ok(report);
    }
    private static async Task<IResult> Kpis(OpsDb db)
    {
        var now = DateTimeOffset.UtcNow; var since = now.AddDays(-7);
        var active = db.WorkOrders.AsNoTracking().Where(x => x.Status != OrderStatus.Resolved && x.Status != OrderStatus.Closed && x.Status != OrderStatus.Cancelled);
        var counts = await active.GroupBy(x => x.Priority).Select(g => new { priority = g.Key, count = g.Count() }).ToListAsync();
        // Aggregate in PostgreSQL, keeping response-time history bounded by date without materializing orders.
        var response = from w in db.WorkOrders join a in db.Alerts on w.AlertId equals a.Id
            where w.OnSiteAt >= since && w.OnSiteAt <= now select (w.OnSiteAt!.Value - a.OpenedAt).TotalMinutes;
        var avg = await response.Select(x => (double?)x).AverageAsync();
        return Results.Ok(new { openOrders = counts.Sum(x => x.count), overdue = await active.CountAsync(x => now > x.SlaDueAt),
            byPriority = counts, avgMinutesAlertToOnSiteLast7Days = avg,
            openAlertsByLevel = await db.Alerts.Where(x => x.Status == AlertStatus.Open).GroupBy(x => x.Level).Select(g => new { level = g.Key, count = g.Count() }).ToListAsync() });
    }
}
