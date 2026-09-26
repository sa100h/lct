using AppService.Models;

namespace AppService.Services.Domain;

public sealed class ForecastHistoryQueryService(
    IForecastJournalRepository journal,
    IDispatcherObjectRepository objects) : IForecastHistoryQueryService
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
        var selected = header.DispatcherObjectIds is null
            ? all
            : all.Where(item => header.DispatcherObjectIds.Contains(item.Id)).ToArray();

        var mapped = selected
            .Select(item => new ForecastHistoryObject(
                item.Id,
                item.ParentId,
                item.Name,
                item.Latitude,
                item.Longitude,
                item.Statuses,
                false))
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
