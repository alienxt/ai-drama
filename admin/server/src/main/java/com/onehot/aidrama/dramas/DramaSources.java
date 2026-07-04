package com.onehot.aidrama.dramas;

public final class DramaSources {
    public static final String BAIDU_PAN = "BAIDU_PAN";
    public static final String HONGGUO_52API = "HONGGUO_52API";

    private DramaSources() {
    }

    public static String normalize(String source) {
        return source == null || source.isBlank() ? BAIDU_PAN : source;
    }

    public static boolean isHongguo(String source) {
        return HONGGUO_52API.equals(normalize(source));
    }
}
