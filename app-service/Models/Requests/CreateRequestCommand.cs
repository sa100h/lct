namespace AppService.Models;

public sealed record CreateRequestCommand(
    Guid ForecastJournalId,
    IReadOnlyList<int> DispatcherObjectIds,
    string Description,
    int? Priority,
    Guid TechnicianId);
