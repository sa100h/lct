using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastApproveServiceTests
{
    [Fact]
    public async Task ApproveAsync_Done_WritesUserAndTime()
    {
        var id = Guid.NewGuid();
        var user = Guid.NewGuid();
        var created = new DateTimeOffset(2026, 9, 29, 8, 0, 0, TimeSpan.Zero);
        var now = created.AddHours(2);
        var journal = new RecordingJournal
        {
            Header = new ForecastHistoryHeader(
                id, created, "a", created, created.AddHours(1), "done", null, null, [1]),
            UpdateOk = true,
        };
        var service = new ForecastApproveService(journal, new FixedTime(now));
        await service.ApproveAsync(id, user, TestContext.Current.CancellationToken);
        Assert.Equal(id, journal.ApprovedId);
        Assert.Equal(user, journal.ApprovedUserId);
        Assert.Equal(now, journal.ApprovedAt);
    }

    [Fact]
    public async Task ApproveAsync_NotDone_Throws()
    {
        var journal = new RecordingJournal
        {
            Header = new ForecastHistoryHeader(
                Guid.NewGuid(), DateTimeOffset.UtcNow, "a", null, null, "pending", null, null, [1]),
        };
        var ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            new ForecastApproveService(journal, TimeProvider.System)
                .ApproveAsync(Guid.NewGuid(), Guid.NewGuid(), TestContext.Current.CancellationToken));
        Assert.Equal(ForecastApproveService.NotDone, ex.Message);
        Assert.Null(journal.ApprovedId);
    }

    [Fact]
    public async Task ApproveAsync_AlreadyApproved_Throws()
    {
        var journal = new RecordingJournal
        {
            Header = new ForecastHistoryHeader(
                Guid.NewGuid(), DateTimeOffset.UtcNow, "a",
                DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, "approved", "x", DateTimeOffset.UtcNow, [1]),
        };
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            new ForecastApproveService(journal, TimeProvider.System)
                .ApproveAsync(Guid.NewGuid(), Guid.NewGuid(), TestContext.Current.CancellationToken));
        Assert.Equal(ForecastApproveService.AlreadyApproved, ex.Message);
    }

    [Fact]
    public async Task ApproveAsync_Missing_Throws()
    {
        var journal = new RecordingJournal { Header = null };
        var ex = await Assert.ThrowsAsync<KeyNotFoundException>(() =>
            new ForecastApproveService(journal, TimeProvider.System)
                .ApproveAsync(Guid.NewGuid(), Guid.NewGuid(), TestContext.Current.CancellationToken));
        Assert.Equal(ForecastApproveService.MissingJournal, ex.Message);
    }

    private sealed class FixedTime(DateTimeOffset utc) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => utc;
    }

    private sealed class RecordingJournal : IForecastJournalRepository
    {
        public ForecastHistoryHeader? Header { get; init; }
        public bool UpdateOk { get; init; }
        public Guid? ApprovedId { get; private set; }
        public Guid? ApprovedUserId { get; private set; }
        public DateTimeOffset? ApprovedAt { get; private set; }

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
        {
            ApprovedId = id;
            ApprovedUserId = userId;
            ApprovedAt = approvedAt;
            return Task.FromResult(UpdateOk);
        }
    }
}
