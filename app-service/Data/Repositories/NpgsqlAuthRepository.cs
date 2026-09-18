using AppService.Services.Domain;
using AppService.Models;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlAuthRepository(string connectionString) : IAuthRepository
{
    public async Task CreateLoginAsync(DirectoryIdentity identity, string role, Guid familyId, Guid tokenId,
        byte[] tokenHash, DateTimeOffset now, DateTimeOffset expiresAt, CancellationToken cancellationToken)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        await using (var user = new NpgsqlCommand("""
            INSERT INTO users (id, login, role, is_active) VALUES (@id, @login, @role, TRUE)
            ON CONFLICT (id) DO UPDATE SET login = EXCLUDED.login, role = EXCLUDED.role, is_active = TRUE
            """, connection, transaction))
        {
            user.Parameters.AddWithValue("id", identity.Id);
            user.Parameters.AddWithValue("login", identity.Login);
            user.Parameters.AddWithValue("role", role);
            await user.ExecuteNonQueryAsync(cancellationToken);
        }

        await using (var token = new NpgsqlCommand("""
            INSERT INTO refresh_tokens (id, family_id, user_id, token_hash, created_at, expires_at)
            VALUES (@id, @family, @user, @hash, @created, @expires)
            """, connection, transaction))
        {
            token.Parameters.AddWithValue("id", tokenId);
            token.Parameters.AddWithValue("family", familyId);
            token.Parameters.AddWithValue("user", identity.Id);
            token.Parameters.AddWithValue("hash", tokenHash);
            token.Parameters.AddWithValue("created", now);
            token.Parameters.AddWithValue("expires", expiresAt);
            await token.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<RefreshTokenRecord?> FindRefreshAsync(byte[] tokenHash, CancellationToken cancellationToken)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT id, family_id, user_id, expires_at, consumed_at, revoked_at
            FROM refresh_tokens WHERE token_hash = @hash
            """, connection);
        command.Parameters.AddWithValue("hash", tokenHash);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            return null;

        return new RefreshTokenRecord(
            reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetFieldValue<DateTimeOffset>(3),
            reader.IsDBNull(4) ? null : reader.GetFieldValue<DateTimeOffset>(4),
            reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5));
    }

    public async Task<RefreshRotationResult> RotateAsync(DirectoryIdentity identity, string role,
        RefreshTokenRecord presented, byte[] tokenHash, byte[] nextHash, Guid nextTokenId,
        DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        await using (var lockUser = new NpgsqlCommand("SELECT id FROM users WHERE id = @id FOR UPDATE", connection, transaction))
        {
            lockUser.Parameters.AddWithValue("id", identity.Id);
            if (await lockUser.ExecuteScalarAsync(cancellationToken) is null)
                return RefreshRotationResult.Invalid;
        }

        RefreshTokenRecord? current;
        await using (var lockToken = new NpgsqlCommand("""
            SELECT id, family_id, user_id, expires_at, consumed_at, revoked_at
            FROM refresh_tokens WHERE id = @id AND token_hash = @hash FOR UPDATE
            """, connection, transaction))
        {
            lockToken.Parameters.AddWithValue("id", presented.Id);
            lockToken.Parameters.AddWithValue("hash", tokenHash);
            await using var reader = await lockToken.ExecuteReaderAsync(cancellationToken);
            current = await reader.ReadAsync(cancellationToken)
                ? new RefreshTokenRecord(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2),
                    reader.GetFieldValue<DateTimeOffset>(3),
                    reader.IsDBNull(4) ? null : reader.GetFieldValue<DateTimeOffset>(4),
                    reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5))
                : null;
        }

        if (current is null || current.UserId != identity.Id || current.FamilyId != presented.FamilyId)
            return RefreshRotationResult.Invalid;

        if (current.ConsumedAt is not null && current.ExpiresAt > now)
        {
            await RevokeFamilyAsync(connection, transaction, current.FamilyId, now, cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            return RefreshRotationResult.Reused;
        }

        if (current.RevokedAt is not null || current.ExpiresAt <= now)
            return RefreshRotationResult.Invalid;

        await using (var user = new NpgsqlCommand(
            "UPDATE users SET login = @login, role = @role, is_active = TRUE WHERE id = @id", connection, transaction))
        {
            user.Parameters.AddWithValue("login", identity.Login);
            user.Parameters.AddWithValue("role", role);
            user.Parameters.AddWithValue("id", identity.Id);
            await user.ExecuteNonQueryAsync(cancellationToken);
        }

        await using (var consume = new NpgsqlCommand(
            "UPDATE refresh_tokens SET consumed_at = @now WHERE id = @id", connection, transaction))
        {
            consume.Parameters.AddWithValue("now", now);
            consume.Parameters.AddWithValue("id", current.Id);
            await consume.ExecuteNonQueryAsync(cancellationToken);
        }

        await using (var next = new NpgsqlCommand("""
            INSERT INTO refresh_tokens (id, family_id, user_id, token_hash, created_at, expires_at)
            VALUES (@id, @family, @user, @hash, @created, @expires)
            """, connection, transaction))
        {
            next.Parameters.AddWithValue("id", nextTokenId);
            next.Parameters.AddWithValue("family", current.FamilyId);
            next.Parameters.AddWithValue("user", identity.Id);
            next.Parameters.AddWithValue("hash", nextHash);
            next.Parameters.AddWithValue("created", now);
            next.Parameters.AddWithValue("expires", current.ExpiresAt);
            await next.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
        return RefreshRotationResult.Success;
    }

    public async Task DeactivateAndRevokeAllAsync(Guid userId, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var lockUser = new NpgsqlCommand(
            "SELECT id FROM users WHERE id = @user FOR UPDATE", connection, transaction))
        {
            lockUser.Parameters.AddWithValue("user", userId);
            await lockUser.ExecuteScalarAsync(cancellationToken);
        }

        await using (var user = new NpgsqlCommand(
            "UPDATE users SET is_active = FALSE WHERE id = @user", connection, transaction))
        {
            user.Parameters.AddWithValue("user", userId);
            await user.ExecuteNonQueryAsync(cancellationToken);
        }

        await using (var tokens = new NpgsqlCommand("""
            UPDATE refresh_tokens SET revoked_at = @now
            WHERE user_id = @user AND consumed_at IS NULL AND revoked_at IS NULL
            """, connection, transaction))
        {
            tokens.Parameters.AddWithValue("now", now);
            tokens.Parameters.AddWithValue("user", userId);
            await tokens.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    public async Task RevokeFamilyAsync(byte[] tokenHash, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        Guid? userId;
        await using (var find = new NpgsqlCommand(
            "SELECT user_id FROM refresh_tokens WHERE token_hash = @hash", connection, transaction))
        {
            find.Parameters.AddWithValue("hash", tokenHash);
            userId = await find.ExecuteScalarAsync(cancellationToken) as Guid?;
        }
        if (userId is null)
            return;

        // Use the same lock order as refresh/revoke-all. A concurrent rotation
        // cannot insert a live token after this family has been logged out.
        await using (var lockUser = new NpgsqlCommand(
            "SELECT id FROM users WHERE id = @id FOR UPDATE", connection, transaction))
        {
            lockUser.Parameters.AddWithValue("id", userId.Value);
            await lockUser.ExecuteScalarAsync(cancellationToken);
        }

        await using (var command = new NpgsqlCommand("""
            UPDATE refresh_tokens SET revoked_at = @now
            WHERE family_id = (SELECT family_id FROM refresh_tokens WHERE token_hash = @hash)
              AND consumed_at IS NULL AND revoked_at IS NULL
            """, connection, transaction))
        {
            command.Parameters.AddWithValue("now", now);
            command.Parameters.AddWithValue("hash", tokenHash);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<bool> IsAccessActiveAsync(Guid userId, Guid familyId, DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var connection = await OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT EXISTS (
                SELECT 1 FROM refresh_tokens r
                JOIN users u ON u.id = r.user_id
                WHERE r.family_id = @family AND r.user_id = @user
                  AND r.consumed_at IS NULL AND r.revoked_at IS NULL
                  AND r.expires_at > @now AND u.is_active
            )
            """, connection);
        command.Parameters.AddWithValue("family", familyId);
        command.Parameters.AddWithValue("user", userId);
        command.Parameters.AddWithValue("now", now);
        return await command.ExecuteScalarAsync(cancellationToken) is true;
    }

    private async Task<NpgsqlConnection> OpenAsync(CancellationToken cancellationToken)
    {
        var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        return connection;
    }

    private static async Task RevokeFamilyAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        Guid familyId, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("""
            UPDATE refresh_tokens SET revoked_at = @now
            WHERE family_id = @family AND consumed_at IS NULL AND revoked_at IS NULL
            """, connection, transaction);
        command.Parameters.AddWithValue("now", now);
        command.Parameters.AddWithValue("family", familyId);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}
