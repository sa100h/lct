using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using AppService.Services.Domain;
using Microsoft.IdentityModel.Tokens;
using Shared.Authentication;

namespace AppService.Services;

public sealed class JwtTokenIssuer : ITokenIssuer, IDisposable
{
    private readonly RSA privateKey;
    private readonly SigningCredentials credentials;
    private readonly JwtOptions options;
    private readonly RoleAccessCatalog roleAccess;

    public JwtTokenIssuer(JwtOptions options, RoleAccessCatalog roleAccess)
    {
        this.options = options;
        this.roleAccess = roleAccess;
        privateKey = RSA.Create();
        privateKey.ImportFromPem(File.ReadAllText(options.PrivateKeyPath
            ?? throw new InvalidOperationException("JWT private key path is required.")));
        credentials = new SigningCredentials(new RsaSecurityKey(privateKey), SecurityAlgorithms.RsaSha256);
    }

    public string IssueAccess(Guid userId, Guid familyId, string role, string login, DateTimeOffset now)
    {
        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, userId.ToString()),
            new(JwtClaimNames.SessionId, familyId.ToString()),
            new(JwtClaimNames.Role, role),
            new(JwtClaimNames.Login, login),
            new(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
            new(JwtRegisteredClaimNames.Iat, now.ToUnixTimeSeconds().ToString(), ClaimValueTypes.Integer64)
        };
        var jwt = new JwtSecurityToken(
            issuer: options.Issuer,
            audience: options.Audience,
            claims: claims,
            notBefore: now.UtcDateTime,
            expires: now.AddMinutes(options.AccessLifetimeMinutes).UtcDateTime,
            signingCredentials: credentials);
        jwt.Payload[JwtClaimNames.Permission] = roleAccess.GetPermissions(role).ToArray();
        return new JwtSecurityTokenHandler().WriteToken(jwt);
    }

    public string CreateRefresh()
    {
        var bytes = RandomNumberGenerator.GetBytes(32);
        return Base64UrlEncoder.Encode(bytes);
    }

    public byte[] HashRefresh(string refreshToken)
        => SHA256.HashData(Encoding.UTF8.GetBytes(refreshToken));

    public void Dispose() => privateKey.Dispose();
}
