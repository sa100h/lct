using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class RequestQueryServiceTests
{
    [Fact]
    public async Task ListAsync_TechnicianRestrictsToUser()
    {
        var technicianId = Guid.NewGuid();
        var requests = new RecordingRequestQueryRepository();
        var service = new RequestQueryService(requests, new StubObjects([]));

        await service.ListAsync(false, technicianId, 1, 20, TestContext.Current.CancellationToken);

        Assert.Equal(technicianId, requests.RestrictToUserId);
        Assert.Equal(0, requests.Offset);
        Assert.Equal(20, requests.Limit);
    }

    [Fact]
    public async Task ListAsync_AdminDoesNotRestrict()
    {
        var requests = new RecordingRequestQueryRepository();
        var service = new RequestQueryService(requests, new StubObjects([]));

        await service.ListAsync(true, Guid.NewGuid(), 1, 20, TestContext.Current.CancellationToken);

        Assert.Null(requests.RestrictToUserId);
    }

    [Fact]
    public async Task GetAsync_ReturnsNullWhenHidden()
    {
        var requests = new RecordingRequestQueryRepository { Header = null };
        var service = new RequestQueryService(requests, new StubObjects([]));

        var detail = await service.GetAsync(
            false,
            Guid.NewGuid(),
            Guid.NewGuid(),
            TestContext.Current.CancellationToken);

        Assert.Null(detail);
    }

    [Fact]
    public async Task GetAsync_IncludesAncestorsOfRequestObjects()
    {
        var id = Guid.NewGuid();
        var requests = new RecordingRequestQueryRepository
        {
            Header = new RequestHeader(
                id,
                DateTimeOffset.UtcNow,
                "Утечка",
                "Новая",
                "dispetcher_ods",
                "technik.test",
                2,
                3,
                "sensor object",
                [3]),
        };
        var objects = new StubObjects(
        [
            new DispatcherObjectInfo(1, null, "root", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(2, 1, "parent", 1, "district", 37.45, 55.6, [], 0, [], 0),
            new DispatcherObjectInfo(3, 2, "sensor object", 1, "district", 37.45, 55.6, ["Норма"], 1, ["Норма"], 1),
            new DispatcherObjectInfo(4, 1, "unrelated", 1, "district", 37.45, 55.6, [], 0, [], 0),
        ]);
        var service = new RequestQueryService(requests, objects);

        var detail = await service.GetAsync(true, Guid.NewGuid(), id, TestContext.Current.CancellationToken);

        Assert.NotNull(detail);
        Assert.Equal("Утечка", detail.Description);
        Assert.Equal(3, detail.ObjectId);
        Assert.Equal([1, 2, 3], detail.Objects.Select(item => item.Id));
        var leaf = detail.Objects.Single(item => item.Id == 3);
        Assert.Equal(["Норма"], leaf.OwnStatuses);
        Assert.Equal(1, leaf.OwnChannelCount);
    }

    private sealed class RecordingRequestQueryRepository : IRequestRepository
    {
        public Guid? RestrictToUserId { get; private set; }
        public int Offset { get; private set; }
        public int Limit { get; private set; }
        public RequestHeader? Header { get; init; }

        public Task<bool> ForecastJournalExistsAsync(Guid id, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<bool> IsActiveTechnicianAsync(Guid userId, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<Guid> InsertAsync(
            Guid forecastJournalId,
            string description,
            Guid dispatcherUserId,
            Guid technicianId,
            IReadOnlyList<int> objectIds,
            int? priority,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<(IReadOnlyList<RequestListItem> Items, int Total)> ListAsync(
            Guid? restrictToUserId,
            int offset,
            int limit,
            CancellationToken cancellationToken = default)
        {
            RestrictToUserId = restrictToUserId;
            Offset = offset;
            Limit = limit;
            return Task.FromResult<(IReadOnlyList<RequestListItem>, int)>(([], 0));
        }

        public Task<RequestHeader?> GetHeaderAsync(
            Guid id,
            Guid? restrictToUserId,
            CancellationToken cancellationToken = default)
        {
            RestrictToUserId = restrictToUserId;
            return Task.FromResult(Header);
        }

        public Task<bool> StatusExistsAsync(string name, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<bool> UpdateStatusAsync(
            Guid id,
            string statusName,
            Guid? restrictToUserId,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }

    private sealed class StubObjects(IReadOnlyList<DispatcherObjectInfo> result) : IDispatcherObjectRepository
    {
        public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult(result);

        public Task<IReadOnlyList<int>> GetSubtreeIdsAsync(
            int rootId,
            CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<int>>([]);
    }
}
