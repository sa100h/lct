using AppService.Contracts;
using AppService.Models;
using AppService.Services.Domain;
using AppService.Services.Infrastructure;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace AppService.Tests;

public sealed class PersistingEventBatchHandlerTests
{
    [Fact]
    public async Task HandleAsync_MapsFeedEventsAndPersistsOccurredAt()
    {
        var repository = new RecordingEventLogRepository(
            new EventLogWriteResult(1, 0, 0, []));
        var handler = new PersistingEventBatchHandler(
            repository,
            NullLogger<PersistingEventBatchHandler>.Instance);
        var occurredAt = DateTimeOffset.Parse("2026-09-23T12:34:56+03:00");
        var sourceOccurredAt = DateTimeOffset.Parse("2026-01-01T12:34:56+03:00");

        await handler.HandleAsync(
            [new EventFeedEventDto(4_524_058_421, 196_727, occurredAt, sourceOccurredAt, true, "0.42")],
            TestContext.Current.CancellationToken);

        var saved = Assert.Single(repository.Events!);
        Assert.Equal(4_524_058_421, saved.Id);
        Assert.Equal(196_727, saved.SensorChannelId);
        Assert.Equal(occurredAt, saved.OccurredAt);
        Assert.NotEqual(sourceOccurredAt, saved.OccurredAt);
        Assert.True(saved.IsAlarm);
        Assert.Equal("0.42", saved.SensorValue);
    }

    [Fact]
    public async Task HandleAsync_DoesNotCallRepositoryForEmptyBatch()
    {
        var repository = new RecordingEventLogRepository(
            new EventLogWriteResult(0, 0, 0, []));
        var handler = new PersistingEventBatchHandler(
            repository,
            NullLogger<PersistingEventBatchHandler>.Instance);

        await handler.HandleAsync([], TestContext.Current.CancellationToken);

        Assert.Null(repository.Events);
    }

    [Fact]
    public async Task HandleAsync_LogsOneWarningForUnknownChannels()
    {
        var repository = new RecordingEventLogRepository(
            new EventLogWriteResult(0, 0, 2, [100, 200]));
        var logger = new RecordingLogger<PersistingEventBatchHandler>();
        var handler = new PersistingEventBatchHandler(repository, logger);
        var occurredAt = DateTimeOffset.Parse("2026-09-23T12:34:56Z");

        await handler.HandleAsync(
            [
                new EventFeedEventDto(1, 100, occurredAt, occurredAt, false, "normal"),
                new EventFeedEventDto(2, 200, occurredAt, occurredAt, true, "alarm"),
            ],
            TestContext.Current.CancellationToken);

        Assert.Equal(1, logger.Levels.Count(level => level == LogLevel.Warning));
        Assert.Equal(1, logger.Levels.Count(level => level == LogLevel.Information));
    }

    private sealed class RecordingEventLogRepository(EventLogWriteResult result) : IEventLogRepository
    {
        public IReadOnlyCollection<EventLogEntry>? Events { get; private set; }

        public Task<EventLogWriteResult> InsertAsync(
            IReadOnlyCollection<EventLogEntry> events,
            CancellationToken cancellationToken = default)
        {
            Events = events;
            return Task.FromResult(result);
        }
    }

    private sealed class RecordingLogger<T> : ILogger<T>
    {
        public List<LogLevel> Levels { get; } = [];

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter) => Levels.Add(logLevel);
    }
}
