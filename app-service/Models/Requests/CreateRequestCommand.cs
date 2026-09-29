namespace AppService.Models;

public sealed record CreateRequestCommand(
    Guid ForecastJournalId,
    int DispatcherObjectId,
    string Description,
    int? Priority,
    Guid TechnicianId);
