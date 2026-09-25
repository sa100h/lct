using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class DispatcherObjectQueryServiceTests
{
    [Fact]
    public async Task GetAllAsync_ReturnsRepositoryProjection()
    {
        IReadOnlyList<DispatcherObjectInfo> expected =
        [
            new DispatcherObjectInfo(
                5,
                5773,
                "объект Альфа",
                2,
                "controlHouse",
                37.50,
                55.61,
                ["Норма", "Тревога"],
                42)
        ];
        var repository = new StubDispatcherObjectRepository(expected);
        var service = new DispatcherObjectQueryService(repository);

        var result = await service.GetAllAsync(TestContext.Current.CancellationToken);

        Assert.Same(expected, result);
        Assert.Equal(1, repository.CallCount);
    }

    private sealed class StubDispatcherObjectRepository(
        IReadOnlyList<DispatcherObjectInfo> result) : IDispatcherObjectRepository
    {
        public int CallCount { get; private set; }

        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
        {
            CallCount++;
            return Task.FromResult(result);
        }
    }
}
