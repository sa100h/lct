using System.IdentityModel.Tokens.Jwt;
using System.Security.Cryptography;
using System.Text.Json;
using AppService.Services.Domain;
using AppService.Services;
using AppService.Models;
using Shared.Authentication;
using Xunit;

namespace AppService.Tests;

public sealed class AuthDesignTests
{
    [Fact]
    public void DirectoryRoleMapper_RequiresExactlyOneApplicationGroup()
    {
        var mapper = new DirectoryRoleMapper(new AdGroupOptions
        {
            Admin = "Admins",
            Technician = "Technics",
            DispatcherOds = "Dispetchers_ODS",
            DispatcherDistrict = "Dispetchers_rayon"
        });

        Assert.True(mapper.TryResolveRole(["Domain Users", "Technics"], out var role));
        Assert.Equal(RoleCatalog.Technician, role);
        Assert.False(mapper.TryResolveRole(["Admins", "Technics"], out _));
        Assert.False(mapper.TryResolveRole(["Domain Users"], out _));
    }

    [Fact]
    public void IssuedAccess_ContainsFiveMinuteRoleAndPermissionSnapshot()
    {
        var directory = Path.Combine(Path.GetTempPath(), $"lct-auth-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        try
        {
            using var rsa = RSA.Create(2048);
            var privatePath = Path.Combine(directory, "private.pem");
            File.WriteAllText(privatePath, rsa.ExportRSAPrivateKeyPem());
            using var issuer = new JwtTokenIssuer(new JwtOptions
            {
                Issuer = "lct-test",
                Audience = "lct-test-api",
                PrivateKeyPath = privatePath
            });

            var now = new DateTimeOffset(2026, 9, 18, 9, 0, 0, TimeSpan.Zero);
            var userId = Guid.NewGuid();
            var familyId = Guid.NewGuid();
            var jwt = new JwtSecurityTokenHandler().ReadJwtToken(
                issuer.IssueAccess(userId, familyId, RoleCatalog.DispatcherDistrict, now));

            Assert.Equal("RS256", jwt.Header.Alg);
            Assert.Equal("lct-test", jwt.Issuer);
            Assert.Contains("lct-test-api", jwt.Audiences);
            Assert.Equal(now.AddMinutes(5), jwt.ValidTo);
            Assert.Equal(userId.ToString(), jwt.Subject);
            Assert.Equal(familyId.ToString(), jwt.Claims.Single(c => c.Type == JwtClaimNames.SessionId).Value);
            Assert.Equal(RoleCatalog.DispatcherDistrict, jwt.Claims.Single(c => c.Type == JwtClaimNames.Role).Value);
            Assert.Contains(jwt.Claims, c => c.Type == JwtClaimNames.Permission && c.Value == PermissionCodes.DemoAccess);
            using var payload = JsonDocument.Parse(jwt.Payload.SerializeToJson());
            Assert.Equal(JsonValueKind.Array,
                payload.RootElement.GetProperty(JwtClaimNames.Permission).ValueKind);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }
}
