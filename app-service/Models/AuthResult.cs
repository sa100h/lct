namespace AppService.Models;

public sealed record AuthResult(string? AccessToken, string? RefreshToken, DateTimeOffset? RefreshExpiresAt, AuthError Error)
{
    public static AuthResult Failed(AuthError error) => new(null, null, null, error);
    public static AuthResult Success(string accessToken, string refreshToken, DateTimeOffset refreshExpiresAt)
        => new(accessToken, refreshToken, refreshExpiresAt, AuthError.None);
}
