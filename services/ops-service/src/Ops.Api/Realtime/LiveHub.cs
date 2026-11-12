using Microsoft.AspNetCore.SignalR;
using Ops.Api.Auth;

namespace Ops.Api.Realtime;

public sealed class LiveHub(IConfiguration config) : Hub
{
    public override async Task OnConnectedAsync()
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, "public");
        if (Context.User != null && Roles.Allows(Context.User, "Operator", config.GetValue("Security:EnforceMfa", false)))
            await Groups.AddToGroupAsync(Context.ConnectionId, "ops");
        await base.OnConnectedAsync();
    }
}
