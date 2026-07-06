package com.onehot.aidrama.hongguo;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;
import java.util.Optional;

public interface HongguoDramaCandidateRepository extends MongoRepository<HongguoDramaCandidate, String> {
    Optional<HongguoDramaCandidate> findByProviderAndProviderDramaId(String provider, String providerDramaId);
    List<HongguoDramaCandidate> findByProviderAndCalendarDateOrderByPublishedAtDesc(String provider, String calendarDate);
    List<HongguoDramaCandidate> findTop50ByProviderOrderByCreatedAtDesc(String provider);
    List<HongguoDramaCandidate> findByProviderAndSearchKeywordOrderByPublishedAtDescCreatedAtDesc(String provider, String searchKeyword);
    List<HongguoDramaCandidate> findByProviderAndSearchKeywordAndSearchPageOrderByPublishedAtDescCreatedAtDesc(String provider, String searchKeyword, Integer searchPage);
    List<HongguoDramaCandidate> findByProviderAndCalendarDateAndCalendarPageOrderByPublishedAtDescCreatedAtDesc(String provider, String calendarDate, Integer calendarPage);
    List<HongguoDramaCandidate> findTop50ByProviderOrderByPublishedAtDescCreatedAtDesc(String provider);
}
