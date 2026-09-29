using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class RequestCommandServiceTests
{
    [Fact]
    public async Task CreateAsync_InsertsSelectedIds()
    {
        var journalId = Guid.NewGuid();
        var technicianId = Guid.NewGuid();
        var dispatcherId = Guid.NewGuid();
        var requests = new RecordingRequestRepository { TechnicianOk = true };
        var journal = HeaderJournal(journalId, [2]);
        var objects = new StubObjects([Item(1, null), Item(2, 1)]);
        var service = new RequestCommandService(requests, journal, objects);

        var id = await service.CreateAsync(
            dispatcherId,
            new CreateRequestCommand(journalId, [1, 2], "  Утечка  ", 2, technicianId),
            TestContext.Current.CancellationToken);

        Assert.Equal(requests.InsertedId, id);
        Assert.Equal("Утечка", requests.Description);
        Assert.Equal(dispatcherId, requests.DispatcherUserId);
        Assert.Equal([1, 2], requests.ObjectIds);
        Assert.Equal(2, requests.Priority);
    }

    [Fact]
    public async Task CreateAsync_RejectsBlankDescription()
    {
        var requests = new RecordingRequestRepository { TechnicianOk = true };
        var service = Create(requests, [5]);

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), [5], "  ", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.DescriptionRequired, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsMissingJournal()
    {
        var requests = new RecordingRequestRepository { TechnicianOk = true };
        var service = new RequestCommandService(
            requests,
            new StubJournal { Header = null },
            new StubObjects([Item(5, null)]));

        var exception = await Assert.ThrowsAsync<KeyNotFoundException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), [5], "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingJournal, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsNonTechnician()
    {
        var requests = new RecordingRequestRepository { TechnicianOk = false };
        var service = Create(requests, [5]);

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), [5], "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingTechnician, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsIdOutsideForecastTree()
    {
        var requests = new RecordingRequestRepository { TechnicianOk = true };
        var service = new RequestCommandService(
            requests,
            HeaderJournal(Guid.NewGuid(), [2]),
            new StubObjects([Item(1, null), Item(2, 1), Item(9, null)]));

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), [9], "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingObject, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsEmpty()
    {
        var requests = new RecordingRequestRepository { TechnicianOk = true };
        var service = Create(requests, [5]);

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), [], "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.EmptyObjects, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task UpdateStatusAsync_RejectsUnknown()
    {
        var requests = new RecordingRequestRepository { StatusExists = false };
        var service = Create(requests, []);

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.UpdateStatusAsync(
            Guid.NewGuid(),
            true,
            Guid.NewGuid(),
            "Неизвестный",
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.UnknownStatus, exception.Message);
        Assert.False(requests.StatusUpdated);
    }

    [Fact]
    public async Task UpdateStatusAsync_Missing_KeyNotFound()
    {
        var requests = new RecordingRequestRepository { StatusExists = true, UpdateAffected = false };
        var service = Create(requests, []);
        var id = Guid.NewGuid();

        var exception = await Assert.ThrowsAsync<KeyNotFoundException>(() => service.UpdateStatusAsync(
            id,
            false,
            Guid.NewGuid(),
            "В работе",
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingRequest, exception.Message);
        Assert.True(requests.StatusUpdated);
        Assert.Equal(id, requests.UpdatedId);
        Assert.Equal("В работе", requests.UpdatedStatus);
    }

    private static RequestCommandService Create(RecordingRequestRepository requests, IReadOnlyList<int> objectIds)
        => new(requests, HeaderJournal(Guid.NewGuid(), objectIds), new StubObjects([.. objectIds.Select(id => Item(id, null))]));

    private static StubJournal HeaderJournal(Guid id, IReadOnlyList<int> objectIds)
        => new()
        {
            Header = new ForecastHistoryHeader(
                id, DateTimeOffset.UtcNow, "a", null, null, "pending", null, null, objectIds),
        };

    private static DispatcherObjectInfo Item(int id, int? parent)
        => new(id, parent, $"o{id}", 1, "district", 0, 0, [], 0, [], 0);

    private sealed class RecordingRequestRepository : IRequestRepository
    {
        public bool TechnicianOk { get; init; }
        public bool Inserted { get; private set; }
        public Guid InsertedId { get; } = Guid.NewGuid();
        public string? Description { get; private set; }
        public Guid DispatcherUserId { get; private set; }
        public IReadOnlyList<int>? ObjectIds { get; private set; }
        public int? Priority { get; private set; }
        public bool StatusExists { get; init; }
        public bool UpdateAffected { get; init; }
        public bool StatusUpdated { get; private set; }
        public Guid UpdatedId { get; private set; }
        public string? UpdatedStatus { get; private set; }

        public Task<bool> ForecastJournalExistsAsync(Guid id, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<bool> IsActiveTechnicianAsync(Guid userId, CancellationToken cancellationToken = default)
            => Task.FromResult(TechnicianOk);

        public Task<Guid> InsertAsync(
            Guid forecastJournalId,
            string description,
            Guid dispatcherUserId,
            Guid technicianId,
            IReadOnlyList<int> objectIds,
            int? priority,
            CancellationToken cancellationToken = default)
        {
            Inserted = true;
            Description = description;
            DispatcherUserId = dispatcherUserId;
            ObjectIds = objectIds;
            Priority = priority;
            return Task.FromResult(InsertedId);
        }

        public Task<(IReadOnlyList<RequestListItem> Items, int Total)> ListAsync(
            Guid? restrictToUserId,
            int offset,
            int limit,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<RequestHeader?> GetHeaderAsync(
            Guid id,
            Guid? restrictToUserId,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<bool> StatusExistsAsync(string name, CancellationToken cancellationToken = default)
            => Task.FromResult(StatusExists);

        public Task<bool> UpdateStatusAsync(
            Guid id,
            string statusName,
            Guid? restrictToUserId,
            CancellationToken cancellationToken = default)
        {
            StatusUpdated = true;
            UpdatedId = id;
            UpdatedStatus = statusName;
            return Task.FromResult(UpdateAffected);
        }
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
