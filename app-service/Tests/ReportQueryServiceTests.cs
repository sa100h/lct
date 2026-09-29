using AppService.Models;
using AppService.Services.Domain;
using AppService.Services.Infrastructure;
using Xunit;

namespace AppService.Tests;

public sealed class ReportQueryServiceTests
{
    [Fact]
    public async Task BuildAsync_RejectsBadPeriodAndUnknownCode()
    {
        var service = Create();
        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.BuildAsync("summary", new DateOnly(2026, 9, 2), new DateOnly(2026, 9, 1), CancellationToken.None));
        await Assert.ThrowsAsync<KeyNotFoundException>(() =>
            service.BuildAsync("nope", new DateOnly(2026, 9, 1), new DateOnly(2026, 9, 1), CancellationToken.None));
    }

    [Fact]
    public async Task BuildAsync_Summary_PadsZeroDaysAndSumsRequests()
    {
        var from = new DateOnly(2026, 9, 1);
        var to = new DateOnly(2026, 9, 3);
        var feeds = new StubFeeds
        {
            AlarmTotal = 2,
            AlarmsByDay = new Dictionary<DateOnly, int> { [from] = 2 },
            RequestsByStatus = [new("Новая", 1), new("Закрыта", 3)],
            RequestsByDay = new Dictionary<DateOnly, int> { [to] = 4 },
            ForecastsByStatus = [new("done", 1)],
        };
        var service = Create(feeds, new DateTimeOffset(2026, 9, 28, 12, 0, 0, TimeSpan.Zero));
        var doc = await service.BuildAsync("summary", from, to, CancellationToken.None);
        var body = Assert.IsType<SummaryReportBody>(doc.Body);
        Assert.Equal("Оперативная сводка", doc.Header.Title);
        Assert.Equal("svodka_2026-09-01_2026-09-03.pdf", doc.Header.FileName);
        Assert.Equal(2, body.Data.AlarmTotal);
        Assert.Equal(4, body.Data.RequestsTotal);
        Assert.Equal([1, 0, 3], body.Data.RequestsByStatus.Select(item => item.Count));
        Assert.Equal([2, 0, 0], body.Data.AlarmsByDay.Select(item => item.Count));
        Assert.Equal([0, 0, 4], body.Data.RequestsByDay.Select(item => item.Count));
        Assert.Equal(["pending", "running", "done"], body.Data.ForecastsByStatus.Select(item => item.Status));
        Assert.Equal([0, 0, 1], body.Data.ForecastsByStatus.Select(item => item.Count));
        Assert.Equal(new DateTimeOffset(2026, 9, 28, 12, 0, 0, TimeSpan.Zero), doc.Header.GeneratedAt);
    }

    [Fact]
    public async Task BuildAsync_Alarms_KeepsTotalWhenRowsCapped()
    {
        var rows = new AlarmReportRow[]
        {
            new(DateTimeOffset.UtcNow, "a", 1, "x"),
            new(DateTimeOffset.UtcNow, "b", 2, "y"),
        };
        var feeds = new StubFeeds { AlarmList = (3, rows) };
        var service = Create(feeds);
        var body = Assert.IsType<AlarmReportBody>(
            (await service.BuildAsync("alarms", new DateOnly(2026, 9, 1), new DateOnly(2026, 9, 1), CancellationToken.None)).Body);
        Assert.Equal(3, body.Total);
        Assert.Equal(2, body.Rows.Count);
    }

    [Fact]
    public async Task BuildAsync_Technicians_PassesThroughLoads()
    {
        var feeds = new StubFeeds { Technicians = [new("t1", 2, 1)] };
        var service = Create(feeds);
        var body = Assert.IsType<TechnicianReportBody>(
            (await service.BuildAsync("technicians", new DateOnly(2026, 9, 1), new DateOnly(2026, 9, 1), CancellationToken.None)).Body);
        var row = Assert.Single(body.Rows);
        Assert.Equal("t1", row.Login);
        Assert.Equal(2, row.Created);
        Assert.Equal(1, row.Closed);
    }

    [Fact]
    public async Task BuildAsync_Forecasts_CountsHighRiskAndIgnoresErroneous()
    {
        var highId = Guid.NewGuid();
        var errId = Guid.NewGuid();
        var noneId = Guid.NewGuid();
        var created = new DateTimeOffset(2026, 9, 1, 10, 0, 0, TimeSpan.Zero);
        var feeds = new StubFeeds
        {
            Journals =
            [
                new(highId, created, "admin.test", created, created, 1),
                new(errId, created, "admin.test", created, created, 1),
                new(noneId, created, "admin.test", created, created, 1),
            ],
            Results = new Dictionary<Guid, IReadOnlyList<ForecastJournalResult>>
            {
                [highId] = [new("""{"channels":{"1":{"fire-risk":{"value":0.9}}}}""", false, false)],
                [errId] = [new("""{"channels":{"1":{"fire-risk":{"value":0.9}}}}""", true, false)],
                [noneId] = [new("""{"channels":{"1":{"fire-risk":{"status_code":"unpredictable"}}}}""", false, false)],
            },
        };
        var service = Create(feeds);
        var body = Assert.IsType<ForecastReportBody>(
            (await service.BuildAsync("forecasts", new DateOnly(2026, 9, 1), new DateOnly(2026, 9, 1), CancellationToken.None)).Body);
        Assert.Equal(3, body.DoneCount);
        Assert.Equal(1, body.HighRiskObjects);
        Assert.Equal(3, body.Rows.Count);
        Assert.All(body.Rows, row => Assert.Equal("done", row.Status));
    }

    private static ReportQueryService Create(
        StubFeeds? feeds = null,
        DateTimeOffset? utcNow = null)
        => new(
            feeds ?? new StubFeeds(),
            new ForecastOptions { RiskThreshold = 0.5 },
            new FixedTimeProvider(utcNow ?? DateTimeOffset.UtcNow));

    private sealed class FixedTimeProvider(DateTimeOffset utc) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => utc;
    }

    private sealed class StubFeeds : IReportFeedRepository
    {
        public int AlarmTotal { get; init; }
        public IReadOnlyDictionary<DateOnly, int> AlarmsByDay { get; init; } = new Dictionary<DateOnly, int>();
        public IReadOnlyList<ReportStatusCount> RequestsByStatus { get; init; } = [];
        public IReadOnlyDictionary<DateOnly, int> RequestsByDay { get; init; } = new Dictionary<DateOnly, int>();
        public IReadOnlyList<ReportStatusCount> ForecastsByStatus { get; init; } = [];
        public (int Total, IReadOnlyList<AlarmReportRow> Rows) AlarmList { get; init; } = (0, []);
        public (int Total, IReadOnlyList<RequestReportRow> Rows) RequestList { get; init; } = (0, []);
        public IReadOnlyList<TechnicianReportRow> Technicians { get; init; } = [];
        public IReadOnlyList<ForecastJournalReportRow> Journals { get; init; } = [];
        public IReadOnlyDictionary<Guid, IReadOnlyList<ForecastJournalResult>> Results { get; init; } =
            new Dictionary<Guid, IReadOnlyList<ForecastJournalResult>>();

        public Task<int> CountAlarmsAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(AlarmTotal);

        public Task<IReadOnlyDictionary<DateOnly, int>> GetAlarmCountsByMoscowDayAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(AlarmsByDay);

        public Task<IReadOnlyList<ReportStatusCount>> GetRequestCountsByStatusCreatedAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(RequestsByStatus);

        public Task<IReadOnlyDictionary<DateOnly, int>> GetRequestCountsByMoscowDayAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(RequestsByDay);

        public Task<IReadOnlyList<ReportStatusCount>> GetForecastCountsByStatusAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(ForecastsByStatus);

        public Task<(int Total, IReadOnlyList<AlarmReportRow> Rows)> ListAlarmsAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            int limit,
            CancellationToken cancellationToken = default)
            => Task.FromResult(AlarmList);

        public Task<(int Total, IReadOnlyList<RequestReportRow> Rows)> ListRequestsAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            int limit,
            CancellationToken cancellationToken = default)
            => Task.FromResult(RequestList);

        public Task<IReadOnlyList<TechnicianReportRow>> ListTechnicianLoadsAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(Technicians);

        public Task<IReadOnlyList<ForecastJournalReportRow>> ListForecastJournalsAsync(
            DateTimeOffset fromInclusive,
            DateTimeOffset toExclusive,
            CancellationToken cancellationToken = default)
            => Task.FromResult(Journals);

        public Task<IReadOnlyDictionary<Guid, IReadOnlyList<ForecastJournalResult>>> ListForecastResultsByJournalsAsync(
            IReadOnlyList<Guid> ids,
            CancellationToken cancellationToken = default)
            => Task.FromResult(Results);
    }
}
