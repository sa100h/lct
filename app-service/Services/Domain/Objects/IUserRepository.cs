using AppService.Models;

namespace AppService.Services.Domain;

public interface IUserRepository
{
    Task<IReadOnlyList<UserListItem>> ListActiveByRoleNameAsync(
        string roleName,
        CancellationToken cancellationToken = default);
}
