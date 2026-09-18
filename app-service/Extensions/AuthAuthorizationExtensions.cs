using AppService.Services.Domain;
using AppService.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Shared.Authentication;

namespace AppService.Extensions;

public static class AuthAuthorizationExtensions
{
    public static IServiceCollection AddAppAuthorization(this IServiceCollection services)
    {
        services.AddAuthorization(options =>
        {
            var authenticated = new AuthorizationPolicyBuilder(JwtBearerDefaults.AuthenticationScheme)
                .RequireAuthenticatedUser()
                .AddRequirements(new ActiveFamilyRequirement())
                .Build();
            options.DefaultPolicy = authenticated;
            options.FallbackPolicy = authenticated;

            options.AddPolicy(PermissionCodes.DemoAccess, new AuthorizationPolicyBuilder(JwtBearerDefaults.AuthenticationScheme)
                .RequireAuthenticatedUser()
                .AddRequirements(new ActiveFamilyRequirement())
                .RequireClaim(JwtClaimNames.Permission, PermissionCodes.DemoAccess)
                .Build());
        });
        services.AddScoped<IAuthorizationHandler, ActiveFamilyRequirementHandler>();
        return services;
    }
}
