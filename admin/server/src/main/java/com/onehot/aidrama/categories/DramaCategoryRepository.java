package com.onehot.aidrama.categories;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;
import java.util.Optional;

public interface DramaCategoryRepository extends MongoRepository<DramaCategory, String> {
    List<DramaCategory> findByEnabledTrueOrderBySortOrderAsc();
    Optional<DramaCategory> findByCode(String code);
}
