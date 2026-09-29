using AppService.Models;

namespace AppService.Services.Domain;

public interface IAuthRepository
{
    Task CreateLoginAsync(DirectoryIdentity identity, string jwtRole, Guid familyId, Guid tokenId,
        byte[] tokenHash, DateTimeOffset now, DateTimeOffset expiresAt, CancellationToken cancellationToken);
    Task<RefreshTokenRecord?> FindRefreshAsync(byte[] tokenHash, CancellationToken cancellationToken);
    Task<RefreshRotationResult> RotateAsync(DirectoryIdentity identity, string jwtRole, RefreshTokenRecord presented,
        byte[] tokenHash, byte[] nextHash, Guid nextTokenId, DateTimeOffset now, CancellationToken cancellationToken);
    Task DeactivateAndRevokeAllAsync(Guid userId, DateTimeOffset now, CancellationToken cancellationToken);
    Task RevokeFamilyAsync(byte[] tokenHash, DateTimeOffset now, CancellationToken cancellationToken);
    Task<bool> IsAccessActiveAsync(Guid userId, Guid familyId, DateTimeOffset now, CancellationToken cancellationToken);
}
