namespace AppService.Services.Infrastructure;

public sealed class AdOptions
{
    public const string SectionName = "Ad";

    public string Host { get; set; } = string.Empty;
    public int Port { get; set; }
    public string BaseDn { get; set; } = string.Empty;
    public string BindName { get; set; } = string.Empty;
    public string BindPassword { get; set; } = string.Empty;
    public string CertificatePath { get; set; } = string.Empty;
    public int TimeoutSeconds { get; set; }
}
