from docx import Document

from aidrama_desktop.contracts.generator import (
    ContractConfigStore,
    ContractRenderInput,
    copy_contract_template,
    render_contract_docx,
)


def test_render_contract_docx_replaces_placeholders_in_paragraphs_and_tables(tmp_path):
    template = tmp_path / "template.docx"
    output = tmp_path / "output.docx"
    doc = Document()
    doc.add_paragraph("合同剧名：{{dramaTitle}}")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "集数"
    table.cell(0, 1).text = "{{ episodeCount }} 集"
    doc.save(template)

    result = render_contract_docx(
        template,
        output,
        ContractRenderInput(
            contract_type="成本合同",
            drama_title="神医归来",
            episode_count="80",
            price="5000",
            buyer="甲方",
            seller="乙方",
            sign_date="2026-06-15",
        ),
    )

    rendered = Document(result)
    assert rendered.paragraphs[0].text == "合同剧名：神医归来"
    assert rendered.tables[0].cell(0, 1).text == "80 集"


def test_contract_config_store_round_trips_template_paths(tmp_path):
    store = ContractConfigStore(tmp_path / "contract-templates.json")

    store.save({"cost": tmp_path / "cost.docx", "purchase": tmp_path / "purchase.docx"})

    assert store.load()["cost"] == tmp_path / "cost.docx"
    assert store.load()["purchase"] == tmp_path / "purchase.docx"


def test_copy_contract_template_keeps_docx_and_safe_name(tmp_path):
    source = tmp_path / "用户模板.docx"
    Document().save(source)

    target = copy_contract_template(source, tmp_path / "templates", "买剧/合同")

    assert target.exists()
    assert target.name == "买剧_合同.docx"
