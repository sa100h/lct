namespace AppService.Models;

public enum AuthError
{
    None,
    InvalidCredentials,
    Forbidden,
    InvalidRefreshToken,
    DirectoryUnavailable
}
