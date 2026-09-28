using AppService.Models;
using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlUserRepository(string connectionString) : IUserRepository
{
    public async Task<IReadOnlyList<UserListItem>> ListActiveByRoleNameAsync(
        string roleName,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT u.id, u.login
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.is_active AND r.name = @roleName
            ORDER BY u.login
            """, connection);
        command.Parameters.AddWithValue("roleName", roleName);

        var result = new List<UserListItem>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new UserListItem(reader.GetGuid(0), reader.GetString(1)));
        }

        return result;
    }
}
