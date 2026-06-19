package com.onehot.aidrama.categories;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DramaCategoryClassifierTest {
    @Test
    void classifiesDramaFromTitleAndSummary() {
        DramaCategoryClassifier classifier = new DramaCategoryClassifier();

        assertThat(classifier.classifyCodes("神医归来，开局抢婚校花老婆", "校花老婆 都市 逆袭"))
                .contains("miracle-doctor", "romance", "counterattack", "urban");
    }
}

