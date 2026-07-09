# Windows 客户端安装文档

本文面向 AI Drama Desktop 的 Windows 使用机器。普通用户只需要安装客户端和运行依赖，不需要安装 Python、Git、Inno Setup 或项目源码。

## 1. 必装软件清单

| 软件 | 用途 | 下载地址 | 安装方式 |
| --- | --- | --- | --- |
| AI Drama Desktop | 客户端程序 | 由管理员提供 `.exe` 安装包 | 双击安装 |
| Google Chrome | 登录媒体号、自动打开发布页面、上传视频 | https://www.google.com/chrome/ | 默认安装 |
| FFmpeg | 视频转码、提高码率、添加封面帧 | https://ffmpeg.org/download.html | 下载 Windows 预编译包后解压 |
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

## 5. 安装 LibreOffice

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

## 6. 安装 Poppler

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

## 7. 环境变量说明

常用环境变量：

```text
AIDRAMA_SERVER_URL      后台 API 地址
AIDRAMA_CHROME_PATH     Chrome 可执行文件路径
AIDRAMA_FFMPEG_PATH     FFmpeg 可执行文件路径
AIDRAMA_SOFFICE_PATH    LibreOffice soffice 可执行文件路径
AIDRAMA_PDFTOPPM_PATH   Poppler pdftoppm 可执行文件路径
```

`setx` 设置的是当前 Windows 用户的永久环境变量，不是临时变量。设置后需要关闭并重新打开客户端才会生效。

## 8. 安装后检查

打开新的 PowerShell，执行：

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --version
C:\Tools\ffmpeg\bin\ffmpeg.exe -version
C:\Tools\ffmpeg\bin\ffprobe.exe -version
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
C:\Tools\poppler\Library\bin\pdftoppm.exe -v
```

以上命令都能输出版本信息，说明客户端运行依赖基本安装完成。

## 9. 合同功能说明

“合同配置 -> 测试生成 -> 生成合同”只生成 Word `.docx`，不需要 LibreOffice 和 Poppler。

完整发布/分发任务会生成上传用的合同图片，此时需要：

1. LibreOffice 将 `.docx` 转为 `.pdf`
2. Poppler 将 `.pdf` 转为 `.png`

如果完整发布时合同图片生成失败，优先检查：

```powershell
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
C:\Tools\poppler\Library\bin\pdftoppm.exe -v
```

## 10. 普通用户不需要安装的软件

以下软件只在开发、拉代码或打包 Windows 客户端时需要，普通用户拿到安装包后不需要安装：

- Python 3.11+
- Git
- Inno Setup 6
- 项目源码
- `.venv`

## 11. 开发打包机器额外软件

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
cd desktop
.\scripts\build-package.ps1
```

只生成便携版、不生成安装包：

```powershell
cd desktop
.\scripts\build-package.ps1 -SkipInstaller
```
