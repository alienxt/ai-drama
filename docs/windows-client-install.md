# Windows 客户端安装文档

本文面向 AI Drama Desktop 的 Windows 使用机器。普通用户只需要安装客户端和运行依赖，不需要安装 Git、Inno Setup 或项目源码。只有启用本机字幕识别时，才需要额外安装官方版 Python 3.11。

## 1. 必装软件清单

| 软件 | 用途 | 下载地址 | 安装方式 |
| --- | --- | --- | --- |
| AI Drama Desktop | 客户端程序 | 由管理员提供 `.exe` 安装包 | 双击安装 |
| Google Chrome | 登录媒体号、自动打开发布页面、上传视频 | https://www.google.com/chrome/ | 默认安装 |
| FFmpeg | 视频转码、提高码率、添加封面帧 | https://ffmpeg.org/download.html | 下载 Windows 预编译包后解压 |
| faster-whisper | 可选：为剪映工程生成中文字幕 SRT | https://www.python.org/downloads/release/python-3119/ | 安装官方 Python 3.11 后通过 pip 安装 |
| Node.js | 运行剪映工程截图生成工具 | https://nodejs.org/ | 默认安装 |
| 剪映专业版 | 生成剧目制作证明用剪映工程截图 | 官方剪映专业版安装包 | 安装 5.9 或兼容版本 |
| LibreOffice | 将合同 Word `.docx` 转为 PDF | https://www.libreoffice.org/download/ | 默认安装 |
| Poppler | 将合同 PDF 转为 PNG 图片 | https://github.com/oschwartz10612/poppler-windows/releases | 下载 zip 后解压 |

Word 或 WPS 不是客户端运行必需软件，但整理合同模板时建议安装一个能打开 `.docx` 的办公软件。

## 2. 安装客户端

优先使用管理员提供的安装包：

```text
AI-Drama-Desktop-Setup-0.1.6-windows-x64.exe
```

安装步骤：

1. 关闭正在运行的旧版客户端。
2. 双击新的 `.exe` 安装包。
3. 按安装向导默认下一步安装。
4. 安装完成后，从桌面或开始菜单打开 `AI Drama Desktop`。

如果使用便携版，解压后运行：

```text
AI Drama Desktop\AI Drama Desktop.exe
```

## 3. 安装 Google Chrome

下载地址：

```text
https://www.google.com/chrome/
```

安装步骤：

1. 打开下载地址。
2. 点击下载 Chrome。
3. 下载完成后双击安装程序。
4. 按默认选项安装即可。

默认安装路径通常是：

```text
C:\Program Files\Google\Chrome\Application\chrome.exe
```

如果客户端提示找不到 Chrome，再设置环境变量：

```powershell
setx AIDRAMA_CHROME_PATH "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

设置后需要重新打开客户端。

## 4. 安装 FFmpeg

用途：视频转码、提高码率、添加封面帧。Windows 上视频处理慢通常也是 FFmpeg 在重新编码整集视频。

下载入口：

```text
https://ffmpeg.org/download.html
```

推荐下载方式：

1. 打开 FFmpeg 下载页。
2. 找到 Windows 图标。
3. 进入 Windows builds，例如：

```text
https://www.gyan.dev/ffmpeg/builds/
```

4. 下载 `ffmpeg-release-essentials.zip`。
5. 解压到：

```text
C:\Tools\ffmpeg
```

最终需要确认这个文件存在：

```text
C:\Tools\ffmpeg\bin\ffmpeg.exe
```

如果解压后多了一层目录，例如：

```text
C:\Tools\ffmpeg\ffmpeg-xxxx-essentials_build\bin\ffmpeg.exe
```

可以把里面的内容移动出来，整理成：

```text
C:\Tools\ffmpeg\bin\ffmpeg.exe
C:\Tools\ffmpeg\bin\ffprobe.exe
```

设置客户端使用的 FFmpeg 路径：

```powershell
setx AIDRAMA_FFMPEG_PATH "C:\Tools\ffmpeg\bin\ffmpeg.exe"
```

验证：

```powershell
C:\Tools\ffmpeg\bin\ffmpeg.exe -version
C:\Tools\ffmpeg\bin\ffprobe.exe -version
```

如果已经把 `C:\Tools\ffmpeg\bin` 加入系统 PATH，也可以直接验证：

```powershell
ffmpeg -version
ffprobe -version
```

## 5. 安装字幕识别（可选：剪映字幕识别）

用途：客户端可以调用本机 `faster-whisper` 识别视频对白，生成剪映工程可用的中文字幕 SRT。新版客户端默认优先使用 `faster-whisper`，如果没有安装才会回退到原来的 `openai-whisper` 命令。

不要使用绿色版或 embeddable Python 安装字幕识别依赖。如果运行下面命令：

```cmd
C:\duanju_ruanjian\python3.11\python.exe -m pip --version
C:\duanju_ruanjian\python3.11\python.exe -m ensurepip --upgrade
```

出现：

```text
No module named pip
No module named ensurepip
```

说明这个 Python 不适合安装字幕识别依赖。它默认没有 `pip`、没有 `ensurepip`，后面安装 `faster-whisper` 或 `openai-whisper` 也容易继续踩坑。

推荐直接安装官方版 Python 3.11：

1. 打开下载页：

```text
https://www.python.org/downloads/release/python-3119/
```

2. 下载 `Windows installer (64-bit)`。
3. 安装时一定勾选：

```text
Add python.exe to PATH
pip
```

4. 安装完成后，关闭并重新打开 CMD 或 PowerShell。
5. 验证 Python 和 pip：

```cmd
py -3.11 --version
py -3.11 -m pip --version
```

如果 `python --version` 提示跳转 Microsoft Store，可以到 Windows 设置里关闭执行别名：

```text
设置 -> 应用 -> 高级应用设置 -> 应用执行别名
```

把 `python.exe` 和 `python3.exe` 的 Microsoft Store 开关关掉。

创建独立 faster-whisper 环境：

```cmd
py -3.11 -m venv C:\AI-Drama\faster-whisper-venv
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -m pip install -U pip setuptools wheel
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -m pip install -U faster-whisper
```

如果 Windows 上安装 faster-whisper 下载很慢，可以先配置国内 PyPI 镜像，再安装：

```cmd
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -m pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -m pip install -U pip setuptools wheel
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -m pip install -U faster-whisper
```

如果不是虚拟环境，也可以把上面的 `C:\AI-Drama\faster-whisper-venv\Scripts\python.exe` 换成 `python`。

验证 faster-whisper：

```cmd
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; print('faster-whisper ok')"
```

设置客户端使用 faster-whisper：

```powershell
setx AIDRAMA_SUBTITLE_PROVIDER "fasterWhisper"
setx AIDRAMA_FASTER_WHISPER_PYTHON_PATH "C:\AI-Drama\faster-whisper-venv\Scripts\python.exe"
```

设置后需要关闭并重新打开客户端。也可以在客户端“系统配置/工具路径”里手动填写：

```text
字幕引擎：faster-whisper（推荐）
faster-whisper Python：C:\AI-Drama\faster-whisper-venv\Scripts\python.exe
```

第一次运行 faster-whisper 会下载模型。客户端默认使用 `base` 模型、中文识别和 `int8` 计算，CPU 也能运行，比原来的 `openai-whisper small` 更适合 Windows 客户端。

## 6. 安装 LibreOffice

用途：完整发布任务中，将 Word 合同 `.docx` 转成 `.pdf`。

下载地址：

```text
https://www.libreoffice.org/download/
```

安装步骤：

1. 打开下载地址。
2. 选择 Windows 版本。
3. 下载 `.msi` 安装包。
4. 双击安装，按默认选项安装。

默认安装路径通常是：

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

设置客户端使用的 LibreOffice 路径：

```powershell
setx AIDRAMA_SOFFICE_PATH "C:\Program Files\LibreOffice\program\soffice.exe"
```

验证：

```powershell
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
```

如果已经加入系统 PATH，也可以直接验证：

```powershell
soffice --version
```

## 7. 安装 Poppler

用途：完整发布任务中，将合同 PDF 转成 PNG 图片，主要使用 `pdftoppm.exe`。

Windows 预编译包下载地址：

```text
https://github.com/oschwartz10612/poppler-windows/releases
```

安装步骤：

1. 打开下载地址。
2. 进入最新的 Release。
3. 下载 zip 包，例如 `Release-xx.xx.x-0.zip`。
4. 解压到：

```text
C:\Tools\poppler
```

最终需要确认这个文件存在：

```text
C:\Tools\poppler\Library\bin\pdftoppm.exe
```

设置客户端使用的 Poppler 路径：

```powershell
setx AIDRAMA_PDFTOPPM_PATH "C:\Tools\poppler\Library\bin\pdftoppm.exe"
```

验证：

```powershell
C:\Tools\poppler\Library\bin\pdftoppm.exe -v
```

如果已经把 `C:\Tools\poppler\Library\bin` 加入系统 PATH，也可以直接验证：

```powershell
pdftoppm -v
```

## 8. 环境变量说明

常用环境变量：

```text
AIDRAMA_SERVER_URL      后台 API 地址
AIDRAMA_CHROME_PATH     Chrome 可执行文件路径
AIDRAMA_FFMPEG_PATH     FFmpeg 可执行文件路径
AIDRAMA_SUBTITLE_PROVIDER  字幕引擎，推荐 fasterWhisper；兼容 openaiWhisper
AIDRAMA_FASTER_WHISPER_PYTHON_PATH  faster-whisper 虚拟环境里的 python.exe 路径
AIDRAMA_WHISPER_PATH    openai-whisper 命令路径，仅作为兼容兜底
AIDRAMA_SOFFICE_PATH    LibreOffice soffice 可执行文件路径
AIDRAMA_PDFTOPPM_PATH   Poppler pdftoppm 可执行文件路径
AIDRAMA_WORK_DIR        客户端工作数据目录，保存下载、转码、合同、更新包和临时文件
AIDRAMA_BROWSER_PROFILE_DIR  媒体号浏览器登录态目录
AIDRAMA_TOKEN_FILE      登录 token 文件路径，体积很小，可选迁移
```

`setx` 设置的是当前 Windows 用户的永久环境变量，不是临时变量。设置后需要关闭并重新打开客户端才会生效。

### C 盘空间不足时迁移数据目录

客户端默认会把数据放在当前用户的 AppData 目录，通常位于 C 盘：

```text
%LOCALAPPDATA%\ai-drama-desktop\work
%LOCALAPPDATA%\ai-drama-desktop\chrome-profiles
```

其中最占空间的是视频下载、转码输出、合同材料和浏览器登录态。建议把工作目录和浏览器目录迁移到空间更大的磁盘，例如 D 盘。

如果电脑允许写系统环境变量，推荐右键 PowerShell 或命令提示符，选择“以管理员身份运行”，执行：

```powershell
setx AIDRAMA_WORK_DIR "D:\ai-drama\ai-drama-desktop\work" /M
setx AIDRAMA_BROWSER_PROFILE_DIR "D:\ai-drama\ai-drama-desktop\chrome-profiles" /M
setx AIDRAMA_TOKEN_FILE "D:\ai-drama\ai-drama-desktop\config\token"
```

其中 `/M` 表示写入系统级环境变量，需要管理员权限。`AIDRAMA_TOKEN_FILE` 体积很小，也可以不设置；如果设置，可以用上面的用户级命令保存到同一套数据目录。

如果不能写系统环境变量，也可以只设置当前用户环境变量：

```powershell
setx AIDRAMA_WORK_DIR "D:\ai-drama\ai-drama-desktop\work"
setx AIDRAMA_BROWSER_PROFILE_DIR "D:\ai-drama\ai-drama-desktop\chrome-profiles"
setx AIDRAMA_TOKEN_FILE "D:\ai-drama\ai-drama-desktop\config\token"
```

设置完成后关闭并重新打开客户端。旧数据如需保留，可手动把下面两个目录内容搬到新的 D 盘目录：

```text
%LOCALAPPDATA%\ai-drama-desktop\work
%LOCALAPPDATA%\ai-drama-desktop\chrome-profiles
```

不建议随意设置 `AIDRAMA_DEVICE_ID`，否则可能影响后台的设备绑定和媒体号权限判断。

## 9. 安装后检查

打开新的 PowerShell，执行：

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --version
C:\Tools\ffmpeg\bin\ffmpeg.exe -version
C:\Tools\ffmpeg\bin\ffprobe.exe -version
C:\AI-Drama\faster-whisper-venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; print('faster-whisper ok')"
node -v
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
C:\Tools\poppler\Library\bin\pdftoppm.exe -v
```

如果没有安装本机字幕识别，可以跳过 faster-whisper 检查。以上命令都能输出版本信息，说明客户端运行依赖基本安装完成。

## 10. 合同功能说明

“合同配置 -> 测试生成 -> 生成合同”只生成 Word `.docx`，不需要 LibreOffice 和 Poppler。

完整发布/分发任务会生成上传用的合同图片，此时需要：

1. LibreOffice 将 `.docx` 转为 `.pdf`
2. Poppler 将 `.pdf` 转为 `.png`

如果完整发布时合同图片生成失败，优先检查：

```powershell
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
C:\Tools\poppler\Library\bin\pdftoppm.exe -v
```

## 11. 普通用户不需要安装的软件

以下软件只在开发、拉代码、打包 Windows 客户端或启用本机 Whisper 字幕识别时需要，普通用户拿到安装包后不一定需要安装：

- Python 3.11+（仅 Whisper 字幕识别或开发打包需要）
- Git
- Inno Setup 6
- 项目源码
- `.venv`

## 12. 开发打包机器额外软件

只有需要从源码构建 Windows 客户端时，才需要安装以下软件。

### Python 3.11+

下载地址：

```text
https://www.python.org/downloads/windows/
```

验证：

```powershell
python --version
```

### Inno Setup 6

用途：生成 Windows 安装包 `.exe`。

下载地址：

```text
https://jrsoftware.org/isinfo.php
```

### Git

用途：拉取和更新代码。

下载地址：

```text
https://git-scm.com/download/win
```

验证：

```powershell
git --version
```

### 构建命令

在开发打包机器上执行：

```powershell
Set-Location E:\IT\ai-drama\desktop
.\scripts\build-package.ps1
```

如果工程不在 `E:\IT\ai-drama`，请替换成实际路径。脚本会打印 `Desktop source root`
和 `Desktop source version`，并在生成安装包前验证打包出的 exe 内部版本，避免安装包显示新版本但客户端仍是旧版本。

只生成便携版、不生成安装包：

```powershell
Set-Location E:\IT\ai-drama\desktop
.\scripts\build-package.ps1 -SkipInstaller
```
