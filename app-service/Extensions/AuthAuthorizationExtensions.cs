using AppService.Services.Domain;
using AppService.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Shared.Authentication;

namespace AppService.Extensions;

public static class AuthAuthorizationExtensions
{
    public static IServiceCollection AddAppAuthorization(
        this IServiceCollection services, RoleAccessCatalog roleAccess)
    {
        services.AddAuthorization(options =>
        {
            var authenticated = new AuthorizationPolicyBuilder(JwtBearerDefaults.AuthenticationScheme)
                .RequireAuthenticatedUser()
                .AddRequirements(new ActiveFamilyRequirement())
                .Build();
            options.DefaultPolicy = authenticated;
            options.FallbackPolicy = authenticated;

            foreach (var permission in roleAccess.AllPermissions)
            {
                options.AddPolicy(permission, new AuthorizationPolicyBuilder(JwtBearerDefaults.AuthenticationScheme)
                    .RequireAuthenticatedUser()
                    .AddRequirements(new ActiveFamilyRequirement())
                    .RequireClaim(JwtClaimNames.Permission, permission)
                    .Build());
            }
        });
        services.AddScoped<IAuthorizationHandler, ActiveFamilyRequirementHandler>();
        return services;
    }
}
