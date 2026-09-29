namespace AppService.Contracts;

public sealed record CreateRequestBody(
    Guid ForecastJournalId,
    IReadOnlyList<int> DispatcherObjectIds,
    string Description,
    int? Priority,
    Guid TechnicianId);
