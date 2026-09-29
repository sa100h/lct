using System.IdentityModel.Tokens.Jwt;
using AppService.Contracts;
using AppService.Models;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Shared.Authentication;

namespace AppService.Controllers;

[ApiController]
[Route("requests")]
public sealed class RequestsController(
    IRequestCommandService commands,
    IRequestQueryService queries) : ControllerBase
{
    [HttpGet]
    [Authorize(Policy = PermissionCodes.ModuleRequests)]
    [ProducesResponseType(typeof(RequestListResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<RequestListResponse>> List(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20,
        CancellationToken cancellationToken = default)
    {
        if (!TryActor(out var userId, out var seesAll))
        {
            return Unauthorized();
        }

        try
        {
            var pageResult = await queries.ListAsync(seesAll, userId, page, pageSize, cancellationToken);
            return Ok(new RequestListResponse(
                pageResult.Items
                    .Select(item => new RequestListItemResponse(
                        item.Id,
                        item.CreatedAt,
                        item.Description,
                        item.ObjectId,
                        item.ObjectName,
                        item.Status,
                        item.DispatcherLogin,
                        item.TechnicianLogin))
                    .ToArray(),
                pageResult.Total));
        }
        catch (ArgumentException)
        {
            return BadRequest();
        }
    }

    [HttpGet("{id:guid}")]
    [Authorize(Policy = PermissionCodes.ModuleRequests)]
    [ProducesResponseType(typeof(RequestDetailResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<RequestDetailResponse>> GetById(
        Guid id,
        CancellationToken cancellationToken)
    {
        if (!TryActor(out var userId, out var seesAll))
        {
            return Unauthorized();
        }

        var detail = await queries.GetAsync(seesAll, userId, id, cancellationToken);
        if (detail is null)
        {
            return NotFound(new { error = RequestCommandService.MissingRequest });
        }

        return Ok(new RequestDetailResponse(
            detail.Id,
            detail.CreatedAt,
            detail.Description,
            detail.Status,
            detail.DispatcherLogin,
            detail.TechnicianLogin,
            detail.Priority,
            detail.ObjectId,
            detail.ObjectName,
            detail.Objects
                .Select(item => new RequestDetailObjectResponse(
                    item.Id,
                    item.ParentId,
                    item.Name,
                    item.Latitude,
                    item.Longitude,
                    item.Statuses,
                    item.OwnStatuses,
                    item.OwnChannelCount))
                .ToArray()));
    }

    [HttpPatch("{id:guid}/status")]
    [Authorize(Policy = PermissionCodes.ModuleRequests)]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> PatchStatus(
        Guid id,
        [FromBody] PatchRequestStatusBody body,
        CancellationToken cancellationToken)
    {
        if (!TryActor(out var userId, out var seesAll))
        {
            return Unauthorized();
        }

        try
        {
            await commands.UpdateStatusAsync(id, seesAll, userId, body?.Status ?? "", cancellationToken);
            return NoContent();
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
            var id = await commands.CreateAsync(
                userId,
                new CreateRequestCommand(
                    body.ForecastJournalId,
                    body.DispatcherObjectIds ?? [],
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

    private bool TryActor(out Guid userId, out bool seesAll)
    {
        seesAll = RequestAccess.SeesAll(User.FindFirst(JwtClaimNames.Role)?.Value);
        return Guid.TryParse(User.FindFirst(JwtRegisteredClaimNames.Sub)?.Value, out userId);
    }
}
