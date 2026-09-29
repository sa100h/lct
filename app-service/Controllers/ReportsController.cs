using System.Globalization;
using AppService.Services.Domain;
using AppService.Services.Infrastructure;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("reports")]
public sealed class ReportsController(
    IReportQueryService reports,
    IReportPdfRenderer renderer) : ControllerBase
{
    [HttpGet("{code}")]
    [Authorize(Policy = PermissionCodes.ModuleReports)]
    public async Task<IActionResult> Get(
        string code,
        [FromQuery] string? from,
        [FromQuery] string? to,
        CancellationToken cancellationToken)
    {
        if (!DateOnly.TryParse(from, CultureInfo.InvariantCulture, out var fromDate)
            || !DateOnly.TryParse(to, CultureInfo.InvariantCulture, out var toDate))
        {
            return BadRequest();
        }

        try
        {
            var document = await reports.BuildAsync(code, fromDate, toDate, cancellationToken);
            var pdf = renderer.Render(document);
            return File(pdf, "application/pdf", document.Header.FileName);
        }
        catch (ArgumentException)
        {
            return BadRequest();
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
    }
}
