# API 设计

## 1. 通用响应

```json
{
  "success": true,
  "data": {},
  "error": null,
  "traceId": "..."
}
```

错误：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数错误",
    "details": {}
  },
  "traceId": "..."
}
```

## 2. 认证

### `POST /api/auth/login`

请求：

```json
{
  "username": "admin",
  "password": "admin123"
}
```

响应：

```json
{
  "token": "...",
  "account": {
    "id": "...",
    "username": "admin",
    "roles": ["ADMIN"]
  }
}
```

## 3. 后台 API

### 用户

- `GET /api/admin/accounts`
- `POST /api/admin/accounts`
- `PATCH /api/admin/accounts/{id}/enabled`
- `POST /api/admin/accounts/{id}/reset-password`

### 短剧类别

- `GET /api/admin/categories`
- `POST /api/admin/categories`
- `PUT /api/admin/categories/{id}`
- `DELETE /api/admin/categories/{id}`

### 系统配置

- `GET /api/admin/configs`
- `PUT /api/admin/configs/{key}`

### 短剧

- `GET /api/admin/dramas`
- `GET /api/admin/dramas/{id}`
- `PUT /api/admin/dramas/{id}`
- `POST /api/admin/dramas/scan-baidu`

### 媒体号

- `GET /api/admin/media-accounts`
- `GET /api/admin/media-accounts/{id}`
- `PUT /api/admin/media-accounts/{id}/policy`
- `POST /api/admin/media-accounts/{id}/verify`

### 分发任务

- `GET /api/admin/distribution-tasks`
- `POST /api/admin/distribution-tasks/{id}/retry`
- `POST /api/admin/distribution-tasks/{id}/cancel`

## 4. 桌面端 API

### 分类读取

- `GET /api/desktop/categories`

### 媒体号绑定

- `POST /api/desktop/media-accounts`
- `PUT /api/desktop/media-accounts/{id}/login-state`
- `PUT /api/desktop/media-accounts/{id}/policy`

### 任务执行

- `POST /api/desktop/devices/heartbeat`
- `POST /api/desktop/tasks/claim`
- `PUT /api/desktop/tasks/{id}/progress`
- `PUT /api/desktop/tasks/{id}/result`
- `GET /api/desktop/dramas/{id}/download-plan`

## 5. 约定

- 所有需要认证的接口都必须带 `Authorization: Bearer <token>`。
- 桌面端任务领取接口需要传 `deviceId`，后端使用短锁避免多个客户端处理同一任务。
- 下载地址短期有效，桌面端按任务实时获取，不长期缓存。

