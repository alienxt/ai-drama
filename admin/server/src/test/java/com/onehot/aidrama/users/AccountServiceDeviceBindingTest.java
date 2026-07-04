package com.onehot.aidrama.users;

import com.onehot.aidrama.common.error.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.data.mongodb.core.MongoTemplate;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AccountServiceDeviceBindingTest {
    @Test
    void bindsDesktopUserToFirstLoginDevice() {
        AccountRepository repository = mock(AccountRepository.class);
        AccountService service = new AccountService(repository, mock(PasswordEncoder.class), mock(MongoTemplate.class));
        Account account = new Account();
        account.setRoles(List.of("DESKTOP_USER"));

        service.verifyLoginDevice(account, "device-a");

        assertThat(account.getBoundDeviceId()).isEqualTo("device-a");
        assertThat(account.getLastLoginDeviceId()).isEqualTo("device-a");
        verify(repository).save(account);
    }

    @Test
    void rejectsDesktopUserLoginFromDifferentDevice() {
        AccountService service = new AccountService(mock(AccountRepository.class), mock(PasswordEncoder.class), mock(MongoTemplate.class));
        Account account = new Account();
        account.setRoles(List.of("DESKTOP_USER"));
        account.setBoundDeviceId("device-a");

        assertThatThrownBy(() -> service.verifyLoginDevice(account, "device-b"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("账号已绑定其他设备");
    }

    @Test
    void doesNotRequireDeviceForAdminLogin() {
        AccountService service = new AccountService(mock(AccountRepository.class), mock(PasswordEncoder.class), mock(MongoTemplate.class));
        Account account = new Account();
        account.setRoles(List.of("ADMIN"));

        service.verifyLoginDevice(account, null);

        assertThat(account.getBoundDeviceId()).isNull();
    }

    @Test
    void adminCanBindDesktopUserDevice() {
        AccountRepository repository = mock(AccountRepository.class);
        AccountService service = new AccountService(repository, mock(PasswordEncoder.class), mock(MongoTemplate.class));
        Account account = new Account();
        account.setRoles(List.of("DESKTOP_USER"));
        when(repository.findById("account-1")).thenReturn(Optional.of(account));
        when(repository.save(account)).thenReturn(account);

        AccountDto result = service.bindDevice("account-1", "device-a");

        assertThat(account.getBoundDeviceId()).isEqualTo("device-a");
        assertThat(result.boundDeviceId()).isEqualTo("device-a");
        verify(repository).save(account);
    }

    @Test
    void adminCanClearDesktopUserDeviceBinding() {
        AccountRepository repository = mock(AccountRepository.class);
        AccountService service = new AccountService(repository, mock(PasswordEncoder.class), mock(MongoTemplate.class));
        Account account = new Account();
        account.setRoles(List.of("DESKTOP_USER"));
        account.setBoundDeviceId("device-a");
        account.setLastLoginDeviceId("device-a");
        when(repository.findById("account-1")).thenReturn(Optional.of(account));
        when(repository.save(account)).thenReturn(account);

        AccountDto result = service.clearDeviceBinding("account-1");

        assertThat(account.getBoundDeviceId()).isNull();
        assertThat(account.getLastLoginDeviceId()).isEqualTo("device-a");
        assertThat(result.boundDeviceId()).isNull();
        verify(repository).save(account);
    }

    @Test
    void adminCannotBindDeviceForNonDesktopUser() {
        AccountRepository repository = mock(AccountRepository.class);
        AccountService service = new AccountService(repository, mock(PasswordEncoder.class), mock(MongoTemplate.class));
        Account account = new Account();
        account.setRoles(List.of("ADMIN"));
        when(repository.findById("account-1")).thenReturn(Optional.of(account));

        assertThatThrownBy(() -> service.bindDevice("account-1", "device-a"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("只有桌面端用户可以绑定设备");
    }

    @Test
    void adminCanResetAccountPassword() {
        AccountRepository repository = mock(AccountRepository.class);
        PasswordEncoder passwordEncoder = mock(PasswordEncoder.class);
        AccountService service = new AccountService(repository, passwordEncoder, mock(MongoTemplate.class));
        Account account = new Account();
        account.setUsername("test");
        when(repository.findById("account-1")).thenReturn(Optional.of(account));
        when(passwordEncoder.encode("new-password")).thenReturn("encoded-new-password");
        when(repository.save(account)).thenReturn(account);

        AccountDto result = service.resetPassword("account-1", "new-password");

        assertThat(account.getPasswordHash()).isEqualTo("encoded-new-password");
        assertThat(result.username()).isEqualTo("test");
        verify(passwordEncoder).encode("new-password");
        verify(repository).save(account);
    }
}
