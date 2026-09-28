namespace AppService.Contracts;

public sealed record RequestDetailResponse(
    Guid Id,
    DateTimeOffset CreatedAt,
    string Description,
    string Status,
    string DispatcherLogin,
    string TechnicianLogin,
    int? Priority,
    int ObjectId,
    string ObjectName,
    IReadOnlyList<RequestDetailObjectResponse> Objects);
