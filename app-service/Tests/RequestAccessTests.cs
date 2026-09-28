using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class RequestAccessTests
{
    [Theory]
    [InlineData("admin", true)]
    [InlineData("dispatcher_ods", true)]
    [InlineData("technician", false)]
    [InlineData("dispatcher_district", false)]
    public void SeesAll_ByJwtRole(string role, bool expected)
        => Assert.Equal(expected, RequestAccess.SeesAll(role));
}
