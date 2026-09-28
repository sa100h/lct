using AppService.Models;

namespace AppService.Services.Domain;

public sealed class RequestCommandService(
    IRequestRepository requests,
    IDispatcherObjectRepository objects) : IRequestCommandService
{
    public const string MissingJournal = "Прогноз не найден.";
    public const string MissingTechnician = "Техник не найден.";
    public const string MissingObject = "Объект не найден.";
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

        if (!await requests.ForecastJournalExistsAsync(command.ForecastJournalId, cancellationToken))
        {
            throw new KeyNotFoundException(MissingJournal);
        }

        if (!await requests.IsActiveTechnicianAsync(command.TechnicianId, cancellationToken))
        {
            throw new ArgumentException(MissingTechnician);
        }

        var objectIds = await objects.GetSubtreeIdsAsync(command.DispatcherObjectId, cancellationToken);
        if (objectIds.Count == 0)
        {
            throw new ArgumentException(MissingObject);
        }

        return await requests.InsertAsync(
            command.ForecastJournalId,
            description,
            dispatcherUserId,
            command.TechnicianId,
            objectIds,
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
