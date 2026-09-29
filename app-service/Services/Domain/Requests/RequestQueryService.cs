using AppService.Models;

namespace AppService.Services.Domain;

public sealed class RequestQueryService(
    IRequestRepository requests,
    IDispatcherObjectRepository objects) : IRequestQueryService
{
    public const int MaxPageSize = 20;

    public async Task<RequestListPage> ListAsync(
        bool seesAll,
        Guid userId,
        int page,
        int pageSize,
        CancellationToken cancellationToken = default)
    {
        if (page < 1 || pageSize < 1)
        {
            throw new ArgumentException("Invalid page.");
        }

        var limit = Math.Min(pageSize, MaxPageSize);
        var offset = (page - 1) * limit;
        var (items, total) = await requests.ListAsync(
            Restrict(seesAll, userId),
            offset,
            limit,
            cancellationToken);
        return new RequestListPage(items, total);
    }

    public async Task<RequestDetail?> GetAsync(
        bool seesAll,
        Guid userId,
        Guid id,
        CancellationToken cancellationToken = default)
    {
        var header = await requests.GetHeaderAsync(id, Restrict(seesAll, userId), cancellationToken);
        if (header is null)
        {
            return null;
        }

        var all = await objects.GetAllWithDescendantStatusesAsync(cancellationToken);
        var byId = all.ToDictionary(item => item.Id);
        var includedIds = new HashSet<int>();
        foreach (var objectId in header.DispatcherObjectIds)
        {
            int? currentId = objectId;
            while (currentId is int ancestorId && byId.TryGetValue(ancestorId, out var current)
                   && includedIds.Add(ancestorId))
            {
                currentId = current.ParentId;
            }
        }

        var mapped = all
            .Where(item => includedIds.Contains(item.Id))
            .Select(item => new RequestDetailObject(
                item.Id,
                item.ParentId,
                item.Name,
                item.Latitude,
                item.Longitude,
                item.Statuses,
                item.OwnStatuses,
                item.OwnChannelCount))
            .ToArray();

        return new RequestDetail(
            header.Id,
            header.CreatedAt,
            header.Description,
            header.Status,
            header.DispatcherLogin,
            header.TechnicianLogin,
            header.Priority,
            header.ObjectId,
            header.ObjectName,
            mapped);
    }

    private static Guid? Restrict(bool seesAll, Guid userId)
        => seesAll ? null : userId;
}
