using AppService.Models;

namespace AppService.Services.Domain;

public interface IReportFeedRepository
{
    Task<int> CountAlarmsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyDictionary<DateOnly, int>> GetAlarmCountsByMoscowDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<ReportStatusCount>> GetRequestCountsByStatusCreatedAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyDictionary<DateOnly, int>> GetRequestCountsByMoscowDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<ReportStatusCount>> GetForecastCountsByStatusAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<(int Total, IReadOnlyList<AlarmReportRow> Rows)> ListAlarmsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        int limit,
        CancellationToken cancellationToken = default);

    Task<(int Total, IReadOnlyList<RequestReportRow> Rows)> ListRequestsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        int limit,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<TechnicianReportRow>> ListTechnicianLoadsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<ForecastJournalReportRow>> ListForecastJournalsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyDictionary<Guid, IReadOnlyList<ForecastJournalResult>>> ListForecastResultsByJournalsAsync(
        IReadOnlyList<Guid> ids,
        CancellationToken cancellationToken = default);
}
