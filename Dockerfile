FROM maven:3.9.9-eclipse-temurin-21 AS backend
WORKDIR /workspace
COPY admin/server/pom.xml admin/server/pom.xml
RUN mvn -f admin/server/pom.xml dependency:go-offline
COPY admin/server admin/server
RUN mvn -f admin/server/pom.xml -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
RUN mkdir -p /app/uploads
COPY --from=backend /workspace/admin/server/target/ai-drama-server-*.jar /app/ai-drama-server.jar
ENV SERVER_PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/ai-drama-server.jar"]
