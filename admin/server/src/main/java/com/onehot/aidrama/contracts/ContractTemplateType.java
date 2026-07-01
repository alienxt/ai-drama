package com.onehot.aidrama.contracts;

public enum ContractTemplateType {
    COST_CONTRACT("成本合同"),
    PURCHASE_CONTRACT("购买合同"),
    RIGHTS_STATEMENT("权利声明");

    private final String label;

    ContractTemplateType(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
