using AppService.Extensions;
using Shared.Observability;

namespace AppService;

public partial class Program
{
    public static async Task Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);
        builder.AddSharedObservability("app-service");
        builder.Services.AddControllers();
        builder.Services.AddProblemDetails();
        builder.Services.AddApplicationServices(builder.Configuration);

        var app = builder.Build();

        app.UseSharedObservability();
        app.UseAuthentication();
        app.UseAuthorization();
        app.MapControllers();
        app.ValidatePermissionPolicies();

        await app.RunAsync();
    }
}
