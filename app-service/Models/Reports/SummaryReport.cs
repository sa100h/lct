namespace AppService.Models;

public sealed record SummaryReport(
    int AlarmTotal,
    IReadOnlyList<ReportStatusCount> RequestsByStatus,
    int RequestsTotal,
    IReadOnlyList<ReportStatusCount> ForecastsByStatus,
    IReadOnlyList<ReportDayCount> AlarmsByDay,
    IReadOnlyList<ReportDayCount> RequestsByDay);
