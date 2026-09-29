using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastJournalTreeTests
{
    [Fact]
    public void AllowedIds_IncludesAncestorsOfChannelObjects()
    {
        var all = new DispatcherObjectInfo[]
        {
            Item(1, null),
            Item(2, 1),
            Item(3, null),
        };
        var allowed = ForecastJournalTree.AllowedIds([2], all);
        Assert.Equal(new HashSet<int> { 1, 2 }, allowed);
        Assert.DoesNotContain(3, allowed);
    }

    [Fact]
    public void AllowedIds_EmptySelection_IsEmpty()
        => Assert.Empty(ForecastJournalTree.AllowedIds(null, []));

    private static DispatcherObjectInfo Item(int id, int? parent)
        => new(id, parent, $"o{id}", 1, "district", 0, 0, [], 0, [], 0);
}
