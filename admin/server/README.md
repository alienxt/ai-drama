# AI Drama Server

Java 21 + Spring Boot + MongoDB 后端。

## Run

```bash
mvn test
mvn spring-boot:run
```

默认启动管理员：

- 用户名：`admin`
- 密码：`admin123456`

生产环境必须通过环境变量覆盖：

- `AIDRAMA_ADMIN_USERNAME`
- `AIDRAMA_ADMIN_PASSWORD`
- `AIDRAMA_JWT_SECRET`
- `MONGODB_URI`

## API Docs

启动后访问：

- `/swagger-ui`
- `/api-docs`

