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
                snapshot.Objects.Deviation,
                snapshot.Objects.ProblemObjects
                    .Select(item => new DashboardProblemObjectResponse(item.Id, item.Name, item.Statuses))
                    .ToArray()),
            snapshot.Events
                .Select(item => new DashboardEventResponse(
                    item.Id,
                    item.OccurredAt,
                    item.ObjectId,
                    item.ObjectName,
                    item.ChannelName,
                    item.IsAlarm,
                    item.Value))
                .ToArray(),
            snapshot.Forecasts
                .Select(item => new DashboardForecastResponse(item.Id, item.CreatedAt, item.Status))
                .ToArray(),
            snapshot.Requests
                .Select(item => new DashboardRequestResponse(
                    item.Id,
                    item.Description,
                    item.ObjectId,
                    item.ObjectName,
                    item.Status))
                .ToArray());
}
