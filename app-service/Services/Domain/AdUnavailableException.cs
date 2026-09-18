namespace AppService.Services.Domain;

public sealed class AdUnavailableException : Exception
{
    public AdUnavailableException() : base("AD integration is not configured yet.") { }
}
