namespace AppService.Contracts;

public sealed record DashboardProblemObjectResponse(int Id, string Name, IReadOnlyList<string> Statuses);
