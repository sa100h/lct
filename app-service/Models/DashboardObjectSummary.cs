namespace AppService.Models;

public sealed record DashboardObjectSummary(
    int Total,
    int Normal,
    int Deviation,
    IReadOnlyList<DashboardProblemObject> ProblemObjects);
