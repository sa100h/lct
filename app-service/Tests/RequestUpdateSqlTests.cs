using AppService.Data.Repositories;
using Xunit;

namespace AppService.Tests;

public sealed class RequestUpdateSqlTests
{
    [Fact]
    public void UpdateStatusSql_AliasesRequestsAsR()
    {
        Assert.Contains("UPDATE requests r", NpgsqlRequestRepository.UpdateStatusSql);
        Assert.Contains("r.user_dispatcher_id", NpgsqlRequestRepository.UpdateStatusSql);
        Assert.Contains("r.user_technician_id", NpgsqlRequestRepository.UpdateStatusSql);
        Assert.DoesNotContain("UPDATE requests\n", NpgsqlRequestRepository.UpdateStatusSql);
    }
}
