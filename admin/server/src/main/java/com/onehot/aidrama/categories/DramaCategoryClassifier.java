package com.onehot.aidrama.categories;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class DramaCategoryClassifier {
    private final List<Rule> rules = List.of(
            new Rule("miracle-doctor", "神医", "医", "救命"),
            new Rule("romance", "老婆", "夫人", "替嫁", "情深", "宠", "校花", "爱"),
            new Rule("counterattack", "归来", "逆袭", "无敌", "横扫", "崛起", "复仇"),
            new Rule("urban", "都市", "校花", "总裁", "老婆"),
            new Rule("costume", "古代", "仙尊", "科举", "皇", "王爷", "侯府"),
            new Rule("food", "厨", "美食", "厨房"),
            new Rule("sci-fi", "AI", "系统", "未来"),
            new Rule("suspense", "暗卫", "仇", "瞒不住")
    );

    public Set<String> classifyCodes(String title, String summary) {
        String text = ((title == null ? "" : title) + " " + (summary == null ? "" : summary)).toLowerCase(Locale.ROOT);
        Set<String> codes = new LinkedHashSet<>();
        for (Rule rule : rules) {
            if (rule.matches(text)) {
                codes.add(rule.code());
            }
        }
        if (codes.isEmpty()) {
            codes.add("general");
        }
        return codes;
    }

    private record Rule(String code, String... keywords) {
        boolean matches(String text) {
            for (String keyword : keywords) {
                if (text.contains(keyword.toLowerCase(Locale.ROOT))) {
                    return true;
                }
            }
            return false;
        }
    }
}

