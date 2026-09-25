using System.Text.Json;
using AppService.Models;
using AppService.Services.Domain;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

public sealed class NpgsqlForecastJournalRepository(string connectionString) : IForecastJournalRepository
{
    public async Task<IReadOnlyList<int>> FindMissingDispatcherObjectIdsAsync(
        IReadOnlyCollection<int> dispatcherObjectIds,
        CancellationToken cancellationToken = default)
    {
        if (dispatcherObjectIds.Count == 0)
        {
            return [];
        }

        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT id FROM dispatcher_objects WHERE id = ANY(@objectIds)",
            connection);
        command.Parameters
            .Add("objectIds", NpgsqlDbType.Array | NpgsqlDbType.Integer)
            .Value = dispatcherObjectIds.ToArray();

        var existingIds = new HashSet<int>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            existingIds.Add(reader.GetInt32(0));
        }

        return dispatcherObjectIds
            .Where(id => !existingIds.Contains(id))
            .OrderBy(id => id)
            .ToArray();
    }

    public async Task<ForecastJournalEntry> CreateAsync(
        Guid userId,
        string description,
        IReadOnlyList<int>? dispatcherObjectIds,
        DateTimeOffset createdAt,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            INSERT INTO forecast_journal
                (description, user_created_id, forecast_objects, creation_time)
            VALUES
                (@description, @userId, @forecastObjects, @creationTime)
            RETURNING id
            """, connection);
        command.Parameters.AddWithValue("description", NpgsqlDbType.Text, description);
        command.Parameters.AddWithValue("userId", NpgsqlDbType.Uuid, userId);
        var forecastObjectsParameter = command.Parameters.Add("forecastObjects", NpgsqlDbType.Json);
        forecastObjectsParameter.Value = dispatcherObjectIds is null
            ? DBNull.Value
            : JsonSerializer.Serialize(dispatcherObjectIds);
        command.Parameters.AddWithValue(
            "creationTime",
            NpgsqlDbType.Timestamp,
            DateTime.SpecifyKind(createdAt.UtcDateTime, DateTimeKind.Unspecified));

        var id = (Guid)(await command.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Forecast journal insert did not return an id."));

        return new ForecastJournalEntry(id, createdAt, dispatcherObjectIds);
    }
}
