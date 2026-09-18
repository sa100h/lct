using Shared.DatabaseMigration;

namespace AppService.Extensions;

public sealed class AppMigrationHostedService(PostgresMigrator migrator, IConfiguration configuration) : IHostedService
{
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var migrationsPath = configuration["Migrations:Path"];
        if (string.IsNullOrWhiteSpace(migrationsPath))
            return;

        var connectionString = configuration.GetConnectionString("AppDb")
            ?? throw new InvalidOperationException("Connection string 'AppDb' is required.");
        await migrator.MigrateAsync(connectionString, migrationsPath, cancellationToken);
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
