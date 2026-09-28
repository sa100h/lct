using AppService.Contracts;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("users")]
public sealed class UsersController(IUserQueryService users) : ControllerBase
{
    [HttpGet]
    [Authorize(Policy = PermissionCodes.ModuleRequests)]
    [ProducesResponseType(typeof(IReadOnlyList<UserListItemResponse>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<IReadOnlyList<UserListItemResponse>>> List(
        [FromQuery] string? role,
        CancellationToken cancellationToken)
    {
        try
        {
            var items = await users.ListByRoleNameAsync(role ?? "", cancellationToken);
            return Ok(items.Select(item => new UserListItemResponse(item.Id, item.Login)).ToArray());
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { error = exception.Message });
        }
    }
}
