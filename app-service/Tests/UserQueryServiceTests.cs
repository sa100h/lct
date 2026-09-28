using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class UserQueryServiceTests
{
    [Fact]
    public async Task ListByRoleNameAsync_ReturnsRepositoryRows()
    {
        IReadOnlyList<UserListItem> expected = [new(Guid.NewGuid(), "technik.test")];
        var users = new StubUserRepository(expected);
        var service = new UserQueryService(users);

        var result = await service.ListByRoleNameAsync("Technics", TestContext.Current.CancellationToken);

        Assert.Same(expected, result);
    }

    [Fact]
    public async Task ListByRoleNameAsync_RejectsBlankRole()
    {
        var service = new UserQueryService(new StubUserRepository([]));

        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.ListByRoleNameAsync("  ", TestContext.Current.CancellationToken));
    }

    private sealed class StubUserRepository(IReadOnlyList<UserListItem> result) : IUserRepository
    {
        public Task<IReadOnlyList<UserListItem>> ListActiveByRoleNameAsync(
            string roleName,
            CancellationToken cancellationToken = default)
            => Task.FromResult(result);
    }
}
