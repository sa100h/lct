namespace AppService.Services.Domain;

public static class ReportForecastStatus
{
    public static string Label(string status)
        => status switch
        {
            "pending" => "Ожидание",
            "running" => "В работе",
            "done" => "Готово",
            _ => status,
        };
}
