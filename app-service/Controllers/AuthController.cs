using AppService.Contracts;
using AppService.Models;
using AppService.Services;
using AppService.Services.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppService.Controllers;

[ApiController]
[Route("auth")]
public sealed class AuthController(IAuthSessionService sessions, AuthCookieOptions cookies) : ControllerBase
{
    [HttpPost("login")]
    [AllowAnonymous]
    [ProducesResponseType(typeof(LoginResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<LoginResponse>> Login([FromBody] LoginRequest request, CancellationToken cancellationToken)
    {
        var result = await sessions.LoginAsync(request.Login, request.Password, cancellationToken);
        return ToLoginResult(result);
    }

    [HttpPost("refresh")]
    [AllowAnonymous]
    [ProducesResponseType(typeof(LoginResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<LoginResponse>> Refresh(CancellationToken cancellationToken)
    {
        var result = await sessions.RefreshAsync(Request.Cookies[cookies.Name], cancellationToken);
        return ToLoginResult(result);
    }

    [HttpPost("logout")]
    [AllowAnonymous]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    public async Task<IActionResult> Logout(CancellationToken cancellationToken)
    {
        await sessions.LogoutAsync(Request.Cookies[cookies.Name], cancellationToken);
        Response.Cookies.Delete(cookies.Name, new CookieOptions { Path = cookies.Path });
        return NoContent();
    }

    private ActionResult<LoginResponse> ToLoginResult(AuthResult result)
    {
        if (result.Error != AuthError.None)
        {
            var status = result.Error switch
            {
                AuthError.InvalidCredentials or AuthError.InvalidRefreshToken => StatusCodes.Status401Unauthorized,
                AuthError.Forbidden => StatusCodes.Status403Forbidden,
                AuthError.DirectoryUnavailable => StatusCodes.Status503ServiceUnavailable,
                _ => StatusCodes.Status500InternalServerError
            };
            return Problem(statusCode: status);
        }

        Response.Cookies.Append(cookies.Name, result.RefreshToken!, new CookieOptions
        {
            HttpOnly = true,
            Secure = true,
            SameSite = SameSiteMode.Strict,
            Path = cookies.Path,
            Expires = result.RefreshExpiresAt
        });
        return Ok(new LoginResponse(result.AccessToken!));
    }
}
