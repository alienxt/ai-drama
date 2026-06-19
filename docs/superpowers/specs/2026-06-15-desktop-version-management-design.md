# Desktop Version Management Design

## Goal

Add an operational desktop release system: administrators can publish macOS and Windows installers, the desktop app can show its current version, check for updates at launch, download the matching installer, open it, and keep normal app usage intact.

## Scope

This implementation covers installer-based updates, not silent binary replacement. The desktop app downloads the installer package for its platform, opens it with the operating system, and exits after launching the installer. A later updater framework can replace this behavior if fully silent updates become required.

## Backend

Create a desktop version module under `admin/server/src/main/java/com/onehot/aidrama/versions`.

Version records are stored in MongoDB with:

- `platform`: `MAC` or `WINDOWS`
- `version`: semantic version text such as `0.1.1`
- `releaseNotes`
- `mandatory`
- `published`
- `fileName`
- `fileSize`
- `downloadUrl`
- `createdAt` and `updatedAt`

Admin APIs live under `/api/admin/desktop-versions` and require authentication. They support listing, creating metadata, uploading an installer file for a version, and publishing or unpublishing a version.

Desktop APIs live under `/api/desktop/versions` and require the already authenticated desktop user. `GET /api/desktop/versions/check?platform=MAC&currentVersion=0.1.0` returns either `updateAvailable=false` or the newest published version for that platform.

Installer files are stored under the existing upload root in `uploads/desktop-versions/{platform}/{version}/...` and are served through the existing `/uploads/**` static resource mapping.

## Admin Frontend

Add a "桌面版本" page to the system section. The page lists versions, platform, published state, package size, download link, and update notes. It provides forms to create/update version metadata, upload the installer package, and publish/unpublish a version.

The page follows current React + Ant Design patterns: `DataPage`, `AdminTable`, `TableToolbar`, and shared `http` helpers. File upload uses the existing bearer token.

## Desktop Client

Expose the current version from `aidrama_desktop.__version__` in the window title or settings area. At app launch, after login state is available, call the update check endpoint with:

- detected platform: `MAC` for Darwin, `WINDOWS` for Windows
- current package version

When a newer published version exists, show a modal with version, notes, package size, and buttons to update now or later. Clicking update downloads the installer to a local update directory, opens it with the OS (`open` on macOS, `os.startfile` on Windows), and exits the app after the installer is launched.

If update checking or downloading fails, the desktop app logs a clear message and continues running unless the release is mandatory. Mandatory updates keep prompting and should not start background publishing work.

## Packaging And Verification

Use the existing PyInstaller spec in `desktop/packaging/pyinstaller/ai-drama-desktop.spec` to build a local app artifact on the current machine. Upload that artifact through the new admin API as a later version, start an older local desktop version, confirm update detection, trigger download, and verify the downloaded file opens.

Full Windows installer behavior cannot be executed on macOS. The Windows path is covered by unit tests for platform detection, API payloads, and opener selection, plus backend file type validation. macOS is tested end-to-end on this machine.

