package com.onehot.aidrama.logs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.SchedulingConfigurer;
import org.springframework.scheduling.config.ScheduledTaskRegistrar;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.util.ErrorHandler;

@Configuration
public class LoggingSchedulingConfig implements SchedulingConfigurer {
    private static final Logger LOGGER = LoggerFactory.getLogger(LoggingSchedulingConfig.class);

    private final ApplicationExceptionLogger exceptionLogger;

    public LoggingSchedulingConfig(ApplicationExceptionLogger exceptionLogger) {
        this.exceptionLogger = exceptionLogger;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar taskRegistrar) {
        taskRegistrar.setScheduler(loggingTaskScheduler());
    }

    @Bean
    ThreadPoolTaskScheduler loggingTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduling-");
        scheduler.setErrorHandler(scheduledTaskErrorHandler());
        return scheduler;
    }

    @Bean
    ErrorHandler scheduledTaskErrorHandler() {
        return exception -> {
            LOGGER.error("Unexpected error occurred in scheduled task", exception);
            exceptionLogger.write(new ApplicationExceptionLogger.ApplicationExceptionInput(
                    null,
                    "SCHEDULED_TASK",
                    null,
                    null,
                    500,
                    "SCHEDULED_TASK_ERROR",
                    exception.getMessage() == null ? "定时任务异常" : exception.getMessage(),
                    exception,
                    null,
                    null,
                    null,
                    null
            ));
        };
    }
}
