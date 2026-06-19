package com.onehot.aidrama.common.config;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class StaticPageController {
    @GetMapping({
            "/",
            "/login",
            "/accounts",
            "/desktop-users",
            "/categories",
            "/configs",
            "/dramas",
            "/media-accounts",
            "/tasks",
            "/ai-tasks",
            "/desktop-versions",
            "/request-logs",
            "/exception-logs"
    })
    public String forward() {
        return "forward:/index.html";
    }
}
