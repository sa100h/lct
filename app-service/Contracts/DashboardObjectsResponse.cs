namespace AppService.Contracts;

public sealed record DashboardObjectsResponse(
    int Total,
    int Normal,
    int Deviation,
    IReadOnlyList<DashboardProblemObjectResponse> ProblemObjects);
