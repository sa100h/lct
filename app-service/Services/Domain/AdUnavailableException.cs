namespace AppService.Services.Domain;

public sealed class AdUnavailableException : Exception
{
    public AdUnavailableException(Exception innerException)
        : base("Active Directory is unavailable.", innerException) { }
}
