using System.ComponentModel.DataAnnotations;

namespace AppService.Contracts;

public sealed class LoginRequest
{
    [Required]
    public string Login { get; init; } = string.Empty;

    [Required]
    public string Password { get; init; } = string.Empty;
}
