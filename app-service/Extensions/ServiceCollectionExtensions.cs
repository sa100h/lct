using AppService.Services.Domain;
using AppService.Services;
using AppService.Data.Repositories;
using Shared.Authentication;
using Shared.DatabaseMigration;

namespace AppService.Extensions;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddApplicationServices(this IServiceCollection services, IConfiguration configuration)
    {
        var connectionString = configuration.GetConnectionString("AppDb")
            ?? throw new InvalidOperationException("Connection string 'AppDb' is required.");

        services.AddSharedJwtAuthentication(configuration, requirePrivateKey: true);
        services.AddAppAuthorization();
        services.AddSingleton(TimeProvider.System);
        services.AddSingleton<IAdIdentityProvider, UnavailableAdIdentityProvider>();

        var groups = configuration.GetSection("AdGroups").Get<AdGroupOptions>() ?? new AdGroupOptions();
        services.AddSingleton(new DirectoryRoleMapper(groups));

        var cookie = configuration.GetSection("AuthCookie").Get<AuthCookieOptions>() ?? new AuthCookieOptions();
        if (string.IsNullOrWhiteSpace(cookie.Name) || !cookie.Path.StartsWith('/'))
            throw new InvalidOperationException("AuthCookie name and absolute path must be configured.");
        services.AddSingleton(cookie);

        services.AddSingleton<IAuthRepository>(_ => new NpgsqlAuthRepository(connectionString));
        services.AddSingleton<ITokenIssuer, JwtTokenIssuer>();
        services.AddScoped<IAuthSessionService, AuthSessionService>();
        services.AddSingleton<PostgresMigrator>();
        services.AddHostedService<AppMigrationHostedService>();
        services.AddHealthChecks().AddNpgSql(connectionString, name: "postgres");

        var mlBaseUrl = configuration["MlService:BaseUrl"] ?? "http://localhost:8000";
        services.AddHttpClient<IMlServiceClient, MlServiceClient>(client => client.BaseAddress = new Uri(mlBaseUrl));
        return services;
    }
}
