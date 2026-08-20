package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.configs.SystemConfigRepository;
import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.dramas.DramaRepository;
import org.junit.jupiter.api.Test;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;

class BaiduDramaScannerCompletenessTest {
    @Test
    void skipsIncompleteDramaDirectoryBeforeLookingUpOrSavingDrama() {
        AtomicBoolean sourceLookupCalled = new AtomicBoolean(false);
        AtomicBoolean saveCalled = new AtomicBoolean(false);
        BaiduDramaScanner scanner = new BaiduDramaScanner(
                baiduPanClientWithIncompleteDrama(),
                dramaRepository(sourceLookupCalled, saveCalled),
                systemConfigService(),
                assetStorage()
        );

        assertThat(scanner.scanDateDirectory("/root/8月18日")).isEmpty();
        assertThat(sourceLookupCalled).isFalse();
        assertThat(saveCalled).isFalse();
    }

    private BaiduPanClient baiduPanClientWithIncompleteDrama() {
        return proxy(BaiduPanClient.class, (proxy, method, args) -> {
            if ("listDirectory".equals(method.getName())) {
                String path = (String) args[0];
                if ("/root/8月18日".equals(path)) {
                    return List.of(new BaiduPanEntry(
                            "/root/8月18日/他的偏爱成光（3集）",
                            "他的偏爱成光（3集）",
                            true,
                            1L,
                            0
                    ));
                }
                if ("/root/8月18日/他的偏爱成光（3集）".equals(path)) {
                    return List.of(
                            new BaiduPanEntry(path + "/简介.txt", "简介.txt", false, 2L, 100),
                            new BaiduPanEntry(path + "/第01集.mp4", "第01集.mp4", false, 3L, 100),
                            new BaiduPanEntry(path + "/第02集.mp4", "第02集.mp4", false, 4L, 100)
                    );
                }
            }
            return defaultValue(method);
        });
    }

    private DramaRepository dramaRepository(AtomicBoolean sourceLookupCalled, AtomicBoolean saveCalled) {
        return proxy(DramaRepository.class, (proxy, method, args) -> {
            if ("findAllBySourcePath".equals(method.getName())) {
                sourceLookupCalled.set(true);
                return List.of();
            }
            if ("save".equals(method.getName())) {
                saveCalled.set(true);
                return args[0];
            }
            return defaultValue(method);
        });
    }

    private SystemConfigService systemConfigService() {
        SystemConfigRepository repository = proxy(SystemConfigRepository.class, (proxy, method, args) -> {
            if ("findByKey".equals(method.getName())) {
                return Optional.empty();
            }
            return defaultValue(method);
        });
        return new SystemConfigService(repository);
    }

    private BaiduAssetStorage assetStorage() {
        return proxy(BaiduAssetStorage.class, (proxy, method, args) -> defaultValue(method));
    }

    private static <T> T proxy(Class<T> type, InvocationHandler handler) {
        return type.cast(Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, (proxy, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                return objectMethodValue(proxy, method, args);
            }
            return handler.invoke(proxy, method, args);
        }));
    }

    private static Object objectMethodValue(Object proxy, Method method, Object[] args) {
        return switch (method.getName()) {
            case "toString" -> proxy.getClass().getInterfaces()[0].getSimpleName() + "Proxy";
            case "hashCode" -> System.identityHashCode(proxy);
            case "equals" -> proxy == args[0];
            default -> null;
        };
    }

    private static Object defaultValue(Method method) {
        Class<?> returnType = method.getReturnType();
        if (returnType == void.class) {
            return null;
        }
        if (returnType == boolean.class) {
            return false;
        }
        if (returnType == int.class || returnType == short.class || returnType == byte.class) {
            return 0;
        }
        if (returnType == long.class) {
            return 0L;
        }
        if (returnType == double.class || returnType == float.class) {
            return 0.0;
        }
        if (Optional.class.isAssignableFrom(returnType)) {
            return Optional.empty();
        }
        if (List.class.isAssignableFrom(returnType)) {
            return List.of();
        }
        return null;
    }
}
