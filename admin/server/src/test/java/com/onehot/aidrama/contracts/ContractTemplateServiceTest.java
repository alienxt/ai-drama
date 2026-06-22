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
        when(repository.findByPlatformAndTypeOrderByWeightDescUploadedAtDesc(
                MediaPlatform.WECHAT_VIDEO,
                ContractTemplateType.COST_CONTRACT
        )).thenReturn(List.of(wechat));
        ContractTemplateService service = new ContractTemplateService(repository);

        List<ContractTemplateDtos.ContractTemplateResponse> templates =
                service.listByPlatformAndType(MediaPlatform.WECHAT_VIDEO, ContractTemplateType.COST_CONTRACT);

        assertThat(templates).singleElement().satisfies(response -> {
            assertThat(response.platform()).isEqualTo(MediaPlatform.WECHAT_VIDEO);
            assertThat(response.type()).isEqualTo(ContractTemplateType.COST_CONTRACT);
            assertThat(response.weight()).isEqualTo(10);
        });
    }

    @Test
    void adminCanUpdateTemplateWeight() {
        ContractTemplateRepository repository = mock(ContractTemplateRepository.class);
        ContractTemplate template = template(MediaPlatform.WECHAT_VIDEO, ContractTemplateType.PURCHASE_CONTRACT);
        when(repository.findById("template-1")).thenReturn(java.util.Optional.of(template));
        when(repository.save(template)).thenReturn(template);
        ContractTemplateService service = new ContractTemplateService(repository);

        ContractTemplate updated = service.updateWeight("template-1", 50);

        assertThat(updated.getWeight()).isEqualTo(50);
    }

    private static ContractTemplate template(MediaPlatform platform, ContractTemplateType type) {
        ContractTemplate template = new ContractTemplate();
        template.setId(platform.name() + "-" + type.name());
        template.setPlatform(platform);
        template.setType(type);
        template.setName("模板");
        template.setWeight(10);
        template.setFileName("template.docx");
        template.setDownloadUrl("/uploads/template.docx");
        template.setUploadedAt(Instant.now());
        return template;
    }
}
