using AppService.Models;
using Shared.Authentication;

namespace AppService.Services.Domain;

public sealed class AuthSessionService(
    IAdIdentityProvider directory,
    IAuthRepository store,
    ITokenIssuer tokens,
    RoleAccessCatalog roleAccess,
    JwtOptions jwtOptions,
    TimeProvider timeProvider) : IAuthSessionService
{
    public async Task<AuthResult> LoginAsync(string login, string password, CancellationToken cancellationToken)
    {
        DirectoryIdentity? identity;
        try
        {
            identity = await directory.AuthenticateAsync(login, password, cancellationToken);
        }
        catch (AdUnavailableException)
        {
            return AuthResult.Failed(AuthError.DirectoryUnavailable);
        }

        if (identity is null)
            return AuthResult.Failed(AuthError.InvalidCredentials);
        if (!identity.IsActive)
        {
            await store.DeactivateAndRevokeAllAsync(identity.Id, timeProvider.GetUtcNow(), cancellationToken);
            return AuthResult.Failed(AuthError.Forbidden);
        }
        if (!roleAccess.TryResolveRole(identity.Groups, out var role))
            return AuthResult.Failed(AuthError.Forbidden);

        var now = timeProvider.GetUtcNow();
        var expiresAt = now.AddDays(jwtOptions.RefreshLifetimeDays);
        var familyId = Guid.NewGuid();
        var refresh = tokens.CreateRefresh();
        var access = tokens.IssueAccess(identity.Id, familyId, role, identity.Login, now);
        await store.CreateLoginAsync(identity, familyId, Guid.NewGuid(),
            tokens.HashRefresh(refresh), now, expiresAt, cancellationToken);
        return AuthResult.Success(access, refresh, expiresAt);
    }

    public async Task<AuthResult> RefreshAsync(string? refresh, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(refresh) || refresh.Length > 256)
            return AuthResult.Failed(AuthError.InvalidRefreshToken);

        var presentedHash = tokens.HashRefresh(refresh);
        var presented = await store.FindRefreshAsync(presentedHash, cancellationToken);
        if (presented is null)
            return AuthResult.Failed(AuthError.InvalidRefreshToken);

        var checkedAt = timeProvider.GetUtcNow();
        if (presented.ConsumedAt is not null)
        {
            if (presented.ExpiresAt > checkedAt)
                await store.RevokeFamilyAsync(presentedHash, checkedAt, cancellationToken);
            return AuthResult.Failed(AuthError.InvalidRefreshToken);
        }
        if (presented.RevokedAt is not null || presented.ExpiresAt <= checkedAt)
            return AuthResult.Failed(AuthError.InvalidRefreshToken);

        DirectoryIdentity? identity;
        try
        {
            identity = await directory.GetCurrentAsync(presented.UserId, cancellationToken);
        }
        catch (AdUnavailableException)
        {
            return AuthResult.Failed(AuthError.DirectoryUnavailable);
        }

        var now = timeProvider.GetUtcNow();
        if (identity is null || !identity.IsActive || identity.Id != presented.UserId)
        {
            await store.DeactivateAndRevokeAllAsync(presented.UserId, now, cancellationToken);
            return AuthResult.Failed(AuthError.Forbidden);
        }
        if (!roleAccess.TryResolveRole(identity.Groups, out var role))
            return AuthResult.Failed(AuthError.Forbidden);

        var nextRefresh = tokens.CreateRefresh();
        var nextHash = tokens.HashRefresh(nextRefresh);
        var access = tokens.IssueAccess(identity.Id, presented.FamilyId, role, identity.Login, now);
        var rotation = await store.RotateAsync(identity, presented, presentedHash,
            nextHash, Guid.NewGuid(), now, cancellationToken);
        return rotation == RefreshRotationResult.Success
            ? AuthResult.Success(access, nextRefresh, presented.ExpiresAt)
            : AuthResult.Failed(AuthError.InvalidRefreshToken);
    }

    public async Task LogoutAsync(string? refresh, CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(refresh) && refresh.Length <= 256)
            await store.RevokeFamilyAsync(tokens.HashRefresh(refresh), timeProvider.GetUtcNow(), cancellationToken);
    }
}
