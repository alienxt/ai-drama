# macOS 客户端安装文档

本文面向 AI Drama Desktop 的 macOS 新用户。普通用户只需要安装客户端和运行依赖，不需要安装 Python、Git、PyInstaller 或项目源码。

## 1. 必装软件清单

| 软件 | 用途 | 下载地址 | 安装方式 |
| --- | --- | --- | --- |
| AI Drama Desktop | 客户端程序 | 由管理员提供 `.dmg` 安装包 | 拖入 Applications |
| Google Chrome | 登录媒体号、自动打开发布页面、上传视频 | https://www.google.com/chrome/ | 默认安装 |
| FFmpeg | 视频转码、提高码率、添加封面帧 | https://ffmpeg.org/download.html | 推荐 Homebrew 安装 |
| LibreOffice | 将合同 Word `.docx` 转为 PDF | https://www.libreoffice.org/download/ | 默认安装或 Homebrew 安装 |
| Poppler | 将合同 PDF 转为 PNG 图片 | https://poppler.freedesktop.org/ | 推荐 Homebrew 安装 |

Word 或 WPS 不是客户端运行必需软件，但整理合同模板时建议安装一个能打开 `.docx` 的办公软件。

## 2. 安装客户端

打开管理员提供的 DMG 文件：

```text
AI-Drama-Desktop-<version>.dmg
```

安装步骤：

1. 双击打开 `.dmg`。
2. 将 `AI Drama Desktop.app` 拖到：

```text
/Applications
```

3. 从“应用程序”里启动 `AI Drama Desktop`。

如果 macOS 提示“无法验证开发者”或阻止打开：

1. 在 Finder 中进入“应用程序”。
2. 按住 Control 点击 `AI Drama Desktop`。
3. 选择“打开”。
4. 在弹窗中再次选择“打开”。

如果仍被拦截，进入：

```text
系统设置 -> 隐私与安全性
```

在页面底部点击“仍要打开”。

仅在确认安装包来自可信内部渠道时，才使用下面的终端命令解除隔离标记：

```bash
xattr -dr com.apple.quarantine "/Applications/AI Drama Desktop.app"
```

## 3. 安装 Homebrew

macOS 推荐用 Homebrew 安装 FFmpeg 和 Poppler。

Homebrew 官网：

```text
https://brew.sh/
```

安装命令：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装完成后，按终端提示把 Homebrew 加入 shell 环境。验证：

```bash
brew --version
which brew
```

## 4. 安装 Google Chrome

下载地址：

```text
https://www.google.com/chrome/
```

安装步骤：

1. 打开下载地址。
2. 下载 macOS 版本。
3. 打开下载的 `.dmg`。
4. 将 Chrome 拖入 `/Applications`。

默认路径：

```text
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
```

验证：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version
```

也可以用 Homebrew 安装：

```bash
brew install --cask google-chrome
```

## 5. 安装 FFmpeg

用途：视频转码、提高码率、添加封面帧，以及部分视频信息读取。

推荐安装命令：

```bash
brew install ffmpeg
```

验证：

```bash
ffmpeg -version
ffprobe -version
```

Apple Silicon 机器常见路径：

```text
/opt/homebrew/bin/ffmpeg
/opt/homebrew/bin/ffprobe
```

Intel 机器常见路径：

```text
/usr/local/bin/ffmpeg
/usr/local/bin/ffprobe
```

如果从 Finder 双击启动客户端后提示找不到 FFmpeg，设置路径：

```bash
launchctl setenv AIDRAMA_FFMPEG_PATH /opt/homebrew/bin/ffmpeg
```

Intel 机器可改为：

```bash
launchctl setenv AIDRAMA_FFMPEG_PATH /usr/local/bin/ffmpeg
```

设置后需要完全退出并重新打开 `AI Drama Desktop`。

## 6. 安装 LibreOffice

用途：完整发布任务中，将 Word 合同 `.docx` 转成 `.pdf`。macOS 内置 Quick Look 可作为兜底，但安装 LibreOffice 后合同转换更稳定。

下载地址：

```text
https://www.libreoffice.org/download/
```

安装步骤：

1. 打开下载地址。
2. 下载 macOS 版本。
3. 打开下载的 `.dmg`。
4. 将 `LibreOffice.app` 拖入 `/Applications`。

默认路径：

```text
/Applications/LibreOffice.app/Contents/MacOS/soffice
```

验证：

```bash
"/Applications/LibreOffice.app/Contents/MacOS/soffice" --version
```

也可以用 Homebrew 安装：

```bash
brew install --cask libreoffice
```

## 7. 安装 Poppler

用途：完整发布任务中，将合同 PDF 转成 PNG 图片，主要使用 `pdftoppm`。macOS 自带 `sips` 可作为兜底，但安装 Poppler 后多页合同转换更稳定。

推荐安装命令：

```bash
brew install poppler
```

验证：

```bash
pdftoppm -v
```

客户端会查找：

```text
/opt/homebrew/bin/pdftoppm
/usr/local/bin/pdftoppm
```

如果安装在非默认位置，可以设置路径：

```bash
launchctl setenv AIDRAMA_PDFTOPPM_PATH "$(which pdftoppm)"
```

设置后需要完全退出并重新打开客户端。

## 8. 一次性安装常用运行依赖

如果用户已经安装好 Homebrew，可以一次性执行：

```bash
brew install ffmpeg poppler
brew install --cask google-chrome libreoffice
```

如果已经手动安装过 Chrome 或 LibreOffice，不需要重复安装对应 cask。

## 9. 安装后检查

打开新的 Terminal，执行：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version
ffmpeg -version
ffprobe -version
"/Applications/LibreOffice.app/Contents/MacOS/soffice" --version
pdftoppm -v
```

以上命令都能输出版本信息，说明客户端运行依赖基本安装完成。

## 10. 合同功能说明

“合同配置 -> 测试生成 -> 生成合同”只生成 Word `.docx`，不需要 LibreOffice 或 Poppler。

完整发布/分发任务会生成上传用的合同图片。macOS 上的转换优先级大致是：

1. LibreOffice 将 `.docx` 转为 `.pdf`
2. Poppler `pdftoppm` 将 `.pdf` 转为 `.png`
3. macOS 内置 `sips` 作为 PDF 转 PNG 兜底
4. macOS 内置 Quick Look `qlmanage` 可作为 Word 预览图兜底

如果完整发布时合同图片生成失败，优先检查：

```bash
"/Applications/LibreOffice.app/Contents/MacOS/soffice" --version
pdftoppm -v
```

## 11. 常用环境变量

普通用户通常不需要设置环境变量。只有工具安装在非默认位置，或 Finder 启动的客户端找不到工具时才需要。

常用变量：

```text
AIDRAMA_SERVER_URL      后台 API 地址
AIDRAMA_CHROME_PATH     Chrome 可执行文件路径
AIDRAMA_FFMPEG_PATH     FFmpeg 可执行文件路径
AIDRAMA_PDFTOPPM_PATH   Poppler pdftoppm 可执行文件路径
```

设置示例：

```bash
launchctl setenv AIDRAMA_CHROME_PATH "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
launchctl setenv AIDRAMA_FFMPEG_PATH /opt/homebrew/bin/ffmpeg
launchctl setenv AIDRAMA_PDFTOPPM_PATH /opt/homebrew/bin/pdftoppm
```

设置后需要完全退出并重新打开客户端。

## 12. 系统权限提示

首次运行时，macOS 可能会询问以下权限：

- 是否允许打开从互联网下载的应用
- 是否允许访问本地文件或下载目录
- 是否允许 Chrome 打开外部页面
- 如果启用了系统防火墙，是否允许客户端接收本机连接

这些权限用于本机下载、转码、打开 Chrome 和本地代理通信。按实际弹窗选择允许即可。

## 13. 普通用户不需要安装的软件

以下软件只在开发或打包 macOS 客户端时需要，普通用户拿到 DMG 后不需要安装：

- Python 3.11+
- Git
- PyInstaller
- 项目源码
- `.venv`

开发打包命令：

```bash
cd desktop
./scripts/build-package.sh
```
