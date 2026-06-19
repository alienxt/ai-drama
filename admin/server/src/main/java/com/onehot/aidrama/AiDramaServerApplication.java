package com.onehot.aidrama;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class AiDramaServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(AiDramaServerApplication.class, args);
    }
}
