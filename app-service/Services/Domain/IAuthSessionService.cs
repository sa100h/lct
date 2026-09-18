using AppService.Models;

namespace AppService.Services.Domain;

public interface IAuthSessionService
{
    Task<AuthResult> LoginAsync(string login, string password, CancellationToken cancellationToken);
    Task<AuthResult> RefreshAsync(string? refreshToken, CancellationToken cancellationToken);
    Task LogoutAsync(string? refreshToken, CancellationToken cancellationToken);
}
