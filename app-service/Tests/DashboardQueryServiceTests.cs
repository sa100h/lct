using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class DashboardQueryServiceTests
{
    private static readonly DateTimeOffset FrozenUtc = new(2026, 9, 28, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void PadDays_FillsFourteenZeros()
    {
        var days = DashboardQueryService.PadDays(new DateOnly(2026, 9, 28), new Dictionary<DateOnly, int>());

        Assert.Equal(14, days.Count);
        Assert.Equal(new DateOnly(2026, 9, 15), days[0].Date);
        Assert.Equal(new DateOnly(2026, 9, 28), days[13].Date);
        Assert.All(days, day => Assert.Equal(0, day.Count));
    }

    [Fact]
    public async Task GetAsync_CountsNormalEmptyOrNormaOnly()
    {
        IReadOnlyList<DispatcherObjectInfo> objects =
        [
            Object(1, []),
            Object(2, ["Норма"]),
            Object(3, ["Норма", "Тревога"]),
        ];
        var service = CreateService(objects, new StubDashboardFeedRepository());

        var snapshot = await service.GetAsync(TestContext.Current.CancellationToken);

        Assert.Equal(3, snapshot.Objects.Total);
        Assert.Equal(2, snapshot.Objects.Normal);
        Assert.Equal(1, snapshot.Objects.Deviation);
    }

    [Fact]
    public async Task GetAsync_PadsAlarmsAndRequestStatusZeros()
    {
        var feeds = new StubDashboardFeedRepository
        {
            Alarms = new Dictionary<DateOnly, int> { [new DateOnly(2026, 9, 28)] = 2 },
            RequestStatuses = [new DashboardStatusCount("В работе", 3)],
        };
        var service = CreateService([], feeds);

        var snapshot = await service.GetAsync(TestContext.Current.CancellationToken);

        Assert.Equal(14, snapshot.AlarmsByDay.Count);
        Assert.Equal(2, snapshot.AlarmsByDay[13].Count);
        Assert.All(snapshot.AlarmsByDay.Take(13), day => Assert.Equal(0, day.Count));
        Assert.Equal(
            ["Новая", "В работе", "Закрыта"],
            snapshot.RequestsByStatus.Select(item => item.Status));
        Assert.Equal([0, 3, 0], snapshot.RequestsByStatus.Select(item => item.Count));
        Assert.Equal(3, snapshot.RequestsTotal);
        Assert.Equal(
            ["pending", "running", "done", "error", "cancelled", "approved"],
            snapshot.ForecastsByStatus.Select(item => item.Status));
        Assert.All(snapshot.ForecastsByStatus, item => Assert.Equal(0, item.Count));
        Assert.Equal(14, snapshot.RequestsByDay.Count);
    }

    [Fact]
    public async Task GetAsync_KeepsJournalStatusesAndUnknownRequestStatus()
    {
        var feeds = new StubDashboardFeedRepository
        {
            RequestStatuses =
            [
                new DashboardStatusCount("Новая", 1),
                new DashboardStatusCount("Отложена", 2),
            ],
            ForecastStatuses =
            [
                new DashboardStatusCount("approved", 4),
                new DashboardStatusCount("error", 1),
            ],
        };
        var snapshot = await CreateService([], feeds).GetAsync(TestContext.Current.CancellationToken);

        Assert.Equal(
            ["Новая", "В работе", "Закрыта", "Отложена"],
            snapshot.RequestsByStatus.Select(item => item.Status));
        Assert.Equal([1, 0, 0, 2], snapshot.RequestsByStatus.Select(item => item.Count));
        Assert.Equal(3, snapshot.RequestsTotal);
        Assert.Equal(
            ["pending", "running", "done", "error", "cancelled", "approved"],
            snapshot.ForecastsByStatus.Select(item => item.Status));
        Assert.Equal([0, 0, 0, 1, 0, 4], snapshot.ForecastsByStatus.Select(item => item.Count));
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

    private static DashboardQueryService CreateService(
        IReadOnlyList<DispatcherObjectInfo> objects,
        IDashboardFeedRepository feeds)
        => new(new StubDispatcherObjectRepository(objects), feeds, new FixedTimeProvider(FrozenUtc));

    private static DispatcherObjectInfo Object(int id, IReadOnlyList<string> statuses)
        => new(id, null, $"o{id}", 1, "district", 0, 0, statuses, 0, [], 0);

    private sealed class FixedTimeProvider(DateTimeOffset utc) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => utc;
    }

    private sealed class StubDispatcherObjectRepository(
        IReadOnlyList<DispatcherObjectInfo> result) : IDispatcherObjectRepository
    {
        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult(result);

        public Task<IReadOnlyList<int>> GetSubtreeIdsAsync(
            int rootId,
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<int>>([]);
    }

    private sealed class StubDashboardFeedRepository : IDashboardFeedRepository
    {
        public IReadOnlyDictionary<DateOnly, int> Alarms { get; init; } = new Dictionary<DateOnly, int>();
        public IReadOnlyList<DashboardStatusCount> RequestStatuses { get; init; } = [];
        public IReadOnlyDictionary<DateOnly, int> RequestsByDay { get; init; } = new Dictionary<DateOnly, int>();
        public IReadOnlyList<DashboardStatusCount> ForecastStatuses { get; init; } = [];

        public Task<IReadOnlyDictionary<DateOnly, int>> GetAlarmCountsByDayAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(Alarms);

        public Task<IReadOnlyList<DashboardStatusCount>> GetRequestCountsByStatusAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult(RequestStatuses);

        public Task<IReadOnlyDictionary<DateOnly, int>> GetRequestCountsByDayAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(RequestsByDay);

        public Task<IReadOnlyList<DashboardStatusCount>> GetForecastCountsByStatusAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(ForecastStatuses);
    }
}
