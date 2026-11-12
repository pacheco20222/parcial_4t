using Microsoft.AspNetCore.Identity;
using Ops.Api.Auth;
using Ops.Api.Domain;

namespace Ops.Api.Data;

public static class Seeder
{
    public static async Task Seed(IServiceProvider services, IConfiguration config)
    {
        var roles = services.GetRequiredService<RoleManager<IdentityRole<Guid>>>();
        var users = services.GetRequiredService<UserManager<AppUser>>();
        foreach (var role in Roles.All)
        {
            if (!await roles.RoleExistsAsync(role))
            {
                var result = await roles.CreateAsync(new IdentityRole<Guid>(role));
                if (!result.Succeeded) throw new InvalidOperationException("Role seed failed.");
            }
            var path = config[$"Seed:{role}PasswordFile"];
            if (path == null || !File.Exists(path)) continue;
            var email = $"{role.ToLowerInvariant()}@flood.local";
            if (await users.FindByEmailAsync(email) != null) continue;
            var user = new AppUser { Id = Guid.NewGuid(), UserName = email, Email = email };
            var created = await users.CreateAsync(user, Secrets.Read(config, $"Seed:{role}PasswordFile"));
            if (!created.Succeeded) throw new InvalidOperationException($"Seed password for {role} does not satisfy policy.");
            if (!(await users.AddToRoleAsync(user, role)).Succeeded) throw new InvalidOperationException("Role seed failed.");
        }
    }
}
