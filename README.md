# AI Drama Distribution

短剧分发系统，覆盖后台管理、云盘短剧入库、桌面端本地处理、以及媒体号自动发布。

## Workspace

- `admin/server`: Java 21 + Spring Boot + MongoDB 后端，提供后台管理 API、桌面端 API、百度云扫描、分发任务与媒体号管理。
- `admin/frontend`: React + Ant Design 后台管理界面。
- `desktop`: Python 桌面端，负责登录、绑定媒体号、调用本机 Chrome、下载短剧、转码、上传视频号，并为抖音/TK保留平台扩展点。
- `docs`: 产品功能、架构、接口和部署说明。

## Current Foundation

本仓库已初始化为可持续演进的工程骨架：

- 后端按领域拆分：认证、用户、短剧分类、系统配置、短剧、媒体号、分发任务、百度云。
- 后端已接入真实百度云扫描，默认从 `/drama/真人剧/2026` 选择最新日期目录同步短剧，并生成真实下载计划。
- 前端按 feature 组织，内置全局 HTTP 客户端、异常边界、路由布局和 Ant Design 主题入口。
- 桌面端按端口和适配器拆分，浏览器自动化、视频处理、平台发布、任务执行彼此隔离，已支持视频号绑定、类别策略和短剧下载。

## Documentation

- [功能文档](docs/功能文档.md)
- [技术文档](docs/技术文档.md)
- [API 设计](docs/API设计.md)

## Quick Start

后端：

```bash
cd admin/server
mvn test
mvn spring-boot:run
```

默认后台账号：`admin / admin123`。

前端：

```bash
cd admin/frontend
npm install
npm run dev
```

桌面端：

```bash
cd desktop
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
aidrama-desktop login
aidrama-desktop bind-wechat-video
aidrama-desktop agent
aidrama-desktop categories
aidrama-desktop publish
aidrama-desktop download-drama <dramaId>
```

真实同步百度云：

```bash
cd admin/server
mvn spring-boot:run
# 登录后调用 POST /api/admin/dramas/scan-baidu，空 body 会扫描数据库配置的默认根目录
```

## Deploy

后端以 Spring Boot Docker 容器部署，只包含后端服务，不构建也不发布后台前端。
容器默认连接 `mongodb://172.31.39.95:27017/ai_drama`：

```bash
./scripts/deploy-server.sh
```

首次部署会在远端生成 `/opt/ai-drama/server.env`，保存 Mongo 地址、JWT secret
和 bootstrap 管理员配置；后续重部署会复用这个文件。

常用覆盖项：

```bash
REMOTE=root@ai-drama-n1 \
HOST_PORT=8080 \
MONGODB_URI=mongodb://172.31.39.95:27017/ai_drama \
AIDRAMA_JWT_SECRET='replace-with-a-long-secret' \
./scripts/deploy-server.sh
```

查看远程容器状态和日志：

```bash
./scripts/remote-status.sh
```

后台前端独立发布到宿主机 nginx 目录：

```bash
./scripts/deploy-frontend.sh
```

桌面端打包：

```bash
cd desktop
./scripts/build-package.sh       # macOS，输出 dmg
.\scripts\build-package.ps1      # Windows PowerShell，输出 zip
```
