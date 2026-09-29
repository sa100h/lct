namespace AppService.Models;

public sealed record ForecastReportBody(
    int DoneCount,
    int HighRiskObjects,
    IReadOnlyList<ForecastReportRow> Rows) : IReportBody;
