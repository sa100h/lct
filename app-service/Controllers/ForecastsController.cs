using System.Globalization;
using System.IdentityModel.Tokens.Jwt;
using AppService.Contracts;
using AppService.Models;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("forecasts")]
public sealed class ForecastsController(
    IForecastRunService forecasts,
    IForecastHistoryQueryService history) : ControllerBase
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

    [HttpGet("authors")]
    [Authorize(Policy = PermissionCodes.ModuleHistory)]
    [ProducesResponseType(typeof(IReadOnlyList<ForecastAuthorResponse>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<ForecastAuthorResponse>>> Authors(
        CancellationToken cancellationToken)
    {
        var authors = await history.ListAuthorsAsync(cancellationToken);
        return Ok(authors.Select(author => new ForecastAuthorResponse(author.Id, author.Login)).ToArray());
    }

    [HttpGet]
    [Authorize(Policy = PermissionCodes.ModuleHistory)]
    [ProducesResponseType(typeof(ForecastHistoryListResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<ForecastHistoryListResponse>> List(
        [FromQuery] Guid? createdBy,
        [FromQuery] string? from,
        [FromQuery] string? to,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20,
        CancellationToken cancellationToken = default)
    {
        DateOnly? fromDate = null;
        DateOnly? toDate = null;
        if (from is not null)
        {
            if (!DateOnly.TryParseExact(
                    from,
                    "yyyy-MM-dd",
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.None,
                    out var parsedFrom))
            {
                return BadRequest();
            }

            fromDate = parsedFrom;
        }

        if (to is not null)
        {
            if (!DateOnly.TryParseExact(
                    to,
                    "yyyy-MM-dd",
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.None,
                    out var parsedTo))
            {
                return BadRequest();
            }

            toDate = parsedTo;
        }

        try
        {
            var pageResult = await history.ListAsync(
                new ForecastHistoryListQuery(createdBy, fromDate, toDate, page, pageSize),
                cancellationToken);
            return Ok(new ForecastHistoryListResponse(
                pageResult.Items
                    .Select(item => new ForecastHistoryListItemResponse(
                        item.Id,
                        item.CreatedAt,
                        item.AuthorLogin,
                        item.Status,
                        item.ObjectCount))
                    .ToArray(),
                pageResult.Total));
        }
        catch (ArgumentException)
        {
            return BadRequest();
        }
    }

    [HttpGet("{id:guid}")]
    [Authorize(Policy = PermissionCodes.ModuleHistory)]
    [ProducesResponseType(typeof(ForecastHistoryDetailResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ForecastHistoryDetailResponse>> GetById(
        Guid id,
        CancellationToken cancellationToken)
    {
        var detail = await history.GetByIdAsync(id, cancellationToken);
        if (detail is null)
        {
            return NotFound();
        }

        return Ok(new ForecastHistoryDetailResponse(
            detail.Id,
            detail.CreatedAt,
            detail.AuthorLogin,
            detail.Status,
            detail.Objects
                .Select(item => new ForecastHistoryObjectResponse(
                    item.Id,
                    item.ParentId,
                    item.Name,
                    item.Latitude,
                    item.Longitude,
                    item.Statuses,
                    item.HasHighRisk))
                .ToArray()));
    }
}
