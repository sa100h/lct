using AppService.Models;
using AppService.Services.Infrastructure;

namespace AppService.Services.Domain;

public sealed class ForecastHistoryQueryService(
    IForecastJournalRepository journal,
    IDispatcherObjectRepository objects,
    IForecastResultRepository results,
    IForecastChannelRepository channels,
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
                ForecastHistoryStatus.Resolve(
                    row.JournalStatus,
                    row.StartCompositionTime,
                    row.EndCompositionTime),
                row.ObjectCount,
                row.ApprovedByLogin,
                row.ApprovedAt))
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
        var includedIds = ForecastJournalTree.AllowedIds(header.DispatcherObjectIds, all);
        var selected = all.Where(item => includedIds.Contains(item.Id)).ToArray();
        var rows = await results.ListByJournalAsync(id, cancellationToken);
        var parsedRows = selected
            .Select(item =>
            {
                rows.TryGetValue(item.Id, out var row);
                var parsed = ForecastRisk.Parse(
                    row?.Description,
                    forecast.RiskThreshold,
                    forecast.RiskThresholds);
                var erroneous = row?.IsErroneous == true;
                return (item, row, parsed, erroneous);
            })
            .ToArray();
        var names = await channels.GetNamesByIdsAsync(
            ForecastChannelNames.NumericIds(parsedRows.SelectMany(entry => entry.parsed.Values)),
            cancellationToken);

        var mapped = parsedRows
            .Select(entry =>
            {
                var hasResult = entry.row is not null;
                var risk = entry.erroneous ? false : entry.parsed.HighRisk;
                return new ForecastHistoryObject(
                    entry.item.Id,
                    entry.item.ParentId,
                    entry.item.Name,
                    entry.item.Latitude,
                    entry.item.Longitude,
                    entry.item.Statuses,
                    risk,
                    entry.item.OwnStatuses,
                    entry.item.OwnChannelCount,
                    entry.erroneous,
                    entry.row?.IsRequestCreated == true,
                    hasResult,
                    ForecastChannelNames.Attach(entry.parsed.Values, names));
            })
            .ToArray();

        return new ForecastHistoryDetail(
            header.Id,
            header.CreatedAt,
            header.AuthorLogin,
            ForecastHistoryStatus.Resolve(
                header.JournalStatus,
                header.StartCompositionTime,
                header.EndCompositionTime),
            header.ApprovedByLogin,
            header.ApprovedAt,
            mapped);
    }
}
