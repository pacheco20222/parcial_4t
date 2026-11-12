using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Ops.Api.Domain;

namespace Ops.Api.Data;

public sealed class OpsDb(DbContextOptions<OpsDb> options) : IdentityDbContext<AppUser, IdentityRole<Guid>, Guid>(options)
{
    public DbSet<Alert> Alerts => Set<Alert>();
    public DbSet<WorkOrder> WorkOrders => Set<WorkOrder>();
    public DbSet<Crew> Crews => Set<Crew>();
    public DbSet<CitizenReport> Reports => Set<CitizenReport>();
    public DbSet<AuditLog> Audit => Set<AuditLog>();
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();
    public DbSet<ProcessedEvent> ProcessedEvents => Set<ProcessedEvent>();
    public DbSet<OutboxMessage> Outbox => Set<OutboxMessage>();
    protected override void OnModelCreating(ModelBuilder b)
    {
        base.OnModelCreating(b);
        b.HasDefaultSchema("ops");
        b.HasSequence<long>("work_order_seq", "ops");
        b.HasSequence<long>("citizen_report_seq", "ops");
        b.Entity<Alert>().ToTable("alert").HasIndex(x => x.SourceEventId).IsUnique();
        b.Entity<Alert>().HasIndex(x => new { x.PointId, x.Status });
        b.Entity<WorkOrder>().ToTable("work_order").HasIndex(x => x.Folio).IsUnique();
        b.Entity<WorkOrder>().Property(x => x.Version).IsConcurrencyToken();
        b.Entity<WorkOrder>().HasOne<Alert>().WithMany().HasForeignKey(x => x.AlertId).OnDelete(DeleteBehavior.Restrict);
        b.Entity<WorkOrder>().HasOne<Crew>().WithMany().HasForeignKey(x => x.CrewId).OnDelete(DeleteBehavior.Restrict);
        b.Entity<WorkOrder>().HasOne<CitizenReport>().WithMany().HasForeignKey(x => x.CitizenReportId).OnDelete(DeleteBehavior.Restrict);
        b.Entity<WorkOrder>().HasIndex(x => new { x.Status, x.SlaDueAt });
        b.Entity<Crew>().ToTable("crew");
        b.Entity<CitizenReport>().ToTable("citizen_report").HasIndex(x => x.Folio).IsUnique();
        b.Entity<CitizenReport>().Property(x => x.Description).HasMaxLength(500);
        b.Entity<CitizenReport>().HasOne<WorkOrder>().WithMany().HasForeignKey(x => x.LinkedWorkOrderId).OnDelete(DeleteBehavior.Restrict);
        b.Entity<AuditLog>().ToTable("audit_log").HasIndex(x => x.At);
        b.Entity<RefreshToken>().ToTable("refresh_token").HasKey(x => x.Hash);
        b.Entity<RefreshToken>().HasIndex(x => x.Family);
        b.Entity<RefreshToken>().Property(x => x.Version).IsConcurrencyToken();
        b.Entity<RefreshToken>().HasOne<AppUser>().WithMany().HasForeignKey(x => x.UserId);
        b.Entity<ProcessedEvent>().ToTable("processed_event").HasKey(x => x.EventId);
        b.Entity<OutboxMessage>().ToTable("outbox_message");
        foreach (var entity in b.Model.GetEntityTypes())
        foreach (var property in entity.GetProperties())
            if (property.ClrType.IsEnum) property.SetProviderClrType(typeof(string));
        b.Entity<Crew>().HasData(
            new Crew { Id = Guid.Parse("00000000-0000-0000-0000-000000000001"), Name = "Cuadrilla Centro", Zone = "Centro" },
            new Crew { Id = Guid.Parse("00000000-0000-0000-0000-000000000002"), Name = "Cuadrilla Norte", Zone = "Norte" },
            new Crew { Id = Guid.Parse("00000000-0000-0000-0000-000000000003"), Name = "Cuadrilla Sur", Zone = "Sur" });
    }
}
public sealed class DesignFactory : IDesignTimeDbContextFactory<OpsDb>
{
    public OpsDb CreateDbContext(string[] args) => new(new DbContextOptionsBuilder<OpsDb>()
        .UseNpgsql("Host=localhost;Database=flood;Username=ops_svc", o => o.MigrationsHistoryTable("__EFMigrationsHistory", "ops")).Options);
}
public sealed class Folios(OpsDb db)
{
    private static long testSequence;
    public async Task<string> Next(bool report = false)
    {
        // Sequence names are fixed literals; no input enters SQL.
        var number = db.Database.IsRelational()
            ? (report ? await db.Database.SqlQueryRaw<long>("SELECT nextval('ops.citizen_report_seq') AS \"Value\"").SingleAsync()
                : await db.Database.SqlQueryRaw<long>("SELECT nextval('ops.work_order_seq') AS \"Value\"").SingleAsync())
            : Interlocked.Increment(ref testSequence);
        return $"{(report ? "RC" : "OT")}-{DateTimeOffset.UtcNow.Year}-{number:D5}";
    }
}
