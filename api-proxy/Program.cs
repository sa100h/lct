using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Shared.Authentication;
using Shared.Observability;

namespace ApiProxy;

public static class Program
{
    public static void Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);
        builder.AddSharedObservability("api-proxy");
        builder.Services.AddHttpsRedirection(options =>
            options.RedirectStatusCode = StatusCodes.Status308PermanentRedirect);
        builder.Services.AddSharedJwtAuthentication(builder.Configuration);
        builder.Services.AddAuthorization(options =>
        {
            options.DefaultPolicy = new AuthorizationPolicyBuilder(JwtBearerDefaults.AuthenticationScheme)
                .RequireAuthenticatedUser().Build();
            options.FallbackPolicy = options.DefaultPolicy;
        });
        builder.Services.AddReverseProxy().LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"));

        var app = builder.Build();
        app.UseHttpsRedirection();
        app.UseDefaultFiles();
        app.UseStaticFiles();
        app.UseSharedObservability();
        app.UseAuthentication();
        app.UseAuthorization();
        app.MapReverseProxy();
        app.MapFallbackToFile("index.html").AllowAnonymous();
        app.Run();
    }
}
