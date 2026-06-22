from pathlib import Path

from docx import Document

from aidrama_desktop.contracts.generator import (
    ContractConfigStore,
    ContractRenderInput,
    copy_contract_template,
    contract_template_key,
    format_contract_date,
    render_contract_docx,
)


def test_render_contract_docx_replaces_placeholders_in_paragraphs_and_tables(tmp_path):
    template = tmp_path / "template.docx"
    output = tmp_path / "output.docx"
    doc = Document()
    doc.add_paragraph("合同剧名：{{dramaTitle}}")
    doc.add_paragraph("签署日期：{{date}}")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "集数"
    table.cell(0, 1).text = "{{ episodeCount }} 集，共 {{episodeMinutes}} 分钟"
    doc.save(template)

    result = render_contract_docx(
        template,
        output,
        ContractRenderInput(
            contract_type="成本合同",
            drama_title="神医归来",
            episode_count="80",
            episode_minutes="80",
            price="5000",
            buyer="甲方",
            seller="乙方",
            sign_date="2026-06-15",
        ),
    )

    rendered = Document(result)
    assert rendered.paragraphs[0].text == "合同剧名：神医归来"
    assert rendered.paragraphs[1].text == "签署日期：2026 年 06 月 15 日"
    assert rendered.tables[0].cell(0, 1).text == "80 集，共 80 分钟"


def test_format_contract_date_supports_chinese_date_input():
    assert format_contract_date("2026年6月5日") == "2026 年 06 月 05 日"


def test_contract_config_store_round_trips_template_paths(tmp_path):
    store = ContractConfigStore(tmp_path / "contract-templates.json")

    store.save({
        contract_template_key("WECHAT_VIDEO", "cost"): tmp_path / "cost.docx",
        contract_template_key("WECHAT_VIDEO", "purchase"): tmp_path / "purchase.docx",
    })

    assert store.load()[contract_template_key("WECHAT_VIDEO", "cost")] == tmp_path / "cost.docx"
    assert store.load()[contract_template_key("WECHAT_VIDEO", "purchase")] == tmp_path / "purchase.docx"


def test_contract_config_store_migrates_legacy_template_keys(tmp_path):
    store = ContractConfigStore(tmp_path / "contract-templates.json")
    (tmp_path / "contract-templates.json").write_text(
        '{"cost": "/tmp/legacy-cost.docx", "purchase": "/tmp/legacy-purchase.docx"}',
        encoding="utf-8",
    )

    templates = store.load()

    assert templates[contract_template_key("WECHAT_VIDEO", "cost")] == Path("/tmp/legacy-cost.docx")
    assert templates[contract_template_key("WECHAT_VIDEO", "purchase")] == Path("/tmp/legacy-purchase.docx")


def test_copy_contract_template_keeps_docx_and_safe_name(tmp_path):
    source = tmp_path / "用户模板.docx"
    Document().save(source)

    target = copy_contract_template(source, tmp_path / "templates", "买剧/合同")

    assert target.exists()
    assert target.name == "买剧_合同.docx"
