namespace AppService.Models;

public sealed record ForecastJournalEntry(
    Guid Id,
    DateTimeOffset CreatedAt,
    IReadOnlyList<int>? DispatcherObjectIds);
