using AppService.Models;

namespace AppService.Services.Domain;

public static class ReportPeriod
{
    public const int MaxInclusiveDays = 93;

    public static readonly TimeZoneInfo Moscow = TimeZoneInfo.FindSystemTimeZoneById("Europe/Moscow");

    public static bool TryCreate(DateOnly from, DateOnly to, out ReportUtcRange range)
    {
        var days = to.DayNumber - from.DayNumber + 1;
        if (to < from || days > MaxInclusiveDays)
        {
            range = new ReportUtcRange(default, default);
            return false;
        }

        var start = DateTime.SpecifyKind(from.ToDateTime(TimeOnly.MinValue), DateTimeKind.Unspecified);
        var end = DateTime.SpecifyKind(to.AddDays(1).ToDateTime(TimeOnly.MinValue), DateTimeKind.Unspecified);
        range = new ReportUtcRange(
            new DateTimeOffset(TimeZoneInfo.ConvertTimeToUtc(start, Moscow), TimeSpan.Zero),
            new DateTimeOffset(TimeZoneInfo.ConvertTimeToUtc(end, Moscow), TimeSpan.Zero));
        return true;
    }
}
