using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastRunServiceTests
{
    [Fact]
    public async Task RunAsync_CreatesJournalForAllObjectsWhenIdsAreNull()
    {
        var repository = new RecordingForecastJournalRepository();
        var now = new DateTimeOffset(2026, 9, 25, 10, 30, 0, TimeSpan.Zero);
        var service = new ForecastRunService(repository, new FixedTimeProvider(now));
        var userId = Guid.NewGuid();

        var entry = await service.RunAsync(userId, null, TestContext.Current.CancellationToken);

        Assert.Equal(userId, repository.UserId);
        Assert.Equal("Запуск прогнозирования", repository.Description);
        Assert.Null(repository.DispatcherObjectIds);
        Assert.Equal(now, entry.CreatedAt);
    }

    [Fact]
    public async Task RunAsync_NormalizesAndValidatesSelectedObjects()
    {
        var repository = new RecordingForecastJournalRepository();
        var service = new ForecastRunService(repository, new FixedTimeProvider(DateTimeOffset.UtcNow));

        await service.RunAsync(
            Guid.NewGuid(),
            [20, 10, 20],
            TestContext.Current.CancellationToken);

        Assert.Equal([10, 20], repository.CheckedObjectIds);
        Assert.Equal([10, 20], repository.DispatcherObjectIds);
    }

    [Fact]
    public async Task RunAsync_RejectsUnknownObjectsWithoutCreatingJournal()
    {
        var repository = new RecordingForecastJournalRepository { MissingObjectIds = [999] };
        var service = new ForecastRunService(repository, new FixedTimeProvider(DateTimeOffset.UtcNow));

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.RunAsync(
            Guid.NewGuid(),
            [20, 999],
            TestContext.Current.CancellationToken));

        Assert.Contains("999", exception.Message);
        Assert.Null(repository.UserId);
    }

    [Fact]
    public async Task RunAsync_RejectsEmptySelection()
    {
        var repository = new RecordingForecastJournalRepository();
        var service = new ForecastRunService(repository, new FixedTimeProvider(DateTimeOffset.UtcNow));

        await Assert.ThrowsAsync<ArgumentException>(() => service.RunAsync(
            Guid.NewGuid(),
            [],
            TestContext.Current.CancellationToken));

        Assert.Null(repository.UserId);
    }

    private sealed class RecordingForecastJournalRepository : IForecastJournalRepository
    {
        public IReadOnlyList<int> MissingObjectIds { get; init; } = [];
        public IReadOnlyList<int>? CheckedObjectIds { get; private set; }
        public Guid? UserId { get; private set; }
        public string? Description { get; private set; }
        public IReadOnlyList<int>? DispatcherObjectIds { get; private set; }

        public Task<IReadOnlyList<int>> FindMissingDispatcherObjectIdsAsync(
            IReadOnlyCollection<int> dispatcherObjectIds,
            CancellationToken cancellationToken = default)
        {
            CheckedObjectIds = dispatcherObjectIds.ToArray();
            return Task.FromResult(MissingObjectIds);
        }

        public Task<ForecastJournalEntry> CreateAsync(
            Guid userId,
            string description,
            IReadOnlyList<int>? dispatcherObjectIds,
            DateTimeOffset createdAt,
            CancellationToken cancellationToken = default)
        {
            UserId = userId;
            Description = description;
            DispatcherObjectIds = dispatcherObjectIds;
            return Task.FromResult(new ForecastJournalEntry(Guid.NewGuid(), createdAt, dispatcherObjectIds));
        }

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
            => throw new NotSupportedException();
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
