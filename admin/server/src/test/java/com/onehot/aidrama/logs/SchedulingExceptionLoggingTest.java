package com.onehot.aidrama.logs;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class SchedulingExceptionLoggingTest {
    @Test
    void scheduledTaskErrorHandlerWritesExceptionLog() {
        ApplicationExceptionLogger logger = mock(ApplicationExceptionLogger.class);
        LoggingSchedulingConfig config = new LoggingSchedulingConfig(logger);
        RuntimeException exception = new RuntimeException("scheduled boom");

        config.scheduledTaskErrorHandler().handleError(exception);

        ArgumentCaptor<ApplicationExceptionLogger.ApplicationExceptionInput> input =
                ArgumentCaptor.forClass(ApplicationExceptionLogger.ApplicationExceptionInput.class);
        verify(logger).write(input.capture());
        assertThat(input.getValue().source()).isEqualTo("SCHEDULED_TASK");
        assertThat(input.getValue().code()).isEqualTo("SCHEDULED_TASK_ERROR");
        assertThat(input.getValue().message()).isEqualTo("scheduled boom");
        assertThat(input.getValue().exception()).isSameAs(exception);
    }
}
