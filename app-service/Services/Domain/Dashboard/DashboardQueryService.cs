using AppService.Models;

namespace AppService.Services.Domain;

public sealed class DashboardQueryService(
    IDispatcherObjectRepository objects,
    IDashboardFeedRepository feeds,
    TimeProvider clock) : IDashboardQueryService
{
    public const int ChartDays = 14;
    public const string NormalStatus = "Норма";

    public static readonly string[] RequestStatusOrder = ["Новая", "В работе", "Закрыта"];
    public static readonly string[] ForecastStatusOrder = ["pending", "running", "done"];

    public async Task<DashboardSnapshot> GetAsync(CancellationToken cancellationToken = default)
    {
        var all = await objects.GetAllWithDescendantStatusesAsync(cancellationToken);
        var today = UtcToday(clock);
        var fromInclusive = new DateTimeOffset(today.AddDays(1 - ChartDays).ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc));
        var toExclusive = new DateTimeOffset(today.AddDays(1).ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc));

        var alarms = await feeds.GetAlarmCountsByDayAsync(fromInclusive, toExclusive, cancellationToken);
        var requestStatuses = await feeds.GetRequestCountsByStatusAsync(cancellationToken);
        var requestsByDay = await feeds.GetRequestCountsByDayAsync(fromInclusive, toExclusive, cancellationToken);
        var forecastStatuses = await feeds.GetForecastCountsByStatusAsync(fromInclusive, toExclusive, cancellationToken);

        var normal = 0;
        foreach (var item in all)
        {
            if (IsNormal(item.Statuses))
            {
                normal++;
            }
        }

        var summary = new DashboardObjectSummary(all.Count, normal, all.Count - normal);

        var requestsByStatus = PadStatuses(RequestStatusOrder, requestStatuses);
        return new DashboardSnapshot(
            summary,
            PadDays(today, alarms),
            requestsByStatus.Sum(item => item.Count),
            requestsByStatus,
            PadDays(today, requestsByDay),
            PadStatuses(ForecastStatusOrder, forecastStatuses));
    }

    public static DateOnly UtcToday(TimeProvider time)
        => DateOnly.FromDateTime(time.GetUtcNow().UtcDateTime);

    public static IReadOnlyList<DashboardDayCount> PadDays(
        DateOnly toInclusive,
        IReadOnlyDictionary<DateOnly, int> counts)
    {
        var from = toInclusive.AddDays(1 - ChartDays);
        return Enumerable.Range(0, ChartDays)
            .Select(offset =>
            {
                var day = from.AddDays(offset);
                return new DashboardDayCount(day, counts.GetValueOrDefault(day));
            })
            .ToArray();
    }

    public static IReadOnlyList<DashboardStatusCount> PadStatuses(
        IReadOnlyList<string> order,
        IEnumerable<DashboardStatusCount> rows)
    {
        var map = rows.ToDictionary(row => row.Status, row => row.Count, StringComparer.Ordinal);
        return order
            .Select(name => new DashboardStatusCount(name, map.GetValueOrDefault(name)))
            .ToArray();
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
