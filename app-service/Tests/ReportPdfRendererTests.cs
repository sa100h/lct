using AppService.Models;
using AppService.Services.Domain;
using AppService.Services.Infrastructure;
using Xunit;

namespace AppService.Tests;

public sealed class ReportPdfRendererTests
{
    [Fact]
    public void Render_SummaryEmpty_IsPdf()
    {
        var pdf = new ReportPdfRenderer().Render(EmptySummary());
        Assert.True(pdf.Length > 100);
        Assert.Equal("%PDF"u8.ToArray(), pdf.AsSpan(0, 4).ToArray());
    }

    private static ReportDocument EmptySummary()
        => new(
            new ReportHeader(
                "Оперативная сводка",
                new DateOnly(2026, 9, 1),
                new DateOnly(2026, 9, 1),
                new DateTimeOffset(2026, 9, 28, 12, 0, 0, TimeSpan.Zero),
                "svodka_2026-09-01_2026-09-01.pdf"),
            new SummaryReportBody(
                new SummaryReport(
                    0,
                    DashboardQueryService.RequestStatusOrder.Select(name => new ReportStatusCount(name, 0)).ToArray(),
                    0,
                    DashboardQueryService.ForecastStatusOrder.Select(name => new ReportStatusCount(name, 0)).ToArray(),
                    [new ReportDayCount(new DateOnly(2026, 9, 1), 0)],
                    [new ReportDayCount(new DateOnly(2026, 9, 1), 0)])));
}
