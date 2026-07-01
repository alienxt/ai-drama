# AI Drama Desktop

桌面端负责所有必须发生在用户本机的动作：打开 Chrome、保存媒体平台登录态、下载短剧素材、调用 FFmpeg 转码、上传到视频号。

## Commands

```bash
aidrama-desktop login admin
aidrama-desktop bind-wechat-video --display-name "主视频号"
aidrama-desktop heartbeat
aidrama-desktop run-once
```

## Environment

- `AIDRAMA_SERVER_URL`: 后端 API 地址，默认 `http://localhost:8080/api`
- `AIDRAMA_DEVICE_ID`: 当前桌面设备 ID
- `AIDRAMA_CHROME_PATH`: Chrome 可执行文件路径
- `AIDRAMA_FFMPEG_PATH`: FFmpeg 路径
- `AIDRAMA_SOFFICE_PATH`: soffice 路径
- `AIDRAMA_WORK_DIR`: 本机工作根目录，默认在系统用户数据目录下
- `AIDRAMA_TOKEN_FILE`: 登录 token 文件，默认在系统用户配置目录下
- `AIDRAMA_BROWSER_PROFILE_DIR`: 媒体平台浏览器登录态目录

## Local directories

桌面端本机目录按用途分开，避免短剧素材、配置和浏览器登录态混在一起：

- 配置目录：保存桌面端 token、临时记住登录信息等本机配置。
- 工作根目录：桌面端运行时数据根目录。
- 短剧目录：`<工作根目录>/dramas`。
- 下载原片目录：`<工作根目录>/dramas/downloads/<dramaId>`。
- 转码成品目录：`<工作根目录>/dramas/processed/<dramaId>`。
- 合同目录：`<工作根目录>/contracts`，保存本地生成的合同文件。
- 临时目录：`<工作根目录>/tmp`。
- 浏览器登录态目录：按平台和媒体号隔离，例如 `<browser-profile-dir>/wechat_video/<mediaAccountId>`。

## Contract templates

桌面端“合同配置”页支持维护成本合同、买剧合同和权利声明 Word 模板。用户选择 `.docx` 后，
桌面端会复制到配置目录的 `contract-templates/`，并在 `contract-templates.json`
里保存模板路径。模板可使用以下占位符：

- `{{agreementNumber}}`: 协议编号，格式为 `HZ-yyyy-MM-随机6位数字`
- `{{dramaTitle}}`: 剧名
- `{{episodeCount}}`: 剧集数量
- `{{episodeMinutes}}`: 总时长，单位分钟
- `{{price}}`: 价格
- `{{halfPrice}}`: 价格的一半
- `{{buyer}}`: 买方或甲方
- `{{seller}}`: 卖方或乙方
- `{{date}}`: 签署日期
- `{{contractType}}`: 合同类型

测试生成的合同会写入合同目录，输出格式为本地 `.docx` 文件，可直接用系统默认
Word 应用打开。模板中的盖章、签字、页眉页脚和排版由用户在 Word 中提前整理。

## Platform Notes

视频号上传已经有稳定的适配器边界，但真实上传按钮和表单选择器必须基于实际登录后的页面继续补齐。抖音和 TikTok 已保留平台接口，后续新增适配器即可。
