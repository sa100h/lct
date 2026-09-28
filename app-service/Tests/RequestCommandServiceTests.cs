using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class RequestCommandServiceTests
{
    [Fact]
    public async Task CreateAsync_InsertsSubtreeIds()
    {
        var journalId = Guid.NewGuid();
        var technicianId = Guid.NewGuid();
        var dispatcherId = Guid.NewGuid();
        var requests = new RecordingRequestRepository { JournalExists = true, TechnicianOk = true };
        var objects = new StubSubtreeRepository([5, 5122]);
        var service = new RequestCommandService(requests, objects);

        var id = await service.CreateAsync(
            dispatcherId,
            new CreateRequestCommand(journalId, 5, "  Утечка  ", 2, technicianId),
            TestContext.Current.CancellationToken);

        Assert.Equal(requests.InsertedId, id);
        Assert.Equal("Утечка", requests.Description);
        Assert.Equal(dispatcherId, requests.DispatcherUserId);
        Assert.Equal([5, 5122], requests.ObjectIds);
        Assert.Equal(2, requests.Priority);
    }

    [Fact]
    public async Task CreateAsync_RejectsBlankDescription()
    {
        var requests = new RecordingRequestRepository { JournalExists = true, TechnicianOk = true };
        var service = new RequestCommandService(requests, new StubSubtreeRepository([5]));

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), 5, "  ", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.DescriptionRequired, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsMissingJournal()
    {
        var requests = new RecordingRequestRepository { JournalExists = false, TechnicianOk = true };
        var service = new RequestCommandService(requests, new StubSubtreeRepository([5]));

        var exception = await Assert.ThrowsAsync<KeyNotFoundException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), 5, "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingJournal, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsNonTechnician()
    {
        var requests = new RecordingRequestRepository { JournalExists = true, TechnicianOk = false };
        var service = new RequestCommandService(requests, new StubSubtreeRepository([5]));

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), 5, "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingTechnician, exception.Message);
        Assert.False(requests.Inserted);
    }

    [Fact]
    public async Task CreateAsync_RejectsUnknownObject()
    {
        var requests = new RecordingRequestRepository { JournalExists = true, TechnicianOk = true };
        var service = new RequestCommandService(requests, new StubSubtreeRepository([]));

        var exception = await Assert.ThrowsAsync<ArgumentException>(() => service.CreateAsync(
            Guid.NewGuid(),
            new CreateRequestCommand(Guid.NewGuid(), 999, "text", null, Guid.NewGuid()),
            TestContext.Current.CancellationToken));

        Assert.Equal(RequestCommandService.MissingObject, exception.Message);
        Assert.False(requests.Inserted);
    }

    private sealed class RecordingRequestRepository : IRequestRepository
    {
        public bool JournalExists { get; init; }
        public bool TechnicianOk { get; init; }
        public bool Inserted { get; private set; }
        public Guid InsertedId { get; } = Guid.NewGuid();
        public string? Description { get; private set; }
        public Guid DispatcherUserId { get; private set; }
        public IReadOnlyList<int>? ObjectIds { get; private set; }
        public int? Priority { get; private set; }

        public Task<bool> ForecastJournalExistsAsync(Guid id, CancellationToken cancellationToken = default)
            => Task.FromResult(JournalExists);

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
