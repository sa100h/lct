using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ReportCodesTests
{
    [Fact]
    public void TryGet_KnownAndFileName()
    {
        Assert.True(ReportCodes.TryGet("summary", out var info));
        Assert.Equal("Оперативная сводка", info.Title);
        Assert.Equal(
            "svodka_2026-09-01_2026-09-28.pdf",
            ReportCodes.FileName(info.FileStem, new DateOnly(2026, 9, 1), new DateOnly(2026, 9, 28)));
    }

    [Fact]
    public void TryGet_Unknown_IsFalse()
        => Assert.False(ReportCodes.TryGet("nope", out _));

    [Fact]
    public void TryGet_Deviations_IsFalse()
        => Assert.False(ReportCodes.TryGet("deviations", out _));
}
