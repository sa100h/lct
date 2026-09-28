using AppService.Models;

namespace AppService.Services.Domain;

public sealed class DashboardQueryService(
    IDispatcherObjectRepository objects,
    IDashboardFeedRepository feeds) : IDashboardQueryService
{
    public const int ProblemObjectLimit = 20;
    public const string NormalStatus = "Норма";

    public async Task<DashboardSnapshot> GetAsync(CancellationToken cancellationToken = default)
    {
        var all = await objects.GetAllWithDescendantStatusesAsync(cancellationToken);
        var events = await feeds.GetRecentEventsAsync(cancellationToken);
        var forecastRows = await feeds.GetRecentForecastsAsync(cancellationToken);

        var normal = 0;
        var problems = new List<DashboardProblemObject>();
        foreach (var item in all)
        {
            if (IsNormal(item.Statuses))
            {
                normal++;
                continue;
            }

            problems.Add(new DashboardProblemObject(item.Id, item.Name, item.Statuses));
        }

        var summary = new DashboardObjectSummary(
            all.Count,
            normal,
            all.Count - normal,
            problems.Take(ProblemObjectLimit).ToArray());

        var forecasts = forecastRows
            .Select(row => new DashboardForecastItem(
                row.Id,
                row.CreatedAt,
                MapForecastStatus(row.StartCompositionTime, row.EndCompositionTime)))
            .ToArray();

        return new DashboardSnapshot(summary, events, forecasts);
    }

    public static bool IsNormal(IReadOnlyList<string> statuses)
        => statuses.Count == 0 || statuses.All(status => status == NormalStatus);

    public static string MapForecastStatus(DateTimeOffset? start, DateTimeOffset? end)
    {
        if (end is not null)
        {
            return "done";
        }

        if (start is not null)
        {
            return "running";
        }

        return "pending";
    }
}
