using AppService.Contracts;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("dispatcher_objects")]
public sealed class DispatcherObjectsController(
    IDispatcherObjectQueryService dispatcherObjects) : ControllerBase
{
    [HttpGet]
    [Authorize(Policy = PermissionCodes.ModuleMap)]
    [ProducesResponseType(typeof(IReadOnlyList<DispatcherObjectResponse>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<DispatcherObjectResponse>>> GetAll(
        CancellationToken cancellationToken)
    {
        var objects = await dispatcherObjects.GetAllAsync(cancellationToken);
        return Ok(objects.Select(item => new DispatcherObjectResponse(
            item.Id,
            item.ParentId,
            item.Name,
            item.ObjectTypeId,
            item.ObjectTypeName,
            item.Longitude,
            item.Latitude,
            item.Statuses,
            item.ChannelCount)));
    }
}
