using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Shared.Authentication;

namespace AppService.Controllers;

[ApiController]
[Route("authz/demo")]
public sealed class AuthzDemoController : ControllerBase
{
    [HttpGet]
    [Authorize(Policy = PermissionCodes.DemoAccess)]
    public IActionResult Get()
        => Ok(new
        {
            role = User.FindFirst(JwtClaimNames.Role)?.Value,
            permissions = User.FindAll(JwtClaimNames.Permission).Select(claim => claim.Value).ToArray()
        });
}
