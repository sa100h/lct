using System.IdentityModel.Tokens.Jwt;
using AppService.Contracts;
using AppService.Models;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("requests")]
public sealed class RequestsController(IRequestCommandService requests) : ControllerBase
{
    [HttpPost]
    [Authorize(Policy = PermissionCodes.ModuleRequests)]
    [ProducesResponseType(typeof(CreateRequestResponse), StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<CreateRequestResponse>> Create(
        [FromBody] CreateRequestBody body,
        CancellationToken cancellationToken)
    {
        if (!Guid.TryParse(User.FindFirst(JwtRegisteredClaimNames.Sub)?.Value, out var userId))
        {
            return Unauthorized();
        }

        try
        {
            var id = await requests.CreateAsync(
                userId,
                new CreateRequestCommand(
                    body.ForecastJournalId,
                    body.DispatcherObjectId,
                    body.Description,
                    body.Priority,
                    body.TechnicianId),
                cancellationToken);
            return StatusCode(StatusCodes.Status201Created, new CreateRequestResponse(id));
        }
        catch (KeyNotFoundException exception)
        {
            return NotFound(new { error = exception.Message });
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { error = exception.Message });
        }
    }
}
