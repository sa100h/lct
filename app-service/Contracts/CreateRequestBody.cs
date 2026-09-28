namespace AppService.Contracts;

public sealed record CreateRequestBody(
    Guid ForecastJournalId,
    int DispatcherObjectId,
    string Description,
    int? Priority,
    Guid TechnicianId);
