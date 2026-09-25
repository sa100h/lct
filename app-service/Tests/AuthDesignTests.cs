using System.IdentityModel.Tokens.Jwt;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Net.Security;
using System.Text.Json;
using AppService.Services.Domain;
using AppService.Services;
using AppService.Models;
using AppService.Services.Infrastructure;
using AppService.Extensions;
using AppService.Controllers;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Shared.Authentication;
using Xunit;

namespace AppService.Tests;

public sealed class AuthDesignTests
{
    [Fact]
    public void DispatcherObjects_RequiresModuleMapPermission()
    {
        var method = typeof(DispatcherObjectsController).GetMethod(nameof(DispatcherObjectsController.GetAll));
        var authorize = Assert.Single(method!.GetCustomAttributes(typeof(AuthorizeAttribute), inherit: true)
            .Cast<AuthorizeAttribute>());

        Assert.Equal(PermissionCodes.ModuleMap, authorize.Policy);
    }

    [Fact]
    public void ForecastRun_RequiresModulePredictionPermission()
    {
        var method = typeof(ForecastsController).GetMethod(nameof(ForecastsController.Run));
        var authorize = Assert.Single(method!.GetCustomAttributes(typeof(AuthorizeAttribute), inherit: true)
            .Cast<AuthorizeAttribute>());

        Assert.Equal(PermissionCodes.ModulePrediction, authorize.Policy);
    }

    [Fact]
    public void RoleAccessCatalog_RequiresExactlyOneApplicationGroup()
    {
        var catalog = CreateCatalog();

        Assert.True(catalog.TryResolveRole(
            ["CN=Domain Users,CN=Users,DC=lct,DC=ru", "CN=Technics,OU=Groups,DC=lct,DC=ru"], out var role));
        Assert.Equal("technician", role);
        Assert.False(catalog.TryResolveRole(
            ["CN=Admins,OU=Groups,DC=lct,DC=ru", "CN=Technics,OU=Groups,DC=lct,DC=ru"], out _));
        Assert.False(catalog.TryResolveRole(["CN=Domain Users,CN=Users,DC=lct,DC=ru"], out _));
        Assert.Equal(
            [
                PermissionCodes.DemoAccess,
                PermissionCodes.ModuleHome,
                PermissionCodes.ModuleMap,
                PermissionCodes.ModulePrediction,
                PermissionCodes.ModuleHistory
            ],
            catalog.GetPermissions("technician"));
    }

    private static RoleAccessCatalog CreateCatalog() => new RoleAccessCatalog(
    [
        new RoleDefinition("admin", "CN=Admins,OU=Groups,DC=lct,DC=ru",
        [
            PermissionCodes.DemoAccess,
            PermissionCodes.ModuleHome,
            PermissionCodes.ModuleDashboard,
            PermissionCodes.ModuleMap,
            PermissionCodes.ModulePrediction,
            PermissionCodes.ModuleHistory,
            PermissionCodes.ModuleNotifications,
            PermissionCodes.ModuleReports,
            PermissionCodes.ModuleSettings
        ]),
        new RoleDefinition("technician", "CN=Technics,OU=Groups,DC=lct,DC=ru",
        [
            PermissionCodes.DemoAccess,
            PermissionCodes.ModuleHome,
            PermissionCodes.ModuleMap,
            PermissionCodes.ModulePrediction,
            PermissionCodes.ModuleHistory
        ]),
        new RoleDefinition("dispatcher_ods", "CN=Dispetchers_ODS,OU=Groups,DC=lct,DC=ru",
        [
            PermissionCodes.DemoAccess,
            PermissionCodes.ModuleHome,
            PermissionCodes.ModuleDashboard,
            PermissionCodes.ModuleMap,
            PermissionCodes.ModuleNotifications,
            PermissionCodes.ModuleReports
        ]),
        new RoleDefinition("dispatcher_district", "CN=Dispetchers_rayon,OU=Groups,DC=lct,DC=ru",
        [
            PermissionCodes.DemoAccess,
            PermissionCodes.ModuleHome,
            PermissionCodes.ModuleMap,
            PermissionCodes.ModuleNotifications
        ])
    ]);

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
            }, CreateCatalog());

            var now = new DateTimeOffset(2026, 9, 18, 9, 0, 0, TimeSpan.Zero);
            var userId = Guid.NewGuid();
            var familyId = Guid.NewGuid();
            var jwt = new JwtSecurityTokenHandler().ReadJwtToken(
                issuer.IssueAccess(userId, familyId, "dispatcher_district", "dispetcher_rayon", now));

            Assert.Equal("RS256", jwt.Header.Alg);
            Assert.Equal("lct-test", jwt.Issuer);
            Assert.Contains("lct-test-api", jwt.Audiences);
            Assert.Equal(now.AddMinutes(5), jwt.ValidTo);
            Assert.Equal(userId.ToString(), jwt.Subject);
            Assert.Equal(familyId.ToString(), jwt.Claims.Single(c => c.Type == JwtClaimNames.SessionId).Value);
            Assert.Equal("dispatcher_district", jwt.Claims.Single(c => c.Type == JwtClaimNames.Role).Value);
            Assert.Equal("dispetcher_rayon", jwt.Claims.Single(c => c.Type == JwtClaimNames.Login).Value);
            Assert.Contains(jwt.Claims, c => c.Type == JwtClaimNames.Permission && c.Value == PermissionCodes.DemoAccess);
            Assert.Contains(jwt.Claims, c => c.Type == JwtClaimNames.Permission && c.Value == PermissionCodes.ModuleHome);
            Assert.DoesNotContain(jwt.Claims, c => c.Type == JwtClaimNames.Permission && c.Value == PermissionCodes.ModuleSettings);
            using var payload = JsonDocument.Parse(jwt.Payload.SerializeToJson());
            Assert.Equal(JsonValueKind.Array,
                payload.RootElement.GetProperty(JwtClaimNames.Permission).ValueKind);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void AdCertificateValidator_RequiresPinnedCertificateAndMatchingHost()
    {
        var directory = Path.Combine(Path.GetTempPath(), $"lct-ad-cert-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        try
        {
            using var rsa = RSA.Create(2048);
            var request = new CertificateRequest(
                "CN=dc1.lct.ru", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            using var certificate = request.CreateSelfSigned(
                DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddDays(1));
            var path = Path.Combine(directory, "ldaps.pem");
            File.WriteAllText(path, certificate.ExportCertificatePem());
            var validator = new AdCertificateValidator(path);

            Assert.True(validator.IsValid(certificate, SslPolicyErrors.RemoteCertificateChainErrors));
            Assert.False(validator.IsValid(certificate, SslPolicyErrors.RemoteCertificateNameMismatch));
            using var otherRsa = RSA.Create(2048);
            var otherRequest = new CertificateRequest(
                "CN=dc1.lct.ru", otherRsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            using var other = otherRequest.CreateSelfSigned(
                DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddDays(1));
            Assert.False(validator.IsValid(other, SslPolicyErrors.RemoteCertificateChainErrors));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void PermissionPolicyValidation_RejectsPermissionMissingFromMatrix()
    {
        var endpoint = new Endpoint(
            _ => Task.CompletedTask,
            new EndpointMetadataCollection(new AuthorizeAttribute { Policy = PermissionCodes.DemoAccess }),
            "AuthzDemoController.Get");
        var catalog = new RoleAccessCatalog(
            [new RoleDefinition("admin", "CN=Admins,DC=lct,DC=ru", ["other.access"])]);

        var error = Assert.Throws<InvalidOperationException>(
            () => PermissionPolicyValidationExtensions.EnsureConfigured([endpoint], catalog));
        Assert.Contains(PermissionCodes.DemoAccess, error.Message);
        Assert.Contains("AuthzDemoController.Get", error.Message);
    }

    [Fact]
    public void RoleAccessCatalog_ModulePermissionsMatchMatrixA()
    {
        var catalog = CreateCatalog();
        Assert.Equal(
            [
                PermissionCodes.DemoAccess, PermissionCodes.ModuleHome, PermissionCodes.ModuleDashboard,
                PermissionCodes.ModuleMap, PermissionCodes.ModulePrediction, PermissionCodes.ModuleHistory,
                PermissionCodes.ModuleNotifications, PermissionCodes.ModuleReports, PermissionCodes.ModuleSettings
            ],
            catalog.GetPermissions("admin"));
        Assert.Equal(
            [
                PermissionCodes.DemoAccess, PermissionCodes.ModuleHome, PermissionCodes.ModuleMap,
                PermissionCodes.ModulePrediction, PermissionCodes.ModuleHistory
            ],
            catalog.GetPermissions("technician"));
        Assert.Equal(
            [
                PermissionCodes.DemoAccess, PermissionCodes.ModuleHome, PermissionCodes.ModuleDashboard,
                PermissionCodes.ModuleMap, PermissionCodes.ModuleNotifications, PermissionCodes.ModuleReports
            ],
            catalog.GetPermissions("dispatcher_ods"));
        Assert.Equal(
            [
                PermissionCodes.DemoAccess, PermissionCodes.ModuleHome, PermissionCodes.ModuleMap,
                PermissionCodes.ModuleNotifications
            ],
            catalog.GetPermissions("dispatcher_district"));
    }

    [Fact]
    public void AppSettings_RoleAccessMatchesMatrixA()
    {
        var path = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "appsettings.json"));
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        var roles = doc.RootElement.GetProperty("RoleAccess").GetProperty("Roles");
        string[] Read(string code) =>
            roles.EnumerateArray().Single(r => r.GetProperty("Code").GetString() == code)
                .GetProperty("Permissions").EnumerateArray().Select(v => v.GetString()!).ToArray();

        Assert.Equal(
            ["demo.access", "module.home", "module.dashboard", "module.map", "module.prediction",
             "module.history", "module.notifications", "module.reports", "module.settings"],
            Read("admin"));
        Assert.Equal(
            ["demo.access", "module.home", "module.map", "module.prediction", "module.history"],
            Read("technician"));
        Assert.Equal(
            ["demo.access", "module.home", "module.dashboard", "module.map", "module.notifications", "module.reports"],
            Read("dispatcher_ods"));
        Assert.Equal(
            ["demo.access", "module.home", "module.map", "module.notifications"],
            Read("dispatcher_district"));
    }
}
