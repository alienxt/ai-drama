package com.onehot.aidrama.contracts;

public enum ContractTemplateType {
    COST_CONTRACT("成本合同"),
    PURCHASE_CONTRACT("买剧合同");

    private final String label;

    ContractTemplateType(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
