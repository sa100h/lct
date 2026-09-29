using AppService.Models;

namespace AppService.Services.Domain;

public sealed class RequestCommandService(
    IRequestRepository requests,
    IForecastJournalRepository journal,
    IDispatcherObjectRepository objects) : IRequestCommandService
{
    public const string MissingJournal = "Прогноз не найден.";
    public const string MissingTechnician = "Техник не найден.";
    public const string MissingObject = "Объект не найден.";
    public const string EmptyObjects = "Выберите объекты.";
    public const string DescriptionRequired = "Описание обязательно.";
    public const string MissingRequest = "Заявка не найдена.";
    public const string UnknownStatus = "Неизвестный статус.";

    public async Task<Guid> CreateAsync(
        Guid dispatcherUserId,
        CreateRequestCommand command,
        CancellationToken cancellationToken = default)
    {
        var description = command.Description?.Trim() ?? "";
        if (description.Length == 0)
        {
            throw new ArgumentException(DescriptionRequired);
        }

        if (command.DispatcherObjectIds is null || command.DispatcherObjectIds.Count == 0)
        {
            throw new ArgumentException(EmptyObjects);
        }

        var header = await journal.GetHeaderAsync(command.ForecastJournalId, cancellationToken);
        if (header is null)
        {
            throw new KeyNotFoundException(MissingJournal);
        }

        if (!await requests.IsActiveTechnicianAsync(command.TechnicianId, cancellationToken))
        {
            throw new ArgumentException(MissingTechnician);
        }

        var all = await objects.GetAllWithDescendantStatusesAsync(cancellationToken);
        var allowed = ForecastJournalTree.AllowedIds(header.DispatcherObjectIds, all);
        if (command.DispatcherObjectIds.Any(id => !allowed.Contains(id)))
        {
            throw new ArgumentException(MissingObject);
        }

        return await requests.InsertAsync(
            command.ForecastJournalId,
            description,
            dispatcherUserId,
            command.TechnicianId,
            command.DispatcherObjectIds.Distinct().ToArray(),
            command.Priority,
            cancellationToken);
    }

    public async Task UpdateStatusAsync(
        Guid id,
        bool seesAll,
        Guid userId,
        string status,
        CancellationToken cancellationToken = default)
    {
        var name = status?.Trim() ?? "";
        if (name.Length == 0 || !await requests.StatusExistsAsync(name, cancellationToken))
        {
            throw new ArgumentException(UnknownStatus);
        }

        var updated = await requests.UpdateStatusAsync(
            id,
            name,
            seesAll ? null : userId,
            cancellationToken);
        if (!updated)
        {
            throw new KeyNotFoundException(MissingRequest);
        }
    }
}
