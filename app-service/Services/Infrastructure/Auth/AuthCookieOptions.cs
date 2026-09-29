namespace AppService.Services;

public sealed class AuthCookieOptions
{
    public string Name { get; set; } = "lct_refresh";
    public string Path { get; set; } = "/api/app/auth";
}
