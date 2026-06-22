package com.onehot.aidrama.contracts;

import com.onehot.aidrama.media.MediaPlatform;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ContractTemplateServiceTest {
    @Test
    void desktopListsTemplatesByPlatformAndContractType() {
        ContractTemplateRepository repository = mock(ContractTemplateRepository.class);
        ContractTemplate wechat = template(MediaPlatform.WECHAT_VIDEO, ContractTemplateType.COST_CONTRACT);
        when(repository.findByPlatformAndTypeOrderByUploadedAtDesc(
                MediaPlatform.WECHAT_VIDEO,
                ContractTemplateType.COST_CONTRACT
        )).thenReturn(List.of(wechat));
        ContractTemplateService service = new ContractTemplateService(repository);

        List<ContractTemplateDtos.ContractTemplateResponse> templates =
                service.listByPlatformAndType(MediaPlatform.WECHAT_VIDEO, ContractTemplateType.COST_CONTRACT);

        assertThat(templates).singleElement().satisfies(response -> {
            assertThat(response.platform()).isEqualTo(MediaPlatform.WECHAT_VIDEO);
            assertThat(response.type()).isEqualTo(ContractTemplateType.COST_CONTRACT);
        });
    }

    private static ContractTemplate template(MediaPlatform platform, ContractTemplateType type) {
        ContractTemplate template = new ContractTemplate();
        template.setId(platform.name() + "-" + type.name());
        template.setPlatform(platform);
        template.setType(type);
        template.setName("模板");
        template.setFileName("template.docx");
        template.setDownloadUrl("/uploads/template.docx");
        template.setUploadedAt(Instant.now());
        return template;
    }
}
