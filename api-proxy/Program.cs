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
        builder.Services.AddReverseProxy().LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"));

        var app = builder.Build();
        app.UseHttpsRedirection();
        app.UseDefaultFiles();
        app.UseStaticFiles();
        app.UseSharedObservability();
        app.MapReverseProxy();
        app.MapFallbackToFile("index.html");
        app.Run();
    }
}
