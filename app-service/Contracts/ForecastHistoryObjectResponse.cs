namespace AppService.Contracts;

public sealed record ForecastHistoryObjectResponse(
    int Id,
    int? ParentId,
    string Name,
    double Latitude,
    double Longitude,
    IReadOnlyList<string> Statuses,
    bool? HasHighRisk,
    IReadOnlyList<string> OwnStatuses,
    int OwnChannelCount,
    bool IsErroneous,
    bool IsRequestCreated,
    bool HasResult,
    IReadOnlyList<ForecastChannelValueResponse> ForecastValues);
