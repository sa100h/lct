using AppService.Contracts;
using AppService.Services;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("predict")]
public sealed class PredictionController(IMlServiceClient ml) : ControllerBase
{
    [HttpPost]
    public async Task<IActionResult> Create([FromBody] PredictRequest request, CancellationToken cancellationToken)
    {
        try
        {
            return Ok(await ml.PredictAsync(request, cancellationToken));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(new { error = ex.Message });
        }
        catch (HttpRequestException ex)
        {
            return StatusCode(StatusCodes.Status502BadGateway, new { error = ex.Message });
        }
    }
}
