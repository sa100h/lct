using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastErroneousServiceTests
{
    [Fact]
    public async Task MarkAsync_SendsSubtreeToRepository()
    {
        var journalId = Guid.NewGuid();
        var userId = Guid.NewGuid();
        var results = new RecordingForecastResultRepository { JournalExists = true };
        var service = new ForecastErroneousService(results, new StubSubtreeRepository([5, 5122]));

        await service.MarkAsync(journalId, userId, 5, TestContext.Current.CancellationToken);

        Assert.Equal(journalId, results.JournalId);
        Assert.Equal(userId, results.UserId);
        Assert.Equal([5, 5122], results.ObjectIds);
    }

    [Fact]
    public async Task MarkAsync_RejectsMissingJournal()
    {
        var results = new RecordingForecastResultRepository { JournalExists = false };
        var service = new ForecastErroneousService(results, new StubSubtreeRepository([5]));

        var exception = await Assert.ThrowsAsync<KeyNotFoundException>(() =>
            service.MarkAsync(Guid.NewGuid(), Guid.NewGuid(), 5, TestContext.Current.CancellationToken));

        Assert.Equal(ForecastErroneousService.MissingJournal, exception.Message);
        Assert.Null(results.ObjectIds);
    }

    [Fact]
    public async Task MarkAsync_RejectsUnknownObject()
    {
        var results = new RecordingForecastResultRepository { JournalExists = true };
        var service = new ForecastErroneousService(results, new StubSubtreeRepository([]));

        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            service.MarkAsync(Guid.NewGuid(), Guid.NewGuid(), 9, TestContext.Current.CancellationToken));

        Assert.Equal(ForecastErroneousService.MissingObject, exception.Message);
        Assert.Null(results.ObjectIds);
    }

    [Fact]
    public async Task MarkAsync_RepeatCallsRepositoryAgain()
    {
        var results = new RecordingForecastResultRepository { JournalExists = true };
        var service = new ForecastErroneousService(results, new StubSubtreeRepository([5]));
        var journalId = Guid.NewGuid();
        var userId = Guid.NewGuid();

        await service.MarkAsync(journalId, userId, 5, TestContext.Current.CancellationToken);
        await service.MarkAsync(journalId, userId, 5, TestContext.Current.CancellationToken);

        Assert.Equal(2, results.CallCount);
    }

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

        public Task<IReadOnlyDictionary<int, ForecastJournalResult>> ListByJournalAsync(
            Guid journalId,
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyDictionary<int, ForecastJournalResult>>(
                new Dictionary<int, ForecastJournalResult>());
    }

    private sealed class StubSubtreeRepository(IReadOnlyList<int> ids) : IDispatcherObjectRepository
    {
        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<IReadOnlyList<int>> GetSubtreeIdsAsync(
            int rootId,
            CancellationToken cancellationToken = default)
            => Task.FromResult(ids);
    }
}
