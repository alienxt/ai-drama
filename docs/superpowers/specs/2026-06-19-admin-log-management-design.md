# Admin Log Management Design

## Goal

Add two system-management log features to the admin console: request logs and exception logs. The implementation should be reusable, so future audit-style logs can share the same recording and query conventions instead of duplicating controller, filtering, and table logic.

## Navigation

Rename the current top-level admin menu group from `系统权限` to `系统管理`. Add two read-only menu entries in that group:

- `请求日志`
- `异常日志`

The existing pages `管理员管理`, `桌面版本`, and `系统配置` remain in the same group after the rename.

## Backend Architecture

Create a new `logs` package under `admin/server/src/main/java/com/onehot/aidrama/logs`.

The package is split into focused units:

- `LogEntry`: a small interface for shared log fields such as `id`, `traceId`, `method`, `path`, `status`, `username`, `accountId`, `clientIp`, `userAgent`, and `createdAt`.
- `RequestLog`: Mongo document stored in `request_logs`. It records request metadata and duration.
- `ExceptionLog`: Mongo document stored in `exception_logs`. It records exception metadata, business error code, message, exception class, and stack trace preview.
- `LogWriter`: service responsible for best-effort persistence. It catches and logs write failures so logging never breaks user requests.
- `LogQuery`: query helper for shared filters: keyword, method, path, status, traceId, username, and time range.
- `LogDtos`: response records for the two admin tables.
- `LogController`: admin-only paginated read API.

This keeps collection-specific document shape separate from shared query and recording mechanics.

## Request Recording

Add a `RequestLogFilter` that runs after the existing trace id setup. It measures request duration and writes one `RequestLog` after the filter chain returns.

It records:

- `traceId`
- `method`
- `path`
- `query`
- `status`
- `durationMs`
- authenticated `accountId` and `username` when present
- `clientIp`
- `userAgent`
- `createdAt`

Static resources and log-query endpoints should be excluded to prevent noise and recursive log growth. The first scope excludes:

- `/api/admin/request-logs`
- `/api/admin/exception-logs`
- `/uploads/**`
- frontend/static asset requests outside `/api/**`

The filter records all other `/api/**` requests, including successful, failed, admin, and desktop requests.

## Exception Recording

Update `GlobalExceptionHandler` to use `LogWriter` when an exception is converted into an API error response.

It records:

- `traceId`
- `method`
- `path`
- `status`
- error `code`
- user-facing `message`
- exception class name
- stack trace preview capped to a reasonable length
- authenticated `accountId` and `username` when present
- `clientIp`
- `userAgent`
- `createdAt`

The global handler remains responsible for API shape. Logging is a side effect through `LogWriter`, not embedded storage logic.

## Admin APIs

Add two endpoints:

- `GET /api/admin/request-logs`
- `GET /api/admin/exception-logs`

Both require `hasRole('ADMIN')`, follow existing `ApiResponse<PageResult<T>>` shape, and support:

- `keyword`: searches trace id, path, username, client IP, user agent, and message where relevant
- `method`
- `status`
- `traceId`
- `username`
- `from`
- `to`
- standard Spring `Pageable`

Default sorting should show newest first. If the caller does not send sort options, the controller applies `createdAt DESC`.

## Frontend Architecture

Create `admin/frontend/src/features/logs/LogsPage.tsx` with two exported pages:

- `RequestLogsPage`
- `ExceptionLogsPage`

Shared frontend pieces stay in the same file unless they grow large:

- `LogFilters`: common toolbar fields for keyword, method, status, and trace id
- `baseColumns`: shared columns for time, trace id, request, status, user, IP, and UA

Add `RequestLog` and `ExceptionLog` types to `shared/types.ts`.

Routes:

- `/request-logs`
- `/exception-logs`

Both pages use the existing `DataPage`, `TableToolbar`, and `AdminTable` patterns.

## Error Handling

Log writes must never fail the original request. `LogWriter` catches persistence exceptions and sends a warning to SLF4J.

Exception logging should also avoid recursion: if log persistence fails inside exception handling, the handler still returns the original API error response.

## Testing

Backend tests should cover:

- `LogQuery` filters and default sorting.
- `LogWriter` creates request and exception log documents.
- `GlobalExceptionHandler` delegates exception recording without changing the existing error response shape.
- `RequestLogFilter` writes one request log for an API request and skips log endpoints.

Frontend verification should cover build/type safety:

- Routes compile.
- Table columns and API type usage compile.
- Menu group rename compiles.

## Non-Goals

- No retention cleanup job in this change.
- No export/download feature.
- No request/response body capture. This avoids leaking credentials, tokens, uploads, or business data into logs.
- No per-role fine-grained log permissions beyond existing `ADMIN`.
