using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastHistoryQueryServiceTests
{
    [Fact]
    public async Task ListAsync_MapsPendingAndClampsPageSize()
    {
        var id = Guid.Parse("2c059017-47c7-480a-b0a1-516be249695d");
        var created = new DateTimeOffset(2026, 9, 25, 10, 30, 0, TimeSpan.Zero);
        var journal = new StubForecastJournalRepository
        {
            Rows =
            [
                new ForecastHistoryListRow(id, created, "admin.test", null, null, 96),
            ],
            Total = 1,
        };
        var service = new ForecastHistoryQueryService(journal, new StubDispatcherObjectRepository([]));

        var page = await service.ListAsync(
            new ForecastHistoryListQuery(null, null, null, 1, 50),
            TestContext.Current.CancellationToken);

        Assert.Equal(20, journal.LastLimit);
        Assert.Equal(0, journal.LastOffset);
        var item = Assert.Single(page.Items);
        Assert.Equal(id, item.Id);
        Assert.Equal("pending", item.Status);
        Assert.Equal("admin.test", item.AuthorLogin);
        Assert.Equal(96, item.ObjectCount);
        Assert.Equal(1, page.Total);
    }

    [Fact]
    public async Task ListAsync_RejectsInvalidPage()
    {
        var service = new ForecastHistoryQueryService(
            new StubForecastJournalRepository(),
            new StubDispatcherObjectRepository([]));

        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.ListAsync(
                new ForecastHistoryListQuery(null, null, null, 0, 20),
                TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task GetByIdAsync_FiltersObjectsAndSetsHasHighRiskFalse()
    {
        var id = Guid.Parse("2c059017-47c7-480a-b0a1-516be249695d");
        var created = new DateTimeOffset(2026, 9, 25, 10, 30, 0, TimeSpan.Zero);
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, created, "admin.test", null, null, [2]),
        };
        var service = new ForecastHistoryQueryService(
            journal,
            new StubDispatcherObjectRepository(
            [
                Object(1),
                Object(2),
            ]));

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        Assert.NotNull(detail);
        var obj = Assert.Single(detail.Objects);
        Assert.Equal(2, obj.Id);
        Assert.False(obj.HasHighRisk);
        Assert.Equal("pending", detail.Status);
    }

    [Fact]
    public async Task GetByIdAsync_ReturnsNullWhenMissing()
    {
        var service = new ForecastHistoryQueryService(
            new StubForecastJournalRepository(),
            new StubDispatcherObjectRepository([]));

        var detail = await service.GetByIdAsync(
            Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            TestContext.Current.CancellationToken);

        Assert.Null(detail);
    }

    [Fact]
    public async Task GetByIdAsync_IncludesAncestorsOfChannelObjects()
    {
        var id = Guid.NewGuid();
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "Автоматически", null, null, [3]),
        };
        var objects = new StubDispatcherObjectRepository(
        [
            new DispatcherObjectInfo(1, null, "root", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(2, 1, "parent", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(3, 2, "sensor object", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(4, 1, "unrelated", 1, "district", 37.45, 55.6, [], 0, [], 0),
        ]);
        var service = new ForecastHistoryQueryService(journal, objects);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        Assert.NotNull(detail);
        Assert.Equal([1, 2, 3], detail.Objects.Select(item => item.Id));
    }

    private static DispatcherObjectInfo Object(int id)
        => new(id, null, $"o{id}", 1, "district", 37.45, 55.6, [], 0, [], 0);

    private sealed class StubDispatcherObjectRepository(
        IReadOnlyList<DispatcherObjectInfo> result) : IDispatcherObjectRepository
    {
        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult(result);
    }

    private sealed class StubForecastJournalRepository : IForecastJournalRepository
    {
        public IReadOnlyList<ForecastHistoryListRow> Rows { get; init; } = [];
        public int Total { get; init; }
        public ForecastHistoryHeader? Header { get; init; }
        public int LastLimit { get; private set; }
        public int LastOffset { get; private set; }

        public Task<IReadOnlyList<int>> FindMissingDispatcherObjectIdsAsync(
            IReadOnlyCollection<int> dispatcherObjectIds,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<ForecastJournalEntry> CreateAsync(
            Guid userId,
            string description,
            IReadOnlyDictionary<int, string> channelReadings,
            IReadOnlyList<int>? dispatcherObjectIds,
            DateTimeOffset createdAt,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<IReadOnlyList<ForecastAuthor>> ListAuthorsAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<ForecastAuthor>>([]);

        public Task<(IReadOnlyList<ForecastHistoryListRow> Items, int Total)> ListRowsAsync(
            Guid? createdBy,
            DateOnly? from,
            DateOnly? to,
            int offset,
            int limit,
            CancellationToken cancellationToken = default)
        {
            LastOffset = offset;
            LastLimit = limit;
            return Task.FromResult((Rows, Total));
        }

        public Task<ForecastHistoryHeader?> GetHeaderAsync(
            Guid id,
            CancellationToken cancellationToken = default)
            => Task.FromResult(Header);
    }
}
