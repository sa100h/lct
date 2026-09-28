using AppService.Contracts;
using AppService.Models;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("dashboard")]
public sealed class DashboardController(IDashboardQueryService dashboard) : ControllerBase
{
    [HttpGet]
    [Authorize(Policy = PermissionCodes.ModuleDashboard)]
    [ProducesResponseType(typeof(DashboardResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<DashboardResponse>> Get(CancellationToken cancellationToken)
    {
        var snapshot = await dashboard.GetAsync(cancellationToken);
        return Ok(ToResponse(snapshot));
    }

    private static DashboardResponse ToResponse(DashboardSnapshot snapshot)
        => new(
            new DashboardObjectsResponse(
                snapshot.Objects.Total,
                snapshot.Objects.Normal,
                snapshot.Objects.Deviation),
            snapshot.AlarmsByDay
                .Select(item => new DashboardDayCountResponse(item.Date, item.Count))
                .ToArray(),
            snapshot.RequestsTotal,
            snapshot.RequestsByStatus
                .Select(item => new DashboardStatusCountResponse(item.Status, item.Count))
                .ToArray(),
            snapshot.RequestsByDay
                .Select(item => new DashboardDayCountResponse(item.Date, item.Count))
                .ToArray(),
            snapshot.ForecastsByStatus
                .Select(item => new DashboardStatusCountResponse(item.Status, item.Count))
                .ToArray());
}
