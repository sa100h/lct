using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class DashboardQueryServiceTests
{
    [Fact]
    public async Task GetAsync_CountsNormalEmptyOrNormaOnly()
    {
        IReadOnlyList<DispatcherObjectInfo> objects =
        [
            Object(1, []),
            Object(2, ["Норма"]),
            Object(3, ["Норма", "Тревога"]),
        ];
        var service = new DashboardQueryService(
            new StubDispatcherObjectRepository(objects),
            new StubDashboardFeedRepository());

        var snapshot = await service.GetAsync(TestContext.Current.CancellationToken);

        Assert.Equal(3, snapshot.Objects.Total);
        Assert.Equal(2, snapshot.Objects.Normal);
        Assert.Equal(1, snapshot.Objects.Deviation);
        var problem = Assert.Single(snapshot.Objects.ProblemObjects);
        Assert.Equal(3, problem.Id);
        Assert.Equal(["Норма", "Тревога"], problem.Statuses);
    }

    [Fact]
    public async Task GetAsync_TruncatesProblemObjectsTo20()
    {
        var objects = Enumerable.Range(1, 21)
            .Select(id => Object(id, ["Тревога"]))
            .ToArray();
        var service = new DashboardQueryService(
            new StubDispatcherObjectRepository(objects),
            new StubDashboardFeedRepository());

        var snapshot = await service.GetAsync(TestContext.Current.CancellationToken);

        Assert.Equal(21, snapshot.Objects.Total);
        Assert.Equal(21, snapshot.Objects.Deviation);
        Assert.Equal(20, snapshot.Objects.ProblemObjects.Count);
        Assert.Equal(1, snapshot.Objects.ProblemObjects[0].Id);
        Assert.Equal(20, snapshot.Objects.ProblemObjects[19].Id);
    }

    [Fact]
    public void ForecastStatus_MapsCompositionTimes()
    {
        var start = new DateTimeOffset(2026, 9, 26, 10, 0, 0, TimeSpan.Zero);
        var end = start.AddHours(1);

        Assert.Equal("pending", DashboardQueryService.MapForecastStatus(null, null));
        Assert.Equal("running", DashboardQueryService.MapForecastStatus(start, null));
        Assert.Equal("done", DashboardQueryService.MapForecastStatus(start, end));
    }

    private static DispatcherObjectInfo Object(int id, IReadOnlyList<string> statuses)
        => new(id, null, $"o{id}", 1, "district", 0, 0, statuses, 0, [], 0);

    private sealed class StubDispatcherObjectRepository(
        IReadOnlyList<DispatcherObjectInfo> result) : IDispatcherObjectRepository
    {
        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult(result);
    }

    private sealed class StubDashboardFeedRepository : IDashboardFeedRepository
    {
        public Task<IReadOnlyList<DashboardEventRow>> GetRecentEventsAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<DashboardEventRow>>([]);

        public Task<IReadOnlyList<DashboardForecastRow>> GetRecentForecastsAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<DashboardForecastRow>>([]);

        public Task<IReadOnlyList<DashboardRequestRow>> GetRecentRequestsAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<DashboardRequestRow>>([]);
    }
}
