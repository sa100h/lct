namespace Shared.Authentication;

public sealed class JwtOptions
{
    public const string SectionName = "Jwt";

    public string Issuer { get; set; } = string.Empty;
    public string Audience { get; set; } = string.Empty;
    public string PublicKeyPath { get; set; } = string.Empty;
    public string? PrivateKeyPath { get; set; }
    public int AccessLifetimeMinutes { get; set; } = 5;
    public int RefreshLifetimeDays { get; set; } = 7;
}
