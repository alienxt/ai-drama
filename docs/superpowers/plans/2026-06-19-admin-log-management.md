# Admin Log Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable backend log recording/query infrastructure and two admin pages for request logs and exception logs.

**Architecture:** Backend logging lives in a focused `logs` package with shared writer/query helpers and separate Mongo documents for request and exception logs. Frontend logging pages share filters and column patterns while staying consistent with the existing `DataPage` and `AdminTable` UI.

**Tech Stack:** Java 21, Spring Boot 3.3, Spring Security, Spring Data MongoDB, React 18, TypeScript, Ant Design.

---

## File Map

- Create `admin/server/src/main/java/com/onehot/aidrama/logs/LogEntry.java`: shared log field contract.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/RequestLog.java`: `request_logs` Mongo document.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/ExceptionLog.java`: `exception_logs` Mongo document.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/RequestLogRepository.java`: repository for request logs.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/ExceptionLogRepository.java`: repository for exception logs.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/LogWriter.java`: best-effort log persistence service.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/LogQuery.java`: shared Mongo query builder for logs.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/LogDtos.java`: API response DTOs.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/LogController.java`: admin log list APIs.
- Create `admin/server/src/main/java/com/onehot/aidrama/logs/RequestLogFilter.java`: API request logging filter.
- Modify `admin/server/src/main/java/com/onehot/aidrama/common/error/GlobalExceptionHandler.java`: record exception logs.
- Create backend tests under `admin/server/src/test/java/com/onehot/aidrama/logs/`.
- Modify `admin/frontend/src/shared/types.ts`: add log types.
- Create `admin/frontend/src/features/logs/LogsPage.tsx`: two log table pages.
- Modify `admin/frontend/src/app/AdminLayout.tsx`: rename group and add menu entries.
- Modify `admin/frontend/src/app/AppRouter.tsx`: add routes.

## Task 1: Backend Log Domain

- [ ] Write failing unit tests for `LogWriter` showing request and exception records are saved and persistence failures are swallowed.
- [ ] Run `cd admin/server && mvn -Dtest=LogWriterTest test` and verify the tests fail because classes do not exist.
- [ ] Implement `LogEntry`, `RequestLog`, `ExceptionLog`, repositories, and `LogWriter`.
- [ ] Re-run `cd admin/server && mvn -Dtest=LogWriterTest test` and verify it passes.

## Task 2: Backend Log Query APIs

- [ ] Write failing tests for `LogQuery` and `LogController` covering keyword filtering, status filtering, and newest-first default sorting.
- [ ] Run `cd admin/server && mvn -Dtest=LogQueryTest,LogControllerTest test` and verify expected failures.
- [ ] Implement `LogQuery`, `LogDtos`, and `LogController`.
- [ ] Re-run `cd admin/server && mvn -Dtest=LogQueryTest,LogControllerTest test` and verify they pass.

## Task 3: Request and Exception Capture

- [ ] Write failing tests for `RequestLogFilter` recording one API request and skipping log endpoints.
- [ ] Write failing tests for `GlobalExceptionHandler` recording exception logs while preserving the API error response.
- [ ] Run `cd admin/server && mvn -Dtest=RequestLogFilterTest,GlobalExceptionHandlerLogTest test` and verify expected failures.
- [ ] Implement `RequestLogFilter`.
- [ ] Update `GlobalExceptionHandler` to accept `LogWriter`, `HttpServletRequest`, and authenticated principal data where available.
- [ ] Re-run the targeted tests and then `cd admin/server && mvn test`.

## Task 4: Frontend Log Pages

- [ ] Add `RequestLog` and `ExceptionLog` types to `admin/frontend/src/shared/types.ts`.
- [ ] Create `admin/frontend/src/features/logs/LogsPage.tsx` with shared filters and two exported pages.
- [ ] Add `/request-logs` and `/exception-logs` routes in `AppRouter.tsx`.
- [ ] Rename menu group from `系统权限` to `系统管理` and add `请求日志` and `异常日志` entries in `AdminLayout.tsx`.
- [ ] Run `cd admin/frontend && npm run build`.

## Task 5: Final Verification

- [ ] Run `cd admin/server && mvn test`.
- [ ] Run `cd admin/frontend && npm run build`.
- [ ] If frontend visual behavior needs checking, start `npm run dev` and inspect the two routes in the browser.
- [ ] Summarize changed files, verification results, and any skipped checks.
