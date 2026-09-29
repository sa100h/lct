namespace AppService.Models;

public sealed record ForecastReportRow(
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    int ObjectCount);
