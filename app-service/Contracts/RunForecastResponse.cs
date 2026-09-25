namespace AppService.Contracts;

public sealed record RunForecastResponse(
    Guid ForecastJournalId,
    string Status,
    DateTimeOffset CreatedAt,
    IReadOnlyList<int>? DispatcherObjectIds);
