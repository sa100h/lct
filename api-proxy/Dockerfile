FROM node:22 AS frontend-build
WORKDIR /src/web-frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
COPY web-frontend/package.json web-frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web-frontend/ .
RUN pnpm run build

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG BUILD_CONFIGURATION=Release
WORKDIR /src
COPY api-proxy/api-proxy.csproj api-proxy/
COPY shared/shared.csproj shared/
RUN dotnet restore api-proxy/api-proxy.csproj
COPY . .
RUN dotnet publish api-proxy/api-proxy.csproj -c $BUILD_CONFIGURATION -o /app/publish /p:UseAppHost=false
RUN mkdir -p /https && dotnet dev-certs https -ep /https/aspnetapp.pfx -p change-me && chmod 644 /https/aspnetapp.pfx

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
USER $APP_UID
WORKDIR /app
EXPOSE 8080
EXPOSE 8443
COPY --from=build /app/publish .
COPY --from=build /https/aspnetapp.pfx /https/aspnetapp.pfx
COPY --from=frontend-build /src/web-frontend/dist ./wwwroot
ENTRYPOINT ["dotnet", "api-proxy.dll"]
