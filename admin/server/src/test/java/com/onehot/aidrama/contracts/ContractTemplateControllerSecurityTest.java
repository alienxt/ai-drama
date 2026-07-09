package com.onehot.aidrama.contracts;

import com.onehot.aidrama.common.security.JwtAuthenticationFilter;
import com.onehot.aidrama.common.security.JwtService;
import com.onehot.aidrama.common.security.SecurityConfig;
import com.onehot.aidrama.logs.ApplicationExceptionLogger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ContractTemplateController.class)
@Import({SecurityConfig.class, JwtAuthenticationFilter.class})
class ContractTemplateControllerSecurityTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ContractTemplateService service;

    @MockBean
    private ContractTemplateStorage storage;

    @MockBean
    private JwtService jwtService;

    @MockBean
    private ApplicationExceptionLogger exceptionLogger;

    @Test
    void desktopTemplateCanBeLoadedWithoutLogin() throws Exception {
        mockMvc.perform(get("/api/desktop/contract-templates")
                        .param("platform", "WECHAT_VIDEO")
                        .param("type", "COST_CONTRACT"))
                .andExpect(status().isOk());
    }

    @Test
    void adminTemplateListStillRequiresLogin() throws Exception {
        mockMvc.perform(get("/api/admin/contract-templates"))
                .andExpect(status().is4xxClientError());
    }
}
