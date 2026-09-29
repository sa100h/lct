namespace AppService.Models;

public sealed record ForecastJournalReportRow(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    DateTimeOffset? StartCompositionTime,
    DateTimeOffset? EndCompositionTime,
    int ObjectCount);
