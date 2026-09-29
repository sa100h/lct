using System.Globalization;
using System.Reflection;
using AppService.Models;
using AppService.Services.Domain;
using QuestPDF.Drawing;
using QuestPDF.Fluent;
using QuestPDF.Helpers;
using QuestPDF.Infrastructure;

namespace AppService.Services.Infrastructure;

public sealed class ReportPdfRenderer : IReportPdfRenderer
{
    private const string FontFamily = "Noto Sans";

    static ReportPdfRenderer()
    {
        QuestPDF.Settings.License = LicenseType.Community;
        using var font = Assembly.GetExecutingAssembly()
            .GetManifestResourceStream("AppService.Assets.NotoSans-Regular.ttf")
            ?? throw new InvalidOperationException("NotoSans missing.");
        FontManager.RegisterFont(font);
    }

    public byte[] Render(ReportDocument document)
        => Document.Create(container =>
            {
                container.Page(page =>
                {
                    page.Size(PageSizes.A4);
                    page.Margin(40);
                    page.DefaultTextStyle(style => style.FontFamily(FontFamily).FontSize(10));
                    page.Content().Column(column =>
                    {
                        WriteHeader(column, document.Header);
                        WriteBody(column, document.Body);
                    });
                });
            })
            .GeneratePdf();

    private static void WriteHeader(ColumnDescriptor column, ReportHeader header)
    {
        column.Item().Text(header.Title).FontSize(16).Bold();
        column.Item().PaddingTop(4).Text(
            $"Период: {header.From.ToString("dd.MM.yyyy", CultureInfo.InvariantCulture)} – {header.To.ToString("dd.MM.yyyy", CultureInfo.InvariantCulture)} (Москва)");
        var generated = TimeZoneInfo.ConvertTime(header.GeneratedAt, ReportPeriod.Moscow);
        column.Item().Text($"Сформирован: {generated.ToString("dd.MM.yyyy HH:mm", CultureInfo.InvariantCulture)}");
        column.Item().PaddingBottom(12);
    }

    private static void WriteBody(ColumnDescriptor column, IReportBody body)
    {
        switch (body)
        {
            case SummaryReportBody summary:
                WriteSummary(column, summary.Data);
                break;
            case AlarmReportBody alarms:
                WriteAlarms(column, alarms);
                break;
            case RequestReportBody requests:
                WriteRequests(column, requests);
                break;
            case TechnicianReportBody technicians:
                WriteTechnicians(column, technicians);
                break;
            case ForecastReportBody forecasts:
                WriteForecasts(column, forecasts);
                break;
            default:
                column.Item().Text("Нет данных за период");
                break;
        }
    }

    private static void WriteSummary(ColumnDescriptor column, SummaryReport data)
    {
        column.Item().Text($"Тревоги: {data.AlarmTotal}");
        foreach (var row in data.RequestsByStatus)
        {
            column.Item().Text($"Заявки «{row.Status}»: {row.Count}");
        }

        column.Item().Text($"Заявки всего: {data.RequestsTotal}");
        foreach (var row in data.ForecastsByStatus)
        {
            column.Item().Text($"Прогнозы «{ReportForecastStatus.Label(row.Status)}»: {row.Count}");
        }

        column.Item().PaddingTop(10).Text("Тревоги по дням").Bold();
        WriteDayTable(column, data.AlarmsByDay);
        column.Item().PaddingTop(10).Text("Заявки по дням").Bold();
        WriteDayTable(column, data.RequestsByDay);
    }

    private static void WriteAlarms(ColumnDescriptor column, AlarmReportBody data)
    {
        if (data.Rows.Count == 0)
        {
            column.Item().Text("Нет данных за период");
            return;
        }

        WriteTruncation(column, data.Rows.Count, data.Total);
        column.Item().Table(table =>
        {
            table.ColumnsDefinition(columns =>
            {
                columns.RelativeColumn(2);
                columns.RelativeColumn(2);
                columns.RelativeColumn(1);
                columns.RelativeColumn(2);
            });
            HeaderRow(table, ["Время", "Объект", "Канал", "Значение"]);
            foreach (var row in data.Rows)
            {
                table.Cell().Element(Cell).Text(FormatMoscow(row.At));
                table.Cell().Element(Cell).Text(row.ObjectName);
                table.Cell().Element(Cell).Text(row.ChannelId.ToString(CultureInfo.InvariantCulture));
                table.Cell().Element(Cell).Text(row.Value ?? "");
            }
        });
    }

    private static void WriteRequests(ColumnDescriptor column, RequestReportBody data)
    {
        if (data.Rows.Count == 0)
        {
            column.Item().Text("Нет данных за период");
            return;
        }

        WriteTruncation(column, data.Rows.Count, data.Total);
        column.Item().Table(table =>
        {
            table.ColumnsDefinition(columns =>
            {
                columns.RelativeColumn(2);
                columns.RelativeColumn(3);
                columns.RelativeColumn(2);
                columns.RelativeColumn(1);
                columns.RelativeColumn(2);
                columns.RelativeColumn(2);
            });
            HeaderRow(table, ["Дата", "Описание", "Объект", "Статус", "Диспетчер", "Техник"]);
            foreach (var row in data.Rows)
            {
                table.Cell().Element(Cell).Text(FormatMoscow(row.CreatedAt));
                table.Cell().Element(Cell).Text(row.Description);
                table.Cell().Element(Cell).Text(row.ObjectName);
                table.Cell().Element(Cell).Text(row.Status);
                table.Cell().Element(Cell).Text(row.DispatcherLogin);
                table.Cell().Element(Cell).Text(row.TechnicianLogin);
            }
        });
    }

    private static void WriteTechnicians(ColumnDescriptor column, TechnicianReportBody data)
    {
        if (data.Rows.Count == 0)
        {
            column.Item().Text("Нет данных за период");
            return;
        }

        column.Item().Table(table =>
        {
            table.ColumnsDefinition(columns =>
            {
                columns.RelativeColumn(2);
                columns.RelativeColumn();
                columns.RelativeColumn();
            });
            HeaderRow(table, ["Техник", "Создано", "Закрыто"]);
            foreach (var row in data.Rows)
            {
                table.Cell().Element(Cell).Text(row.Login);
                table.Cell().Element(Cell).Text(row.Created.ToString(CultureInfo.InvariantCulture));
                table.Cell().Element(Cell).Text(row.Closed.ToString(CultureInfo.InvariantCulture));
            }
        });
    }

    private static void WriteForecasts(ColumnDescriptor column, ForecastReportBody data)
    {
        column.Item().Text($"Готово: {data.DoneCount}");
        column.Item().Text($"Объектов с высоким риском: {data.HighRiskObjects}");
        if (data.Rows.Count == 0)
        {
            column.Item().PaddingTop(8).Text("Нет данных за период");
            return;
        }

        column.Item().PaddingTop(8).Table(table =>
        {
            table.ColumnsDefinition(columns =>
            {
                columns.RelativeColumn(2);
                columns.RelativeColumn(2);
                columns.RelativeColumn(2);
                columns.RelativeColumn();
            });
            HeaderRow(table, ["Дата", "Автор", "Статус", "Объекты"]);
            foreach (var row in data.Rows)
            {
                table.Cell().Element(Cell).Text(FormatMoscow(row.CreatedAt));
                table.Cell().Element(Cell).Text(row.AuthorLogin);
                table.Cell().Element(Cell).Text(ReportForecastStatus.Label(row.Status));
                table.Cell().Element(Cell).Text(row.ObjectCount.ToString(CultureInfo.InvariantCulture));
            }
        });
    }

    private static void WriteDayTable(ColumnDescriptor column, IReadOnlyList<ReportDayCount> rows)
    {
        column.Item().Table(table =>
        {
            table.ColumnsDefinition(columns =>
            {
                columns.RelativeColumn();
                columns.RelativeColumn();
            });
            HeaderRow(table, ["Дата", "Количество"]);
            foreach (var row in rows)
            {
                table.Cell().Element(Cell).Text(row.Date.ToString("dd.MM.yyyy", CultureInfo.InvariantCulture));
                table.Cell().Element(Cell).Text(row.Count.ToString(CultureInfo.InvariantCulture));
            }
        });
    }

    private static void WriteTruncation(ColumnDescriptor column, int shown, int total)
    {
        if (total > shown)
        {
            column.Item().PaddingBottom(6).Text($"показано {shown} из {total}");
        }
    }

    private static void HeaderRow(TableDescriptor table, IReadOnlyList<string> titles)
    {
        foreach (var title in titles)
        {
            table.Cell().Element(HeaderCell).Text(title).Bold();
        }
    }

    private static IContainer Cell(IContainer container)
        => container.Padding(4).BorderBottom(0.5f).BorderColor(Colors.Grey.Lighten2);

    private static IContainer HeaderCell(IContainer container)
        => container.Background("#f5f5f5").Padding(4);

    private static string FormatMoscow(DateTimeOffset value)
        => TimeZoneInfo.ConvertTime(value, ReportPeriod.Moscow)
            .ToString("dd.MM.yyyy HH:mm", CultureInfo.InvariantCulture);
}
