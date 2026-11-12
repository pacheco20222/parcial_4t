using Ops.Api.Domain;
using Ops.Api.Messaging;

namespace Ops.Api.Tests;

public class DomainTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-11-12T00:00:00Z");
    [Theory]
    [InlineData(Priority.Critical, 30)] [InlineData(Priority.High, 120)]
    [InlineData(Priority.Medium, 480)] [InlineData(Priority.Low, 1440)]
    public void SlaMatchesContract(Priority priority, int minutes) => Assert.Equal(minutes, WorkOrder.Sla(priority).TotalMinutes);
    [Fact]
    public void FullLifecycleSetsTimestampsAndVersion()
    {
        var order = new WorkOrder(); var version = order.Version;
        order.Assign(Guid.NewGuid(), true, Now); Assert.Equal(Now, order.AssignedAt); Assert.NotEqual(version, order.Version);
        order.Transition(OrderStatus.InProgress, false, null, Now.AddMinutes(1)); Assert.Equal(Now.AddMinutes(1), order.OnSiteAt);
        order.Transition(OrderStatus.Resolved, false, null, Now.AddMinutes(2)); Assert.Equal(Now.AddMinutes(2), order.ResolvedAt);
        order.Transition(OrderStatus.Closed, true, null, Now.AddMinutes(3)); Assert.Equal(Now.AddMinutes(3), order.ClosedAt);
    }
    [Fact]
    public void AssignmentRequiresSupervisor() => Assert.Throws<UnauthorizedAccessException>(() => new WorkOrder().Assign(Guid.NewGuid(), false, Now));
    [Theory]
    [InlineData(OrderStatus.Open, OrderStatus.InProgress)] [InlineData(OrderStatus.Open, OrderStatus.Closed)]
    [InlineData(OrderStatus.Assigned, OrderStatus.Resolved)] [InlineData(OrderStatus.Closed, OrderStatus.Open)]
    [InlineData(OrderStatus.InProgress, OrderStatus.Cancelled)] [InlineData(OrderStatus.Cancelled, OrderStatus.Assigned)]
    public void InvalidTransitionsFail(OrderStatus from, OrderStatus to) => Assert.Throws<ArgumentException>(() => new WorkOrder { Status = from }.Transition(to, true, "reason", Now));
    [Theory]
    [InlineData(null)] [InlineData("")] [InlineData("   ")]
    public void CancelRequiresReason(string? reason) => Assert.Throws<ArgumentException>(() => new WorkOrder().Transition(OrderStatus.Cancelled, true, reason, Now));
    [Theory]
    [InlineData(OrderStatus.Open, OrderStatus.Cancelled)] [InlineData(OrderStatus.Resolved, OrderStatus.Closed)]
    public void PrivilegedTransitionsRequireSupervisor(OrderStatus from, OrderStatus target) => Assert.Throws<UnauthorizedAccessException>(() => new WorkOrder { Status = from }.Transition(target, false, "reason", Now));
    [Fact]
    public void CancelTrimsReason()
    {
        var order = new WorkOrder(); order.Transition(OrderStatus.Cancelled, true, " false alarm ", Now);
        Assert.Equal("false alarm", order.CancelReason); Assert.Equal(OrderStatus.Cancelled, order.Status);
    }
    [Theory]
    [InlineData(OrderStatus.Open, true)] [InlineData(OrderStatus.Assigned, true)] [InlineData(OrderStatus.InProgress, true)]
    [InlineData(OrderStatus.Resolved, false)] [InlineData(OrderStatus.Closed, false)] [InlineData(OrderStatus.Cancelled, false)]
    public void OverdueExcludesTerminalOrders(OrderStatus status, bool expected) => Assert.Equal(expected, new WorkOrder { Status = status, SlaDueAt = Now }.IsOverdue(Now.AddSeconds(1)));
    [Fact]
    public void DueInstantNotOverdue() => Assert.False(new WorkOrder { SlaDueAt = Now }.IsOverdue(Now));
    [Theory]
    [InlineData("Alert", 44.9, 30.0, Priority.High)] [InlineData("Alert", 45.0, 30.0, Priority.Critical)]
    [InlineData("Alert", null, 30.0, Priority.High)] [InlineData("Alert", 30.0, 20.0, Priority.Critical)]
    [InlineData("NoData", null, 30.0, Priority.Medium)] [InlineData("Watch", 15.0, 30.0, Priority.Low)]
    public void EventPriorities(string status, double? depth, double threshold, Priority expected) => Assert.Equal(expected, StatusHandler.EventPriority(status, depth, threshold));
}
