namespace AppService.Contracts;

public sealed record RequestListResponse(
    IReadOnlyList<RequestListItemResponse> Items,
    int Total);
