using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Routing;

namespace AppService.Extensions;

public static class PermissionPolicyValidationExtensions
{
    public static WebApplication ValidatePermissionPolicies(this WebApplication app)
    {
        var catalog = app.Services.GetRequiredService<RoleAccessCatalog>();
        EnsureConfigured(((IEndpointRouteBuilder)app).DataSources
            .SelectMany(source => source.Endpoints), catalog);
        return app;
    }

    public static void EnsureConfigured(IEnumerable<Endpoint> endpoints, RoleAccessCatalog catalog)
    {
        var configured = catalog.AllPermissions.ToHashSet(StringComparer.Ordinal);
        var missing = endpoints
            .SelectMany(endpoint => endpoint.Metadata.GetOrderedMetadata<IAuthorizeData>()
                .Where(attribute => !string.IsNullOrWhiteSpace(attribute.Policy))
                .Select(attribute => (Endpoint: endpoint.DisplayName, Policy: attribute.Policy!)))
            .Where(item => !configured.Contains(item.Policy))
            .Select(item => $"'{item.Policy}' on '{item.Endpoint}'")
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        if (missing.Length > 0)
            throw new InvalidOperationException(
                "Authorization permissions missing from RoleAccess:Roles: " + string.Join(", ", missing));
    }
}
