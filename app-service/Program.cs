using AppService.Contracts;
using AppService.Ml;
using Shared.DatabaseMigration;
using Shared.Observability;

namespace AppService;

public partial class Program
{
    public static async Task Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);
        builder.AddSharedObservability("app-service");
        builder.Services.AddSingleton<PostgresMigrator>();

        var connectionString = builder.Configuration.GetConnectionString("AppDb")
            ?? throw new InvalidOperationException("Connection string 'AppDb' is required.");
        builder.Services.AddHealthChecks().AddNpgSql(connectionString, name: "postgres");

        // ml-service (FastAPI) client: http://ml-service:8000 in Docker,
        // override via MlService__BaseUrl for local development.
        var mlBaseUrl = builder.Configuration["MlService:BaseUrl"] ?? "http://localhost:8000";
        builder.Services.AddHttpClient<MlServiceClient>(client => client.BaseAddress = new Uri(mlBaseUrl));

        var app = builder.Build();
        var migrationsPath = builder.Configuration["Migrations:Path"];
        if (!string.IsNullOrWhiteSpace(migrationsPath))
        {
            await app.Services.GetRequiredService<PostgresMigrator>()
                .MigrateAsync(connectionString, migrationsPath, app.Lifetime.ApplicationStopping);
        }

        app.UseSharedObservability();
        app.MapGet("/status", () => Results.Ok(new ServiceStatusResponse("app-service", "ready")))
            .WithName("GetServiceStatus");

        app.MapPost("/predict", async (PredictRequest request, MlServiceClient ml, CancellationToken ct) =>
            {
                try
                {
                    return Results.Ok(await ml.PredictAsync(request, ct));
                }
                catch (ArgumentException ex)
                {
                    return Results.BadRequest(new { error = ex.Message });
                }
                catch (HttpRequestException ex)
                {
                    return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status502BadGateway);
                }
            })
            .WithName("CreatePrediction")
            .DisableAntiforgery();

        app.MapGet("/ml/status", async (MlServiceClient ml, CancellationToken ct) =>
            {
                try
                {
                    return Results.Ok(await ml.GetStatusAsync(ct));
                }
                catch (HttpRequestException ex)
                {
                    return Results.Json(new { error = ex.Message }, statusCode: StatusCodes.Status502BadGateway);
                }
            })
            .WithName("GetMlStatus");

        await app.RunAsync();
    }
}
