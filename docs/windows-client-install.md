# Windows 客户端安装文档

本文面向 AI Drama Desktop 的 Windows 使用机器。普通使用者只需要安装“运行客户端需要的软件”，不需要安装 Python、Inno Setup 或 Git。

## 1. 安装客户端

优先使用安装包：

```text
desktop/dist/AI-Drama-Desktop-Setup-0.1.6-windows-x64.exe
```

也可以使用便携版，解压后运行：

```text
desktop/dist/AI Drama Desktop/AI Drama Desktop.exe
```

如果机器上已经安装过旧版本，先关闭旧客户端，再运行新的安装包覆盖安装。

## 2. 运行客户端需要的软件

### Google Chrome

用途：媒体号登录、打开视频号发布页面、自动发布上传。

下载地址：

```text
https://www.google.com/chrome/
```

默认安装即可。若 Chrome 安装在非默认位置，可设置：

```powershell
setx AIDRAMA_CHROME_PATH "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

### FFmpeg

用途：短剧视频下载后的转码、处理。

下载入口：

```text
https://ffmpeg.org/download.html
```

Windows 通常下载预编译包，解压后把 `bin` 目录加入系统 `PATH`，例如：

```text
C:\Tools\ffmpeg\bin
```

验证：

```powershell
ffmpeg -version
```

如果不加入 `PATH`，也可以直接指定可执行文件路径：

```powershell
setx AIDRAMA_FFMPEG_PATH "C:\Tools\ffmpeg\bin\ffmpeg.exe"
```

### LibreOffice

用途：完整发布任务中，将 Word 合同 `.docx` 转成 `.pdf`。

下载地址：

```text
https://www.libreoffice.org/download/
```

默认安装即可。常见路径：

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

验证：

```powershell
soffice --version
```

如果命令不可用，设置：

```powershell
setx AIDRAMA_SOFFICE_PATH "C:\Program Files\LibreOffice\program\soffice.exe"
```

### Poppler

用途：完整发布任务中，将合同 PDF 转成 PNG 图片，主要使用 `pdftoppm`。

Poppler 官方项目入口：

```text
https://poppler.freedesktop.org/
```

Windows 机器可使用常见预编译包：

```text
https://github.com/oschwartz10612/poppler-windows/releases
```

下载后解压，把包含 `pdftoppm.exe` 的 `Library\bin` 目录加入系统 `PATH`，例如：

```text
C:\Tools\poppler\Library\bin
```

验证：

```powershell
pdftoppm -v
```

如果不加入 `PATH`，也可以直接指定可执行文件路径：

```powershell
setx AIDRAMA_PDFTOPPM_PATH "C:\Tools\poppler\Library\bin\pdftoppm.exe"
```

设置后需要重新打开客户端。

### Word 或 WPS

用途：编辑合同模板、添加盖章和签名。

客户端运行不强依赖 Word/WPS，但合同模板整理需要能打开 `.docx` 的办公软件。

## 3. 环境变量说明

常用环境变量：

```text
AIDRAMA_SERVER_URL      后台 API 地址
AIDRAMA_CHROME_PATH     Chrome 可执行文件路径
AIDRAMA_FFMPEG_PATH     FFmpeg 可执行文件路径
AIDRAMA_SOFFICE_PATH    LibreOffice soffice 可执行文件路径
AIDRAMA_PDFTOPPM_PATH   Poppler pdftoppm 可执行文件路径
```

使用 `setx` 设置环境变量后，需要重新打开客户端才会生效。

## 4. 安装后检查

打开新的 PowerShell，执行：

```powershell
ffmpeg -version
soffice --version
pdftoppm -v
```

三条命令都能输出版本信息，说明视频处理和合同图片转换依赖基本就绪。

## 5. 合同功能说明

“合同配置 -> 测试生成 -> 生成合同”只生成 Word `.docx`，不需要 LibreOffice 和 Poppler。

完整发布/分发任务会生成上传用的合同图片，此时需要：

1. LibreOffice 将 `.docx` 转为 `.pdf`
2. Poppler 将 `.pdf` 转为 `.png`

如果完整发布时合同图片生成失败，优先检查：

```powershell
soffice --version
pdftoppm -v
```

## 6. 开发打包机器额外需要的软件

只有需要从源码构建 Windows 客户端时，才需要安装以下软件：

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

## 7. 构建命令

在开发打包机器上执行：

```powershell
cd desktop
.\scripts\build-package.ps1
```

只生成便携版、不生成安装包：

```powershell
cd desktop
.\scripts\build-package.ps1 -SkipInstaller
```
