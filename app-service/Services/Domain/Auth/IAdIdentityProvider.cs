using AppService.Models;

namespace AppService.Services.Domain;

public interface IAdIdentityProvider
{
    Task<DirectoryIdentity?> AuthenticateAsync(string login, string password, CancellationToken cancellationToken);
    Task<DirectoryIdentity?> GetCurrentAsync(Guid objectGuid, CancellationToken cancellationToken);
}
