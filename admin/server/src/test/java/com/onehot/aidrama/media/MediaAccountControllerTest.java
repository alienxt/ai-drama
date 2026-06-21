package com.onehot.aidrama.media;

import com.onehot.aidrama.common.error.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoTemplate;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MediaAccountControllerTest {
    @Test
    void adminCanPauseDistributionForMediaAccount() {
        MediaAccountRepository repository = mock(MediaAccountRepository.class);
        MediaAccount account = new MediaAccount();
        account.setId("media-1");
        account.setStatus(MediaAccountStatus.ACTIVE);
        account.setLoginStateRef("profile.json");
        when(repository.findById("media-1")).thenReturn(Optional.of(account));
        when(repository.save(account)).thenReturn(account);
        MediaAccountController controller = new MediaAccountController(repository, mock(MongoTemplate.class));

        MediaAccount updated = controller.adminUpdateStatus("media-1", new MediaDtos.StatusRequest(MediaAccountStatus.PAUSED)).data();

        assertThat(updated.getStatus()).isEqualTo(MediaAccountStatus.PAUSED);
    }

    @Test
    void adminCannotEnableMediaAccountWithoutLoginState() {
        MediaAccountRepository repository = mock(MediaAccountRepository.class);
        MediaAccount account = new MediaAccount();
        account.setId("media-1");
        account.setStatus(MediaAccountStatus.PAUSED);
        when(repository.findById("media-1")).thenReturn(Optional.of(account));
        MediaAccountController controller = new MediaAccountController(repository, mock(MongoTemplate.class));

        assertThatThrownBy(() -> controller.adminUpdateStatus("media-1", new MediaDtos.StatusRequest(MediaAccountStatus.ACTIVE)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("启用前请先保存登录信息");
    }

    @Test
    void adminCanDeleteMediaAccount() {
        MediaAccountRepository repository = mock(MediaAccountRepository.class);
        MediaAccountController controller = new MediaAccountController(repository, mock(MongoTemplate.class));

        controller.adminDelete("media-1");

        verify(repository).deleteById("media-1");
    }
}
