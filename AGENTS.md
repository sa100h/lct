---
name: "General task planning and verification"
applyTo: "**/*"
---

- Before approving a plan or starting an implementation, review the task for uncertainties, omissions, conceptual gaps, and requirements that may be interpreted in more than one way.
- If any uncertainty, ambiguity, missing information, or conceptual question exists, inform the user immediately and ask for clarification. Do not make planning or implementation decisions on the user's behalf or without the user's knowledge and explicit approval.
- Before starting an implementation, prepare a concise plan describing what will be changed and present it to the user for review and approval. Do not begin implementation until the user has approved the plan.
- While working, periodically verify that the available information is still sufficient to complete the task correctly.
- If implementation problems, unresolved questions, or missing information arise, stop the affected work and notify the user instead of silently choosing an assumption.
- After completing the task, return to the originally approved plan and verify every item explicitly before reporting completion.

---
name: "C# backend conventions"
applyTo: "**/*.cs"
---

- Prefer one public type per file.
- Use file-scoped namespaces.
- Prefer primary constructors where they improve readability.
- Use `sealed` for classes not intended for inheritance.
- Avoid service locator patterns.
- Prefer explicit interfaces for cross-layer services.
- Validation goes in validators/pipeline, not inline in endpoints.
- Mapping code should be explicit; avoid hidden magic unless mapper is already standard in the repo.
- Follow standard C# naming conventions (PascalCase for classes/methods, camelCase for variables).
- Async/Await: Always use async/await for I/O-bound operations with proper `CancellationToken` usage[reference:11].
- Single Responsibility: Each class and method should have a clear, single purpose.
- Reuse, Don't Reinvent: Before creating a new helper, check if one already exists in `Shared` libraries.
- Keep `Shared` implementation-agnostic: it must not depend on a particular microservice, product, business system, or concrete implementation. Treat it as a reusable library, prefer abstractions and generalized solutions, and keep service-specific behavior in the owning service.
- Before writing backend code, describe the proposed architecture explicitly: list the classes and interfaces, their locations, responsibilities, dependencies, and interactions. Review the proposal for cleanliness, extensibility, testability, and clarity, and follow DDD concepts where they fit the task and the existing architecture.
- Present the backend architecture proposal as part of the implementation plan and obtain the user's approval before writing code.
- After writing backend code, perform another architectural review of all newly written or changed code. Look for weak boundaries, unnecessary coupling, unclear responsibilities, poor extensibility or testability, and deviations from the approved design or task requirements.
- If the post-implementation review reveals a materially better architecture that still fits the requirements, revise the implementation accordingly and review it again.
- If an architectural ambiguity, unstated requirement, or conceptual decision appears at any stage, notify the user and ask for a decision. Do not choose an architecture-affecting assumption without the user's knowledge and approval.

Common microservice structure:
MicroService/
- Controllers/          # only routing and validation, no business logic!
  - Contracts/            # DTOs for API (Request/Response records)
  - Services/
    - Domain/           # Core business logic
    - Infrastructure/   # Technical services (e.g. IEmailSender, IExcelProcessor)
- Data/
    - Repositories/     # Data access layer with Repository pattern
    - Contexts/         # EF Core DbContexts
- Models/               # Domain models (not for API!)
- Extensions/           # Dependency Injection setup

---
name: "React frontend conventions"
applyTo: "web-frontend/src/**/*.{js,jsx}"
---

