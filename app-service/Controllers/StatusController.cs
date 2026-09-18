using AppService.Contracts;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("status")]
public sealed class StatusController : ControllerBase
{
    [HttpGet]
    [AllowAnonymous]
    public ActionResult<ServiceStatusResponse> Get()
        => Ok(new ServiceStatusResponse("app-service", "ready"));
}
