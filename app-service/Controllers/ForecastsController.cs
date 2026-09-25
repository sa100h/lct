using System.IdentityModel.Tokens.Jwt;
using AppService.Contracts;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("forecasts")]
public sealed class ForecastsController(IForecastRunService forecasts) : ControllerBase
{
    [HttpPost("run")]
    [Authorize(Policy = PermissionCodes.ModulePrediction)]
    [ProducesResponseType(typeof(RunForecastResponse), StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<RunForecastResponse>> Run(
        [FromBody] RunForecastRequest request,
        CancellationToken cancellationToken)
    {
        if (!Guid.TryParse(User.FindFirst(JwtRegisteredClaimNames.Sub)?.Value, out var userId))
        {
            return Unauthorized();
        }

        try
        {
            var entry = await forecasts.RunAsync(
                userId,
                request.DispatcherObjectIds,
                cancellationToken);
            return Accepted(new RunForecastResponse(
                entry.Id,
                "pending",
                entry.CreatedAt,
                entry.DispatcherObjectIds));
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { error = exception.Message });
        }
    }
}
