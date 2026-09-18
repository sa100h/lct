using System.Net;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace AppService.Tests;

public sealed class StatusEndpointTests : IClassFixture<WebApplicationFactory<Program>>, IDisposable
{
    private readonly HttpClient client;
    private readonly string keyDirectory;

    public StatusEndpointTests(WebApplicationFactory<Program> factory)
    {
        keyDirectory = Path.Combine(Path.GetTempPath(), $"lct-jwt-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(keyDirectory);
        using var rsa = RSA.Create(2048);
        var privatePath = Path.Combine(keyDirectory, "private.pem");
        var publicPath = Path.Combine(keyDirectory, "public.pem");
        File.WriteAllText(privatePath, rsa.ExportRSAPrivateKeyPem());
        File.WriteAllText(publicPath, rsa.ExportRSAPublicKeyPem());
        client = factory.WithWebHostBuilder(builder => builder
            .UseSetting("Migrations:Path", string.Empty)
            .UseSetting("Jwt:Issuer", "lct-test")
            .UseSetting("Jwt:Audience", "lct-test-api")
            .UseSetting("Jwt:PrivateKeyPath", privatePath)
            .UseSetting("Jwt:PublicKeyPath", publicPath)).CreateClient();
    }

    [Fact]
    public async Task AuthenticationBoundary_BehavesAsConfigured()
    {
        var response = await client.GetAsync("/status", TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        response = await client.GetAsync("/authz/demo", TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        using var predictBody = new StringContent("{}", Encoding.UTF8, "application/json");
        response = await client.PostAsync("/predict", predictBody, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        using var body = new StringContent("""{"login":"example","password":"example"}""", Encoding.UTF8, "application/json");
        response = await client.PostAsync("/auth/login", body, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);

        using var invalidBody = new StringContent("""{"login":"","password":""}""", Encoding.UTF8, "application/json");
        response = await client.PostAsync("/auth/login", invalidBody, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);

        response = await client.PostAsync("/auth/refresh", null, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    public void Dispose()
    {
        client.Dispose();
        Directory.Delete(keyDirectory, recursive: true);
    }
}
