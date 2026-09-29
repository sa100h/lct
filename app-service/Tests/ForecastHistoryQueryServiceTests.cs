using AppService.Models;
using AppService.Services.Domain;
using AppService.Services.Infrastructure;
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
                new ForecastHistoryListRow(id, created, "admin.test", null, null, 96, "pending", null, null),
            ],
            Total = 1,
        };
        var service = CreateService(journal, new StubDispatcherObjectRepository([]));

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
        Assert.Null(item.ApprovedByLogin);
        Assert.Null(item.ApprovedAt);
        Assert.Equal(1, page.Total);
    }

    [Fact]
    public async Task ListAsync_RejectsInvalidPage()
    {
        var service = CreateService(
            new StubForecastJournalRepository(),
            new StubDispatcherObjectRepository([]));

        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.ListAsync(
                new ForecastHistoryListQuery(null, null, null, 0, 20),
                TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task GetByIdAsync_FiltersObjectsAndSetsHasHighRiskNullWithoutResult()
    {
        var id = Guid.Parse("2c059017-47c7-480a-b0a1-516be249695d");
        var created = new DateTimeOffset(2026, 9, 25, 10, 30, 0, TimeSpan.Zero);
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, created, "admin.test", null, null, "pending", null, null, [2]),
        };
        var service = CreateService(
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
        Assert.Null(obj.HasHighRisk);
        Assert.False(obj.IsErroneous);
        Assert.False(obj.HasResult);
        Assert.Empty(obj.ForecastValues);
        Assert.Equal("pending", detail.Status);
    }

    [Fact]
    public async Task GetByIdAsync_AttachesSensorNamesFromChannelRepository()
    {
        var id = Guid.NewGuid();
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "admin.test", null, null, "pending", null, null, [1]),
        };
        var rows = new Dictionary<int, ForecastJournalResult>
        {
            [1] = new("""{"channels":{"196623":{"infrastructure-wear":{"value":0.59}},"196624":{"infrastructure-wear":{"value":0.4}}}}""", false),
        };
        var channels = new StubForecastChannelRepository
        {
            Names = new Dictionary<int, string> { [196623] = "ДУ" },
        };
        var service = CreateService(
            journal,
            new StubDispatcherObjectRepository([Object(1)]),
            rows,
            channels: channels);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        Assert.Equal([196623, 196624], channels.LastRequestedIds);
        var values = detail!.Objects.Single().ForecastValues;
        Assert.Equal("ДУ", values.Single(item => item.ChannelId == "196623").SensorName);
        Assert.Equal("196624", values.Single(item => item.ChannelId == "196624").SensorName);
    }

    [Fact]
    public async Task GetByIdAsync_ReturnsNullWhenMissing()
    {
        var service = CreateService(
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
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "Автоматически", null, null, "pending", null, null, [3]),
        };
        var objects = new StubDispatcherObjectRepository(
        [
            new DispatcherObjectInfo(1, null, "root", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(2, 1, "parent", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(3, 2, "sensor object", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(4, 1, "unrelated", 1, "district", 37.45, 55.6, [], 0, [], 0),
        ]);
        var service = CreateService(journal, objects);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        Assert.NotNull(detail);
        Assert.Equal([1, 2, 3], detail.Objects.Select(item => item.Id));
        Assert.All(detail.Objects, item => Assert.Null(item.HasHighRisk));
    }

    [Fact]
    public async Task GetByIdAsync_CopiesOwnStatusesFromDispatcherObject()
    {
        var id = Guid.NewGuid();
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "admin.test", null, null, "pending", null, null, [3]),
        };
        IReadOnlyList<string> own = ["Нет связи"];
        var objects = new StubDispatcherObjectRepository(
        [
            new DispatcherObjectInfo(3, null, "ДУ", 1, "district", 37.45, 55.6, ["Нет связи"], 1, own, 1),
        ]);
        var service = CreateService(journal, objects);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        var obj = Assert.Single(detail!.Objects);
        Assert.Equal(own, obj.OwnStatuses);
        Assert.Equal(1, obj.OwnChannelCount);
    }

    [Fact]
    public async Task GetByIdAsync_SetsHasHighRiskFromDescriptionAndThreshold()
    {
        var id = Guid.NewGuid();
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "admin.test", null, null, "pending", null, null, [1, 2, 3]),
        };
        var rows = new Dictionary<int, ForecastJournalResult>
        {
            [1] = new("""{"channels":{"a":{"fire-risk":{"value":0.9}}}}""", false),
            [2] = new("""{"channels":{"a":{"fire-risk":{"value":0.1}}}}""", false),
            [3] = new("{}", false),
        };
        var service = CreateService(
            journal,
            new StubDispatcherObjectRepository([Object(1), Object(2), Object(3)]),
            rows,
            threshold: 0.5);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        Assert.Equal([true, false, null], detail!.Objects.Select(item => item.HasHighRisk));
        Assert.Equal([true, true, true], detail.Objects.Select(item => item.HasResult));
        var high = Assert.Single(detail.Objects[0].ForecastValues);
        Assert.Equal("a", high.ChannelId);
        Assert.Equal("fire-risk", high.Category);
        Assert.Equal(0.9, high.Value);
        Assert.Single(detail.Objects[1].ForecastValues);
        Assert.Empty(detail.Objects[2].ForecastValues);
    }

    [Fact]
    public async Task GetByIdAsync_ErroneousForcesHasHighRiskFalse()
    {
        var id = Guid.NewGuid();
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "admin.test", null, null, "pending", null, null, [1]),
        };
        var rows = new Dictionary<int, ForecastJournalResult>
        {
            [1] = new("""{"channels":{"a":{"fire-risk":{"value":0.9}}}}""", true),
        };
        var service = CreateService(
            journal,
            new StubDispatcherObjectRepository([Object(1)]),
            rows,
            threshold: 0.5);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);

        var obj = Assert.Single(detail!.Objects);
        Assert.True(obj.IsErroneous);
        Assert.False(obj.HasHighRisk);
        Assert.True(obj.HasResult);
        Assert.Equal(0.9, Assert.Single(obj.ForecastValues).Value);
    }

    [Fact]
    public async Task GetByIdAsync_UnpredictableDescription_IsResultWithoutRisk()
    {
        var id = Guid.NewGuid();
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(id, DateTimeOffset.UtcNow, "admin.test", null, null, "pending", null, null, [1]),
        };
        var rows = new Dictionary<int, ForecastJournalResult>
        {
            [1] = new("""{"channels":{"x":{"fire-risk":{"status_code":"unpredictable"}}}}""", false),
        };
        var service = CreateService(
            journal,
            new StubDispatcherObjectRepository([Object(1)]),
            rows);

        var detail = await service.GetByIdAsync(id, TestContext.Current.CancellationToken);
        var obj = Assert.Single(detail!.Objects);
        Assert.True(obj.HasResult);
        Assert.Null(obj.HasHighRisk);
        Assert.Empty(obj.ForecastValues);
    }

    [Fact]
    public async Task ListAsync_ApprovedColumn_MapsLoginAndTime()
    {
        var id = Guid.Parse("2c059017-47c7-480a-b0a1-516be249695d");
        var created = new DateTimeOffset(2026, 9, 25, 10, 30, 0, TimeSpan.Zero);
        var start = created;
        var end = created.AddHours(1);
        var approvedAt = created.AddHours(2);
        var journal = new StubForecastJournalRepository
        {
            Rows =
            [
                new ForecastHistoryListRow(
                    id, created, "admin.test", start, end, 96, "approved", "dispetcher_ods", approvedAt),
            ],
            Total = 1,
        };
        var page = await CreateService(journal, new StubDispatcherObjectRepository([]))
            .ListAsync(new ForecastHistoryListQuery(null, null, null, 1, 20), TestContext.Current.CancellationToken);
        var item = Assert.Single(page.Items);
        Assert.Equal("approved", item.Status);
        Assert.Equal("dispetcher_ods", item.ApprovedByLogin);
        Assert.Equal(approvedAt, item.ApprovedAt);
    }

    [Fact]
    public async Task GetByIdAsync_Approved_SetsStatusAndApprover()
    {
        var id = Guid.NewGuid();
        var created = DateTimeOffset.UtcNow;
        var start = created;
        var end = created.AddMinutes(5);
        var approvedAt = end.AddMinutes(1);
        var journal = new StubForecastJournalRepository
        {
            Header = new ForecastHistoryHeader(
                id, created, "admin.test", start, end, "approved", "admin.test", approvedAt, [1]),
        };
        var detail = await CreateService(journal, new StubDispatcherObjectRepository([Object(1)]))
            .GetByIdAsync(id, TestContext.Current.CancellationToken);
        Assert.Equal("approved", detail!.Status);
        Assert.Equal("admin.test", detail.ApprovedByLogin);
        Assert.Equal(approvedAt, detail.ApprovedAt);
    }

    private static ForecastHistoryQueryService CreateService(
        IForecastJournalRepository journal,
        IDispatcherObjectRepository objects,
        IReadOnlyDictionary<int, ForecastJournalResult>? rows = null,
        double threshold = 0.5,
        IForecastChannelRepository? channels = null)
        => new(
            journal,
            objects,
            new StubForecastResultRepository(rows ?? new Dictionary<int, ForecastJournalResult>()),
            channels ?? new StubForecastChannelRepository(),
            new ForecastOptions { RiskThreshold = threshold });

    private static DispatcherObjectInfo Object(int id)
        => new(id, null, $"o{id}", 1, "district", 37.45, 55.6, [], 0, [], 0);

    private sealed class StubForecastChannelRepository : IForecastChannelRepository
    {
        public IReadOnlyDictionary<int, string> Names { get; init; } = new Dictionary<int, string>();
        public IReadOnlyList<int>? LastRequestedIds { get; private set; }

        public Task<ForecastChannelSnapshot> GetLatestForObjectsAsync(
            IReadOnlyCollection<int>? dispatcherObjectIds,
            DateTimeOffset from,
            DateTimeOffset to,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<IReadOnlyDictionary<int, string>> GetNamesByIdsAsync(
            IReadOnlyCollection<int> channelIds,
            CancellationToken cancellationToken = default)
        {
            LastRequestedIds = [.. channelIds];
            return Task.FromResult(Names);
        }
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

    private sealed class StubForecastResultRepository(
        IReadOnlyDictionary<int, ForecastJournalResult> rows) : IForecastResultRepository
    {
        public Task<bool> JournalExistsAsync(Guid journalId, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task MarkErroneousAsync(
            Guid journalId,
            Guid dispatcherUserId,
            IReadOnlyList<int> objectIds,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<IReadOnlyDictionary<int, ForecastJournalResult>> ListByJournalAsync(
            Guid journalId,
            CancellationToken cancellationToken = default)
            => Task.FromResult(rows);
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

        public Task<bool> ApproveAsync(
            Guid id,
            Guid userId,
            DateTimeOffset approvedAt,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
