using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;

namespace Shared.Authentication;

public static class JwtAuthenticationExtensions
{
    public static IServiceCollection AddSharedJwtAuthentication(
        this IServiceCollection services,
        IConfiguration configuration,
        bool requirePrivateKey = false)
    {
        var options = configuration.GetSection(JwtOptions.SectionName).Get<JwtOptions>() ?? new JwtOptions();
        if (string.IsNullOrWhiteSpace(options.Issuer) || string.IsNullOrWhiteSpace(options.Audience)
            || string.IsNullOrWhiteSpace(options.PublicKeyPath) || options.AccessLifetimeMinutes != 5
            || options.RefreshLifetimeDays <= 0 || (requirePrivateKey && string.IsNullOrWhiteSpace(options.PrivateKeyPath)))
        {
            throw new InvalidOperationException("JWT issuer, audience, key paths and lifetimes must be configured.");
        }

        using var rsa = RSA.Create();
        rsa.ImportFromPem(File.ReadAllText(options.PublicKeyPath));
        var publicKey = new RsaSecurityKey(rsa.ExportParameters(false));
        if (requirePrivateKey)
        {
            using var signer = RSA.Create();
            signer.ImportFromPem(File.ReadAllText(options.PrivateKeyPath!));
            var probe = RandomNumberGenerator.GetBytes(32);
            var signature = signer.SignData(probe, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            if (!rsa.VerifyData(probe, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))
                throw new InvalidOperationException("JWT private and public keys do not match.");
        }

        services.AddSingleton(options);
        services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
            .AddJwtBearer(jwt =>
            {
                jwt.MapInboundClaims = false;
                jwt.TokenValidationParameters = new TokenValidationParameters
                {
                    RequireSignedTokens = true,
                    ValidateIssuerSigningKey = true,
                    IssuerSigningKey = publicKey,
                    ValidAlgorithms = [SecurityAlgorithms.RsaSha256],
                    ValidateIssuer = true,
                    ValidIssuer = options.Issuer,
                    ValidateAudience = true,
                    ValidAudience = options.Audience,
                    ValidateLifetime = true,
                    RequireExpirationTime = true,
                    ClockSkew = TimeSpan.Zero
                };
            });

        return services;
    }
}
