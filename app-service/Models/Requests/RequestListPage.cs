namespace AppService.Models;

public sealed record RequestListPage(
    IReadOnlyList<RequestListItem> Items,
    int Total);
