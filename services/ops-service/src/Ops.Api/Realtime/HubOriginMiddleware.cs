namespace Ops.Api.Realtime;

public sealed class HubOriginMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context)
    {
        var request = context.Request;
        if (request.Path.StartsWithSegments("/hubs") && request.Headers.TryGetValue("Origin", out var origins))
        {
            if (origins.Count != 1 || !Uri.TryCreate(origins[0], UriKind.Absolute, out var origin)
                || (origin.Scheme != "https" && origin.Scheme != "http")
                || origin.UserInfo.Length != 0 || origin.AbsolutePath != "/"
                || origin.Query.Length != 0 || origin.Fragment.Length != 0
                || !string.Equals(origin.Scheme, request.Scheme, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(origin.Host, request.Host.Host, StringComparison.OrdinalIgnoreCase)
                || origin.Port != (request.Host.Port ?? (request.IsHttps ? 443 : 80)))
            {
                context.Response.StatusCode = StatusCodes.Status403Forbidden;
                return;
            }
        }
        await next(context);
    }
}
