using AppService.Services.Domain;
using AppService.Services;
using AppService.Services.Infrastructure;
using AppService.Models;
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
        services.AddSingleton(TimeProvider.System);
        var ad = configuration.GetSection(AdOptions.SectionName).Get<AdOptions>() ?? new AdOptions();
        if (string.IsNullOrWhiteSpace(ad.Host) || ad.Port is < 1 or > 65535
            || string.IsNullOrWhiteSpace(ad.BaseDn) || string.IsNullOrWhiteSpace(ad.BindName)
            || string.IsNullOrWhiteSpace(ad.BindPassword) || string.IsNullOrWhiteSpace(ad.CertificatePath)
            || ad.TimeoutSeconds is < 1 or > 60)
            throw new InvalidOperationException("AD host, base DN, bind credentials, certificate and timeout must be configured.");
        services.AddSingleton(ad);
        services.AddSingleton(new AdCertificateValidator(ad.CertificatePath));
        services.AddSingleton<IAdIdentityProvider, LdapAdIdentityProvider>();

        var roleOptions = configuration.GetSection(RoleAccessOptions.SectionName).Get<RoleAccessOptions>()
            ?? new RoleAccessOptions();
        var roleAccess = new RoleAccessCatalog(roleOptions.Roles.Select(definition =>
            new RoleDefinition(definition.Code, definition.GroupDn, definition.Permissions)));
        services.AddSingleton(roleAccess);
        services.AddAppAuthorization(roleAccess);

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
