using System.Globalization;
using AppService.Models;

namespace AppService.Services.Domain;

public static class ReportCodes
{
    private static readonly Dictionary<string, ReportCodeInfo> ByCode = new(StringComparer.Ordinal)
    {
        ["summary"] = new("summary", "Оперативная сводка", "svodka"),
        ["alarms"] = new("alarms", "Журнал тревог", "trevogi"),
        ["requests"] = new("requests", "Заявки за период", "zayavki"),
        ["technicians"] = new("technicians", "Нагрузка техников", "tehniki"),
        ["forecasts"] = new("forecasts", "Прогнозы за период", "prognozy"),
    };

    public static bool TryGet(string code, out ReportCodeInfo info)
        => ByCode.TryGetValue(code, out info!);

    public static string FileName(string stem, DateOnly from, DateOnly to)
        => $"{stem}_{from.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}_{to.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}.pdf";
}
