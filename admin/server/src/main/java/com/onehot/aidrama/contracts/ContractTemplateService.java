package com.onehot.aidrama.contracts;

import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import com.onehot.aidrama.common.error.BusinessException;

@Service
public class ContractTemplateService {
    private final ContractTemplateRepository repository;

    public ContractTemplateService(ContractTemplateRepository repository) {
        this.repository = repository;
    }

    public List<ContractTemplateDtos.ContractTemplateResponse> list() {
        return repository.findAll(Sort.by(Sort.Direction.ASC, "type").and(Sort.by(Sort.Direction.DESC, "uploadedAt")))
                .stream()
                .map(ContractTemplateDtos.ContractTemplateResponse::from)
                .toList();
    }

    public List<ContractTemplateDtos.ContractTemplateResponse> listByType(ContractTemplateType type) {
        return repository.findByTypeOrderByUploadedAtDesc(type)
                .stream()
                .filter(template -> template.getDownloadUrl() != null && !template.getDownloadUrl().isBlank())
                .map(ContractTemplateDtos.ContractTemplateResponse::from)
                .toList();
    }

    public ContractTemplate create(ContractTemplateType type, String name, MultipartFile upload, ContractTemplateStorage storage) {
        ContractTemplate template = new ContractTemplate();
        template.setType(type);
        template.setName(normalizeName(name, upload.getOriginalFilename()));
        template = repository.save(template);
        return attachFile(template, storage.store(type, template.getId(), upload));
    }

    public ContractTemplate replaceFile(String id, MultipartFile upload, ContractTemplateStorage storage) {
        ContractTemplate template = get(id);
        return attachFile(template, storage.store(template.getType(), template.getId(), upload));
    }

    public void delete(String id) {
        repository.delete(get(id));
    }

    private ContractTemplate attachFile(ContractTemplate template, ContractTemplateStorage.StoredFile file) {
        template.setFileName(file.fileName());
        template.setFileSize(file.fileSize());
        template.setDownloadUrl(file.downloadUrl());
        template.setUploadedAt(Instant.now());
        return repository.save(template);
    }

    private ContractTemplate get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("CONTRACT_TEMPLATE_NOT_FOUND", "合同模板不存在", HttpStatus.NOT_FOUND));
    }

    private static String normalizeName(String name, String fileName) {
        if (name != null && !name.isBlank()) {
            return name.trim();
        }
        if (fileName == null || fileName.isBlank()) {
            return "未命名模板";
        }
        return fileName.replaceFirst("(?i)\\.docx$", "").trim();
    }
}
