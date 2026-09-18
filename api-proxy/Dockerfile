FROM node:22 AS frontend-build
WORKDIR /src/web-frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
ARG VITE_YANDEX_MAPS_API_KEY
ENV VITE_YANDEX_MAPS_API_KEY=$VITE_YANDEX_MAPS_API_KEY
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

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS dev-certificate
RUN mkdir -p /https && dotnet dev-certs https --export-path /https/fullchain.pem --format PEM --no-password && mv /https/fullchain.key /https/privkey.pem

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
EXPOSE 8080
EXPOSE 8443
COPY --from=build /app/publish .
COPY --from=frontend-build /src/web-frontend/dist ./wwwroot
USER $APP_UID
ENTRYPOINT ["dotnet", "api-proxy.dll"]

FROM runtime AS local
USER root
COPY --from=dev-certificate /https/fullchain.pem /https/privkey.pem /https/
RUN chmod 644 /https/fullchain.pem && chown $APP_UID:$APP_UID /https/privkey.pem && chmod 600 /https/privkey.pem
USER $APP_UID

FROM runtime AS final
