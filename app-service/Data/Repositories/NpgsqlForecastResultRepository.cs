using AppService.Models;
using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlForecastResultRepository(string connectionString) : IForecastResultRepository
{
    public async Task<bool> JournalExistsAsync(
        Guid journalId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT EXISTS (SELECT 1 FROM forecast_journal WHERE id = @id)",
            connection);
        command.Parameters.AddWithValue("id", journalId);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is true;
    }

    public async Task MarkErroneousAsync(
        Guid journalId,
        Guid dispatcherUserId,
        IReadOnlyList<int> objectIds,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        foreach (var objectId in objectIds)
        {
            await using var command = new NpgsqlCommand("""
                INSERT INTO forecast_results (
                    forecast_journal_id, forecast_name, forecast_description,
                    dispatcher_object_id, user_dispatcher_id, is_erroneous, is_cancelled)
                VALUES (
                    @journal, 'Ошибочный', '{}'::jsonb,
                    @objectId, @user, TRUE, FALSE)
                ON CONFLICT (forecast_journal_id, dispatcher_object_id)
                DO UPDATE SET is_erroneous = TRUE
                """, connection, transaction);
            command.Parameters.AddWithValue("journal", journalId);
            command.Parameters.AddWithValue("objectId", objectId);
            command.Parameters.AddWithValue("user", dispatcherUserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<IReadOnlyDictionary<int, ForecastJournalResult>> ListByJournalAsync(
        Guid journalId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT dispatcher_object_id, forecast_description::text, is_erroneous
            FROM forecast_results
            WHERE forecast_journal_id = @id
            """, connection);
        command.Parameters.AddWithValue("id", journalId);

        var result = new Dictionary<int, ForecastJournalResult>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result[reader.GetInt32(0)] = new ForecastJournalResult(
                reader.IsDBNull(1) ? "{}" : reader.GetString(1),
                reader.GetBoolean(2));
        }

        return result;
    }
}
