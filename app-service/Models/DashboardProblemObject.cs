namespace AppService.Models;

public sealed record DashboardProblemObject(int Id, string Name, IReadOnlyList<string> Statuses);
