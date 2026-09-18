using System.Globalization;
using System.Net.Sockets;
using System.Security.Authentication;
using AppService.Models;
using AppService.Services.Domain;
using Novell.Directory.Ldap;

namespace AppService.Services.Infrastructure;

public sealed class LdapAdIdentityProvider(
    AdOptions options,
    AdCertificateValidator certificateValidator,
    ILogger<LdapAdIdentityProvider> logger)
    : IAdIdentityProvider
{
    private static readonly string[] UserAttributes =
        ["objectGUID", "sAMAccountName", "userAccountControl", "memberOf"];

    public async Task<DirectoryIdentity?> AuthenticateAsync(
        string login, string password, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(login) || login.Length > 256
            || login.Contains('@') || login.Contains('\\') || string.IsNullOrEmpty(password))
            return null;

        using var timeout = CreateTimeout(cancellationToken);
        try
        {
            using var serviceConnection = await ConnectAndBindAsync(
                options.BindName, options.BindPassword, timeout.Token);
            var entry = await FindUserAsync(serviceConnection,
                $"(&(objectClass=user)(sAMAccountName={EscapeFilter(login)}))", timeout.Token);
            if (entry is null)
                return null;

            var identity = ReadIdentity(entry);
            if (!identity.IsActive)
                return identity;

            try
            {
                using var userConnection = await ConnectAndBindAsync(entry.Dn, password, timeout.Token);
                return identity;
            }
            catch (LdapException exception) when (exception.ResultCode == LdapException.InvalidCredentials)
            {
                return null;
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (IsDirectoryFailure(exception))
        {
            logger.LogWarning(exception, "AD login lookup or bind failed.");
            throw new AdUnavailableException(exception);
        }
    }

    public async Task<DirectoryIdentity?> GetCurrentAsync(Guid objectGuid, CancellationToken cancellationToken)
    {
        using var timeout = CreateTimeout(cancellationToken);
        try
        {
            using var serviceConnection = await ConnectAndBindAsync(
                options.BindName, options.BindPassword, timeout.Token);
            var binaryGuid = string.Concat(objectGuid.ToByteArray().Select(value => $"\\{value:X2}"));
            var entry = await FindUserAsync(serviceConnection,
                $"(&(objectClass=user)(objectGUID={binaryGuid}))", timeout.Token);
            return entry is null ? null : ReadIdentity(entry);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (IsDirectoryFailure(exception))
        {
            logger.LogWarning(exception, "AD refresh lookup failed.");
            throw new AdUnavailableException(exception);
        }
    }

    private async Task<LdapConnection> ConnectAndBindAsync(
        string bindName, string password, CancellationToken cancellationToken)
    {
        var connectionOptions = new LdapConnectionOptions()
            .ConfigureRemoteCertificateValidationCallback(
                (_, certificate, _, errors) => certificateValidator.IsValid(certificate, errors));
        var connection = new LdapConnection(connectionOptions)
        {
            SecureSocketLayer = true,
            ConnectionTimeout = checked(options.TimeoutSeconds * 1000)
        };
        try
        {
            await connection.ConnectAsync(options.Host, options.Port, cancellationToken);
            await connection.BindAsync(bindName, password, cancellationToken);
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    private async Task<LdapEntry?> FindUserAsync(
        LdapConnection connection, string filter, CancellationToken cancellationToken)
    {
        var results = await connection.SearchAsync(options.BaseDn, LdapConnection.ScopeSub,
            filter, UserAttributes, false, cancellationToken);
        LdapEntry? found = null;
        while (await results.HasMoreAsync(cancellationToken))
        {
            LdapEntry entry;
            try
            {
                entry = await results.NextAsync(cancellationToken);
            }
            catch (LdapReferralException)
            {
                // Samba returns search continuations for other naming contexts.
                continue;
            }

            if (found is not null)
                throw new InvalidDataException("AD returned more than one user for a unique identifier.");
            found = entry;
        }
        return found;
    }

    private static DirectoryIdentity ReadIdentity(LdapEntry entry)
    {
        var attributes = entry.GetAttributeSet();
        var guidBytes = attributes.GetAttribute("objectGUID")?.ByteValue;
        var login = attributes.GetAttribute("sAMAccountName")?.StringValue;
        var control = attributes.GetAttribute("userAccountControl")?.StringValue;
        if (guidBytes is null || guidBytes.Length != 16 || string.IsNullOrWhiteSpace(login)
            || !int.TryParse(control, NumberStyles.None, CultureInfo.InvariantCulture, out var flags))
            throw new InvalidDataException("AD user lacks required identity attributes.");

        var groups = attributes.GetAttribute("memberOf")?.StringValueArray ?? [];
        return new DirectoryIdentity(new Guid(guidBytes), login, (flags & 0x2) == 0, groups);
    }

    private static string EscapeFilter(string value)
    {
        var result = new System.Text.StringBuilder(value.Length);
        foreach (var character in value)
        {
            result.Append(character switch
            {
                '*' => @"\2a",
                '(' => @"\28",
                ')' => @"\29",
                '\\' => @"\5c",
                '\0' => @"\00",
                _ => character.ToString()
            });
        }
        return result.ToString();
    }

    private CancellationTokenSource CreateTimeout(CancellationToken cancellationToken)
    {
        var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(options.TimeoutSeconds));
        return timeout;
    }

    private static bool IsDirectoryFailure(Exception exception)
        => exception is LdapException or AuthenticationException or IOException or InvalidDataException
            or SocketException or TimeoutException or OperationCanceledException or ArgumentException;
}
