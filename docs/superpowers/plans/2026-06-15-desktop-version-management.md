# Desktop Version Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a desktop release management flow for macOS and Windows installers.

**Architecture:** Store release metadata in MongoDB, store installer files under the existing upload directory, expose admin management APIs and authenticated desktop update-check APIs, then add desktop startup checks and installer download/open behavior. The admin UI gets a focused version page in the existing Ant Design shell.

**Tech Stack:** Spring Boot 3, MongoDB repositories, React + Ant Design + axios, Python/PySide6/httpx/PyInstaller.

---

## File Structure

- Create `admin/server/src/main/java/com/onehot/aidrama/versions/*` for platform enum, entity, repository, service, storage, DTOs, and controller.
- Modify `admin/server/src/main/java/com/onehot/aidrama/common/security/SecurityConfig.java` only if unauthenticated downloads/checks are required. The chosen design keeps desktop checks authenticated and downloads public through `/uploads/**`.
- Create `admin/server/src/test/java/com/onehot/aidrama/versions/*Test.java` for service and controller behavior.
- Create `admin/frontend/src/features/versions/DesktopVersionsPage.tsx`.
- Modify `admin/frontend/src/app/AdminLayout.tsx`, `admin/frontend/src/app/AppRouter.tsx`, and `admin/frontend/src/shared/types.ts`.
- Create `desktop/src/aidrama_desktop/update.py`.
- Modify `desktop/src/aidrama_desktop/api/client.py`, `desktop/src/aidrama_desktop/gui/app.py`, and possibly `desktop/src/aidrama_desktop/gui/state.py`.
- Create `desktop/tests/test_update.py` and extend API client tests.

## Tasks

### Task 1: Backend Version Domain

- [ ] Write failing service tests for semantic version comparison, per-platform latest published selection, and unsupported platform rejection.
- [ ] Run `cd admin/server && mvn -Dtest=DesktopVersionServiceTest test` and confirm the tests fail because the module does not exist.
- [ ] Implement `DesktopPlatform`, `DesktopVersion`, `DesktopVersionRepository`, and `DesktopVersionService`.
- [ ] Run the same Maven test and confirm it passes.

### Task 2: Backend Upload And APIs

- [ ] Write failing controller/storage tests for creating metadata, uploading a package, publishing a version, and checking updates.
- [ ] Run targeted Maven tests and confirm they fail for missing endpoints.
- [ ] Implement DTOs, storage class, and `DesktopVersionController` with `/api/admin/desktop-versions` and `/api/desktop/versions/check`.
- [ ] Run targeted Maven tests, then `cd admin/server && mvn test`.

### Task 3: Admin Frontend

- [ ] Add a version type in `shared/types.ts`.
- [ ] Build `DesktopVersionsPage.tsx` using existing `DataPage` and `AdminTable` patterns.
- [ ] Wire the nav item and route.
- [ ] Run `cd admin/frontend && npm run build`.

### Task 4: Desktop Update Client

- [ ] Write failing Python tests for platform detection, update-check API call, download target naming, and installer opener dispatch.
- [ ] Run `cd desktop && pytest tests/test_update.py tests/test_api_client_device.py -q` and confirm the new tests fail.
- [ ] Implement `update.py`, add `ApiClient.check_update`, and wire launch check in `DesktopWindow`.
- [ ] Run desktop tests.

### Task 5: Packaging And Local End-To-End Check

- [ ] Build the backend and frontend.
- [ ] Build the desktop app with the PyInstaller spec.
- [ ] Start or reuse the local backend.
- [ ] Upload the built macOS artifact through the admin API as a newer `MAC` version.
- [ ] Launch the desktop app at the old version and verify it shows the update prompt.
- [ ] Click update, verify download completes, verify the installer/app artifact opens, then verify basic login and main UI still work.

## Notes

This workspace is not currently a git repository, so commit steps are intentionally omitted. If the repository metadata is restored, commit after each task using concise feature/test messages.

