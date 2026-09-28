using AppService.Models;

namespace AppService.Services.Domain;

public interface IUserQueryService
{
    Task<IReadOnlyList<UserListItem>> ListByRoleNameAsync(
        string roleName,
        CancellationToken cancellationToken = default);
}
