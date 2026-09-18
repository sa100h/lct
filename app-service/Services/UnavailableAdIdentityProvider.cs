using AppService.Services.Domain;
using AppService.Models;

namespace AppService.Services;

public sealed class UnavailableAdIdentityProvider : IAdIdentityProvider
{
    public Task<DirectoryIdentity?> AuthenticateAsync(string login, string password, CancellationToken cancellationToken)
        => throw new AdUnavailableException();

    public Task<DirectoryIdentity?> GetCurrentAsync(Guid objectGuid, CancellationToken cancellationToken)
        => throw new AdUnavailableException();
}
