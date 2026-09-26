namespace AppService.Models;

public sealed record ForecastHistoryListQuery(
    Guid? CreatedBy,
    DateOnly? From,
    DateOnly? To,
    int Page,
    int PageSize);
