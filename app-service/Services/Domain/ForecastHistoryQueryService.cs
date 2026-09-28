using AppService.Models;
using AppService.Services.Infrastructure;

namespace AppService.Services.Domain;

public sealed class ForecastHistoryQueryService(
    IForecastJournalRepository journal,
    IDispatcherObjectRepository objects,
    IForecastResultRepository results,
    ForecastOptions forecast) : IForecastHistoryQueryService
{
    public const int MaxPageSize = 20;

    public Task<IReadOnlyList<ForecastAuthor>> ListAuthorsAsync(
        CancellationToken cancellationToken = default)
        => journal.ListAuthorsAsync(cancellationToken);

    public async Task<ForecastHistoryListPage> ListAsync(
        ForecastHistoryListQuery query,
        CancellationToken cancellationToken = default)
    {
        if (query.Page < 1 || query.PageSize < 1)
        {
            throw new ArgumentException("Invalid page.");
        }

        var limit = Math.Min(query.PageSize, MaxPageSize);
        var offset = (query.Page - 1) * limit;
        var (rows, total) = await journal.ListRowsAsync(
            query.CreatedBy,
            query.From,
            query.To,
            offset,
            limit,
            cancellationToken);

        var items = rows
            .Select(row => new ForecastHistoryListItem(
                row.Id,
                row.CreatedAt,
                row.AuthorLogin,
                DashboardQueryService.MapForecastStatus(
                    row.StartCompositionTime,
                    row.EndCompositionTime),
                row.ObjectCount))
            .ToArray();

        return new ForecastHistoryListPage(items, total);
    }

    public async Task<ForecastHistoryDetail?> GetByIdAsync(
        Guid id,
        CancellationToken cancellationToken = default)
    {
        var header = await journal.GetHeaderAsync(id, cancellationToken);
        if (header is null)
        {
            return null;
        }

        var all = await objects.GetAllWithDescendantStatusesAsync(cancellationToken);
        var byId = all.ToDictionary(item => item.Id);
        var includedIds = new HashSet<int>();
        foreach (var objectId in header.DispatcherObjectIds ?? [])
        {
            int? currentId = objectId;
            while (currentId is int ancestorId && byId.TryGetValue(ancestorId, out var current)
                   && includedIds.Add(ancestorId))
            {
                currentId = current.ParentId;
            }
        }
        var selected = all.Where(item => includedIds.Contains(item.Id));
        var rows = await results.ListByJournalAsync(id, cancellationToken);

        var mapped = selected
            .Select(item =>
            {
                rows.TryGetValue(item.Id, out var row);
                var hasResult = row is not null;
                var parsed = ForecastRisk.Parse(row?.Description, forecast.RiskThreshold);
                var erroneous = row?.IsErroneous == true;
                var risk = erroneous ? false : parsed.HighRisk;
                return new ForecastHistoryObject(
                    item.Id,
                    item.ParentId,
                    item.Name,
                    item.Latitude,
                    item.Longitude,
                    item.Statuses,
                    risk,
                    item.OwnStatuses,
                    item.OwnChannelCount,
                    erroneous,
                    hasResult,
                    parsed.Values);
            })
            .ToArray();

        return new ForecastHistoryDetail(
            header.Id,
            header.CreatedAt,
            header.AuthorLogin,
            DashboardQueryService.MapForecastStatus(
                header.StartCompositionTime,
                header.EndCompositionTime),
            mapped);
    }
}
