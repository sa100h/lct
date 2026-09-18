using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace AppService.Services.Infrastructure;

public sealed class AdCertificateValidator
{
    private readonly byte[] trustedCertificate;
    private readonly DateTime notBeforeUtc;
    private readonly DateTime notAfterUtc;

    public AdCertificateValidator(string certificatePath)
    {
        using var certificate = X509Certificate2.CreateFromPem(File.ReadAllText(certificatePath));
        trustedCertificate = certificate.RawData;
        notBeforeUtc = certificate.NotBefore.ToUniversalTime();
        notAfterUtc = certificate.NotAfter.ToUniversalTime();
        if (DateTime.UtcNow < notBeforeUtc || DateTime.UtcNow > notAfterUtc)
            throw new InvalidOperationException("The configured AD certificate is not valid at the current time.");
    }

    public bool IsValid(X509Certificate? certificate, SslPolicyErrors errors)
    {
        if (certificate is null
            || (errors & ~SslPolicyErrors.RemoteCertificateChainErrors) != SslPolicyErrors.None)
            return false;

        var now = DateTime.UtcNow;
        return now >= notBeforeUtc && now <= notAfterUtc
            && CryptographicOperations.FixedTimeEquals(certificate.GetRawCertData(), trustedCertificate);
    }
}
