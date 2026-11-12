FROM mcr.microsoft.com/dotnet/sdk:10.0.404 AS build
WORKDIR /src
COPY src/Ops.Api/Ops.Api.csproj src/Ops.Api/
RUN dotnet restore src/Ops.Api/Ops.Api.csproj
COPY src/Ops.Api/ src/Ops.Api/
RUN dotnet publish src/Ops.Api/Ops.Api.csproj -c Release --no-restore -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0.15 AS runtime
WORKDIR /app
COPY --from=build /app/publish ./
ENV ASPNETCORE_HTTP_PORTS=8080 DOTNET_EnableDiagnostics=0
USER $APP_UID
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["dotnet", "Ops.Api.dll", "--healthcheck"]
ENTRYPOINT ["dotnet", "Ops.Api.dll"]
