namespace AppService.Services.Domain;

public static class ForecastHistoryStatus
{
    public const string Approved = "approved";

    public static string Resolve(
        string? journalStatus,
        DateTimeOffset? start,
        DateTimeOffset? end)
    {
        if (string.Equals(journalStatus, Approved, StringComparison.Ordinal))
        {
            return Approved;
        }

        return DashboardQueryService.MapForecastStatus(start, end);
    }
}
