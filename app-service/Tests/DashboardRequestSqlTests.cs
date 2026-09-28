using AppService.Data.Repositories;
using Xunit;

namespace AppService.Tests;

public sealed class DashboardRequestSqlTests
{
    [Fact]
    public void RecentRequestsSql_UsesJsonArrayNotDroppedColumn()
    {
        Assert.Contains("dispatcher_objects_id", NpgsqlDashboardFeedRepository.RecentRequestsSql);
        Assert.DoesNotContain("r.dispatcher_object_id", NpgsqlDashboardFeedRepository.RecentRequestsSql);
        Assert.Contains("->> 0", NpgsqlDashboardFeedRepository.RecentRequestsSql);
    }
}
