using AppService.Models;
using AppService.Services.Infrastructure;

namespace AppService.Services.Domain;

public sealed class ReportQueryService(
    IReportFeedRepository feeds,
    ForecastOptions forecast,
    TimeProvider clock) : IReportQueryService
{
    public const int TableLimit = 2000;

    public async Task<ReportDocument> BuildAsync(
        string code,
        DateOnly from,
        DateOnly to,
        CancellationToken cancellationToken = default)
    {
        if (!ReportPeriod.TryCreate(from, to, out var range))
        {
            throw new ArgumentException("Invalid period.");
        }

        if (!ReportCodes.TryGet(code, out var info))
        {
            throw new KeyNotFoundException(code);
        }

        var header = new ReportHeader(
            info.Title,
            from,
            to,
            clock.GetUtcNow(),
            ReportCodes.FileName(info.FileStem, from, to));

        IReportBody body = code switch
        {
            "summary" => await BuildSummaryAsync(from, to, range, cancellationToken),
            "alarms" => await BuildAlarmsAsync(range, cancellationToken),
            "requests" => await BuildRequestsAsync(range, cancellationToken),
            "technicians" => await BuildTechniciansAsync(range, cancellationToken),
            "forecasts" => await BuildForecastsAsync(range, cancellationToken),
            _ => throw new NotSupportedException(code),
        };

        return new ReportDocument(header, body);
    }

    private async Task<SummaryReportBody> BuildSummaryAsync(
        DateOnly from,
        DateOnly to,
        ReportUtcRange range,
        CancellationToken cancellationToken)
    {
        var alarmTotal = await feeds.CountAlarmsAsync(
            range.FromInclusive, range.ToExclusive, cancellationToken);
        var alarmsByDay = await feeds.GetAlarmCountsByMoscowDayAsync(
            range.FromInclusive, range.ToExclusive, cancellationToken);
        var requestsByStatus = PadStatuses(
            DashboardQueryService.RequestStatusOrder,
            await feeds.GetRequestCountsByStatusCreatedAsync(
                range.FromInclusive, range.ToExclusive, cancellationToken));
        var requestsByDay = await feeds.GetRequestCountsByMoscowDayAsync(
            range.FromInclusive, range.ToExclusive, cancellationToken);
        var forecastsByStatus = PadStatuses(
            DashboardQueryService.ForecastStatusOrder,
            await feeds.GetForecastCountsByStatusAsync(
                range.FromInclusive, range.ToExclusive, cancellationToken));

        return new SummaryReportBody(
            new SummaryReport(
                alarmTotal,
                requestsByStatus,
                requestsByStatus.Sum(item => item.Count),
                forecastsByStatus,
                PadDays(from, to, alarmsByDay),
                PadDays(from, to, requestsByDay)));
    }

    private async Task<AlarmReportBody> BuildAlarmsAsync(
        ReportUtcRange range,
        CancellationToken cancellationToken)
    {
        var (total, rows) = await feeds.ListAlarmsAsync(
            range.FromInclusive, range.ToExclusive, TableLimit, cancellationToken);
        return new AlarmReportBody(total, rows);
    }

    private async Task<RequestReportBody> BuildRequestsAsync(
        ReportUtcRange range,
        CancellationToken cancellationToken)
    {
        var (total, rows) = await feeds.ListRequestsAsync(
            range.FromInclusive, range.ToExclusive, TableLimit, cancellationToken);
        return new RequestReportBody(total, rows);
    }

    private async Task<TechnicianReportBody> BuildTechniciansAsync(
        ReportUtcRange range,
        CancellationToken cancellationToken)
    {
        var rows = await feeds.ListTechnicianLoadsAsync(
            range.FromInclusive, range.ToExclusive, cancellationToken);
        return new TechnicianReportBody(rows);
    }

    private async Task<ForecastReportBody> BuildForecastsAsync(
        ReportUtcRange range,
        CancellationToken cancellationToken)
    {
        var journals = await feeds.ListForecastJournalsAsync(
            range.FromInclusive, range.ToExclusive, cancellationToken);
        var results = journals.Count == 0
            ? new Dictionary<Guid, IReadOnlyList<ForecastJournalResult>>()
            : await feeds.ListForecastResultsByJournalsAsync(
                journals.Select(item => item.Id).ToArray(), cancellationToken);

        var highRisk = 0;
        var done = 0;
        var rows = new List<ForecastReportRow>(journals.Count);
        foreach (var journal in journals)
        {
            var status = DashboardQueryService.MapForecastStatus(
                journal.StartCompositionTime, journal.EndCompositionTime);
            if (status == "done")
            {
                done++;
            }

            if (results.TryGetValue(journal.Id, out var journalResults))
            {
                foreach (var result in journalResults)
                {
                    if (result.IsErroneous)
                    {
                        continue;
                    }

                    if (ForecastRisk.FromDescription(
                            result.Description,
                            forecast.RiskThreshold,
                            forecast.RiskThresholds) == true)
                    {
                        highRisk++;
                    }
                }
            }

            rows.Add(new ForecastReportRow(
                journal.CreatedAt, journal.AuthorLogin, status, journal.ObjectCount));
        }

        return new ForecastReportBody(done, highRisk, rows);
    }

    private static IReadOnlyList<ReportStatusCount> PadStatuses(
        IReadOnlyList<string> order,
        IEnumerable<ReportStatusCount> rows)
    {
        var map = rows.ToDictionary(row => row.Status, row => row.Count, StringComparer.Ordinal);
        var known = new HashSet<string>(order, StringComparer.Ordinal);
        return order
            .Concat(map.Keys.Where(name => !known.Contains(name)))
            .Select(name => new ReportStatusCount(name, map.GetValueOrDefault(name)))
            .ToArray();
    }

    private static IReadOnlyList<ReportDayCount> PadDays(
        DateOnly from,
        DateOnly to,
        IReadOnlyDictionary<DateOnly, int> counts)
    {
        var length = to.DayNumber - from.DayNumber + 1;
        return Enumerable.Range(0, length)
            .Select(offset =>
            {
                var day = from.AddDays(offset);
                return new ReportDayCount(day, counts.GetValueOrDefault(day));
            })
            .ToArray();
    }
}
