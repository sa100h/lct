namespace AppService.Models;

public sealed record RefreshTokenRecord(Guid Id, Guid FamilyId, Guid UserId, DateTimeOffset ExpiresAt,
    DateTimeOffset? ConsumedAt, DateTimeOffset? RevokedAt);
