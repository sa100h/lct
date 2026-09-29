using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastErroneousServiceTests
{
    [Fact]
    public async Task MarkAsync_SendsOnlyRequestedIdsInForecastTree()
    {
        var journalId = Guid.NewGuid();
        var userId = Guid.NewGuid();
        var results = new RecordingForecastResultRepository { JournalExists = true };
        var journal = HeaderJournal(journalId, [2]);
        var objects = new StubObjects([Item(1, null), Item(2, 1), Item(9, null)]);
        var service = new ForecastErroneousService(results, journal, objects);
        await service.MarkAsync(journalId, userId, [1, 2], TestContext.Current.CancellationToken);
        Assert.Equal([1, 2], results.ObjectIds);
    }

    [Fact]
    public async Task MarkAsync_RejectsEmpty()
    {
        var service = new ForecastErroneousService(
            new RecordingForecastResultRepository { JournalExists = true },
            HeaderJournal(Guid.NewGuid(), [1]),
            new StubObjects([Item(1, null)]));
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            service.MarkAsync(Guid.NewGuid(), Guid.NewGuid(), [], TestContext.Current.CancellationToken));
        Assert.Equal(ForecastErroneousService.EmptyObjects, ex.Message);
    }

    [Fact]
    public async Task MarkAsync_RejectsIdOutsideForecastTree()
    {
        var results = new RecordingForecastResultRepository { JournalExists = true };
        var service = new ForecastErroneousService(
            results,
            HeaderJournal(Guid.NewGuid(), [2]),
            new StubObjects([Item(1, null), Item(2, 1), Item(9, null)]));
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            service.MarkAsync(Guid.NewGuid(), Guid.NewGuid(), [9], TestContext.Current.CancellationToken));
        Assert.Equal(ForecastErroneousService.MissingObject, ex.Message);
        Assert.Null(results.ObjectIds);
    }

    [Fact]
    public async Task MarkAsync_RejectsMissingJournal()
    {
        var results = new RecordingForecastResultRepository { JournalExists = false };
        var service = new ForecastErroneousService(
            results,
            new StubJournal { Header = null },
            new StubObjects([Item(5, null)]));

        var exception = await Assert.ThrowsAsync<KeyNotFoundException>(() =>
            service.MarkAsync(Guid.NewGuid(), Guid.NewGuid(), [5], TestContext.Current.CancellationToken));

        Assert.Equal(ForecastErroneousService.MissingJournal, exception.Message);
        Assert.Null(results.ObjectIds);
    }

    [Fact]
    public async Task MarkAsync_RepeatCallsRepositoryAgain()
    {
        var results = new RecordingForecastResultRepository { JournalExists = true };
        var journalId = Guid.NewGuid();
        var userId = Guid.NewGuid();
        var service = new ForecastErroneousService(
            results,
            HeaderJournal(journalId, [5]),
            new StubObjects([Item(5, null)]));

        await service.MarkAsync(journalId, userId, [5], TestContext.Current.CancellationToken);
        await service.MarkAsync(journalId, userId, [5], TestContext.Current.CancellationToken);

        Assert.Equal(2, results.CallCount);
    }

    private static StubJournal HeaderJournal(Guid id, IReadOnlyList<int> objectIds)
        => new()
        {
            Header = new ForecastHistoryHeader(
                id, DateTimeOffset.UtcNow, "a", null, null, "pending", null, null, objectIds),
        };

    private static DispatcherObjectInfo Item(int id, int? parent)
        => new(id, parent, $"o{id}", 1, "district", 0, 0, [], 0, [], 0);

    private sealed class RecordingForecastResultRepository : IForecastResultRepository
    {
        public bool JournalExists { get; init; }
        public int CallCount { get; private set; }
        public Guid? JournalId { get; private set; }
        public Guid? UserId { get; private set; }
        public IReadOnlyList<int>? ObjectIds { get; private set; }

        public Task<bool> JournalExistsAsync(Guid journalId, CancellationToken cancellationToken = default)
            => Task.FromResult(JournalExists);

        public Task MarkErroneousAsync(
            Guid journalId,
            Guid dispatcherUserId,
            IReadOnlyList<int> objectIds,
            CancellationToken cancellationToken = default)
        {
            CallCount++;
            JournalId = journalId;
            UserId = dispatcherUserId;
            ObjectIds = objectIds;
            return Task.CompletedTask;
        }

        public Task MarkRequestCreatedAsync(
            Guid journalId,
            Guid dispatcherUserId,
            IReadOnlyList<int> objectIds,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<IReadOnlyDictionary<int, ForecastJournalResult>> ListByJournalAsync(
            Guid journalId,
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyDictionary<int, ForecastJournalResult>>(
                new Dictionary<int, ForecastJournalResult>());
    }

    private sealed class StubObjects(IReadOnlyList<DispatcherObjectInfo> items) : IDispatcherObjectRepository
    {
        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult(items);

        public Task<IReadOnlyList<int>> GetSubtreeIdsAsync(
            int rootId,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }

    private sealed class StubJournal : IForecastJournalRepository
    {
        public ForecastHistoryHeader? Header { get; init; }

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
            => throw new NotSupportedException();

        public Task<(IReadOnlyList<ForecastHistoryListRow> Items, int Total)> ListRowsAsync(
            Guid? createdBy,
            DateOnly? from,
            DateOnly? to,
            int offset,
            int limit,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

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
