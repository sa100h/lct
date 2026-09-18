using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Shared.Authentication;

namespace AppService.Services;

public sealed class ActiveFamilyRequirementHandler(IAuthRepository store, TimeProvider timeProvider)
    : AuthorizationHandler<ActiveFamilyRequirement>
{
    protected override async Task HandleRequirementAsync(
        AuthorizationHandlerContext context,
        ActiveFamilyRequirement requirement)
    {
        if (!Guid.TryParse(context.User.FindFirst("sub")?.Value, out var userId)
            || !Guid.TryParse(context.User.FindFirst(JwtClaimNames.SessionId)?.Value, out var familyId))
            return;

        var cancellationToken = context.Resource is HttpContext httpContext
            ? httpContext.RequestAborted
            : CancellationToken.None;
        if (await store.IsAccessActiveAsync(userId, familyId, timeProvider.GetUtcNow(), cancellationToken))
            context.Succeed(requirement);
    }
}
