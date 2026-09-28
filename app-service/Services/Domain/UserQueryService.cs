using AppService.Models;

namespace AppService.Services.Domain;

public sealed class UserQueryService(IUserRepository users) : IUserQueryService
{
    public Task<IReadOnlyList<UserListItem>> ListByRoleNameAsync(
        string roleName,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(roleName))
        {
            throw new ArgumentException("Роль обязательна.", nameof(roleName));
        }

        return users.ListActiveByRoleNameAsync(roleName.Trim(), cancellationToken);
    }
}
