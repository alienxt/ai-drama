from pathlib import Path
from zipfile import ZipFile

from docx import Document

from aidrama_desktop.contracts.generator import (
    ContractConfigStore,
    ContractRenderInput,
    all_required_contract_templates_configured,
    build_contract_template_download_path,
    contract_party_key,
    copy_contract_template,
    contract_template_key,
    format_contract_date,
    format_contract_date_compact,
    format_contract_date_no_wrap,
    format_contract_date_short,
    replace_double_date_footer_text,
    normalize_contract_docx_for_rendering,
    normalize_purchase_contract_layout,
    required_contract_template_types,
    render_contract_material_bundle,
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
    assert rendered.paragraphs[1].text == "签署日期：2026\u00a0年\u00a006\u00a0月\u00a015\u00a0日"
    assert rendered.tables[0].cell(0, 1).text == "80 集，共 80 分钟"


def test_format_contract_date_supports_chinese_date_input():
    assert format_contract_date("2026年6月5日") == "2026 年 06 月 05 日"


def test_format_contract_date_compact_removes_render_spacing():
    assert format_contract_date_compact("2026-06-05") == "2026年06月05日"


def test_format_contract_date_short_fits_repeated_footer_date():
    assert format_contract_date_short("2026-06-05") == "2026.06.05"


def test_format_contract_date_no_wrap_keeps_visual_spacing_without_line_breaks():
    assert format_contract_date_no_wrap("2026-06-05") == "2026\u00a0年\u00a006\u00a0月\u00a005\u00a0日"


def test_replace_double_date_footer_text_keeps_chinese_date_format():
    text = "日期：{{date}}                                            日期：{{date}}"

    replaced = replace_double_date_footer_text(text, "2026 年 06 月 23 日")

    assert replaced == "日期：2026 年 06 月 23 日                    日期：2026 年 06 月 23 日"


def test_double_date_paragraph_keeps_chinese_date_format_with_compact_spacing(tmp_path):
    template = tmp_path / "template.docx"
    output = tmp_path / "output.docx"
    doc = Document()
    doc.add_paragraph("日期：{{date}}                                            日期：{{date}}")
    doc.save(template)

    result = render_contract_docx(
        template,
        output,
        ContractRenderInput(
            contract_type="购买合同",
            drama_title="一五折陷阱",
            episode_count="27",
            episode_minutes="30",
            price="1",
            buyer="甲方",
            seller="乙方",
            sign_date="2026-06-23",
        ),
    )

    assert Document(result).paragraphs[0].text == (
        "日期：2026\u00a0年\u00a006\u00a0月\u00a023\u00a0日"
        "                    "
        "日期：2026\u00a0年\u00a006\u00a0月\u00a023\u00a0日"
    )


def test_render_contract_material_bundle_reuses_cached_images(tmp_path):
    templates = {}
    for contract_type in ("cost", "purchase"):
        template = tmp_path / f"{contract_type}.docx"
        doc = Document()
        doc.add_paragraph("{{contractType}} {{dramaTitle}} {{episodeCount}} {{episodeMinutes}} {{price}}")
        doc.save(template)
        templates[contract_template_key("WECHAT_VIDEO", contract_type)] = template

    converter_calls = []

    def fake_converter(docx_path: Path, image_dir: Path, image_stem: str | None):
        converter_calls.append((docx_path, image_stem))
        image_dir.mkdir(parents=True, exist_ok=True)
        image = image_dir / f"{image_stem}.png"
        image.write_bytes(b"png")
        return [image]

    def data_factory(_contract_type: str, label: str) -> ContractRenderInput:
        return ContractRenderInput(
            contract_type=label,
            drama_title="一五折陷阱",
            episode_count="27",
            episode_minutes="30",
            price="1",
            buyer="甲方",
            seller="乙方",
            sign_date="2026-06-23",
        )

    first = render_contract_material_bundle(
        templates,
        "WECHAT_VIDEO",
        tmp_path / "generated" / "task-1",
        data_factory,
        image_converter=fake_converter,
    )
    second = render_contract_material_bundle(
        templates,
        "WECHAT_VIDEO",
        tmp_path / "generated" / "task-1",
        data_factory,
        image_converter=fake_converter,
    )

    assert len(converter_calls) == 2
    assert [material.image_paths for material in second.materials] == [
        material.image_paths for material in first.materials
    ]


def test_render_contract_material_bundle_invalidates_cache_when_data_changes(tmp_path):
    templates = {}
    for contract_type in ("cost", "purchase"):
        template = tmp_path / f"{contract_type}.docx"
        doc = Document()
        doc.add_paragraph("{{price}}")
        doc.save(template)
        templates[contract_template_key("WECHAT_VIDEO", contract_type)] = template

    price = {"value": "1"}
    converter_calls = []

    def fake_converter(docx_path: Path, image_dir: Path, image_stem: str | None):
        converter_calls.append((docx_path, image_stem))
        image_dir.mkdir(parents=True, exist_ok=True)
        image = image_dir / f"{image_stem}.png"
        image.write_bytes(f"png-{len(converter_calls)}".encode("utf-8"))
        return [image]

    def data_factory(_contract_type: str, label: str) -> ContractRenderInput:
        return ContractRenderInput(
            contract_type=label,
            drama_title="一五折陷阱",
            episode_count="27",
            episode_minutes="30",
            price=price["value"],
            buyer="甲方",
            seller="乙方",
            sign_date="2026-06-23",
        )

    render_contract_material_bundle(
        templates,
        "WECHAT_VIDEO",
        tmp_path / "generated" / "task-1",
        data_factory,
        image_converter=fake_converter,
    )
    price["value"] = "2"
    render_contract_material_bundle(
        templates,
        "WECHAT_VIDEO",
        tmp_path / "generated" / "task-1",
        data_factory,
        image_converter=fake_converter,
    )

    assert len(converter_calls) == 4


def test_contract_config_store_round_trips_template_paths(tmp_path):
    store = ContractConfigStore(tmp_path / "contract-templates.json")

    store.save({
        contract_template_key("WECHAT_VIDEO", "cost"): tmp_path / "cost.docx",
        contract_template_key("WECHAT_VIDEO", "purchase"): tmp_path / "purchase.docx",
    })

    assert store.load()[contract_template_key("WECHAT_VIDEO", "cost")] == tmp_path / "cost.docx"
    assert store.load()[contract_template_key("WECHAT_VIDEO", "purchase")] == tmp_path / "purchase.docx"


def test_contract_config_store_round_trips_party_fields(tmp_path):
    store = ContractConfigStore(tmp_path / "contract-templates.json")

    store.save({
        contract_party_key("WECHAT_VIDEO", "buyer"): "甲方公司",
        contract_party_key("WECHAT_VIDEO", "seller"): "乙方公司",
    })

    config = store.load()

    assert config[contract_party_key("WECHAT_VIDEO", "buyer")] == "甲方公司"
    assert config[contract_party_key("WECHAT_VIDEO", "seller")] == "乙方公司"


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


def test_build_contract_template_download_path_uses_selected_directory_and_safe_docx_name(tmp_path):
    target = build_contract_template_download_path(
        tmp_path,
        "wechat_video:purchase",
        {"name": "购买合同/标准版", "fileName": "系统模板"},
    )

    assert target == tmp_path / "wechat_video_purchase-购买合同_标准版.docx"


def test_normalize_contract_docx_for_rendering_keeps_template_fonts(tmp_path):
    docx_path = tmp_path / "render.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:rPr>
          <w:rFonts w:eastAsia="仿宋_GB2312" w:asciiTheme="minorEastAsia" w:hAnsiTheme="minorEastAsia"/>
          <w:spacing w:val="-20"/>
        </w:rPr>
        <w:t>成本配置比例情况报告</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>"""
    with ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", "")

    assert normalize_contract_docx_for_rendering(docx_path)

    with ZipFile(docx_path) as archive:
        updated = archive.read("word/document.xml").decode("utf-8")

    assert 'w:eastAsia="仿宋_GB2312"' in updated
    assert 'w:spacing w:val="0"' in updated
    assert "minorEastAsia" in updated


def test_normalize_purchase_contract_layout_raises_stamp_without_moving_images(tmp_path):
    docx_path = tmp_path / "purchase.docx"
    original_stamp_offset = 247015
    original_seller_stamp_offset = 97155
    document_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    <w:p>
      <w:r>
        <w:drawing>
          <wp:anchor relativeHeight="20" behindDoc="1" allowOverlap="0">
            <wp:positionV relativeFrom="paragraph"><wp:posOffset>{original_stamp_offset}</wp:posOffset></wp:positionV>
            <wp:docPr id="1" name="图片 1" descr="甲方-盖章"/>
          </wp:anchor>
        </w:drawing>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:drawing>
          <wp:anchor relativeHeight="25" behindDoc="1" allowOverlap="0">
            <wp:positionV relativeFrom="paragraph"><wp:posOffset>{original_seller_stamp_offset}</wp:posOffset></wp:positionV>
            <wp:docPr id="3" name="图片 3" descr="乙方"/>
          </wp:anchor>
        </w:drawing>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:drawing>
          <wp:anchor relativeHeight="30" behindDoc="0" allowOverlap="1">
            <wp:positionV relativeFrom="paragraph"><wp:posOffset>276225</wp:posOffset></wp:positionV>
            <wp:docPr id="2" name="图片 2" descr="签名"/>
          </wp:anchor>
        </w:drawing>
      </w:r>
    </w:p>
  </w:body>
</w:document>"""
    with ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", "")

    assert normalize_purchase_contract_layout(docx_path)

    with ZipFile(docx_path) as archive:
        updated = archive.read("word/document.xml").decode("utf-8")

    assert 'descr="甲方-盖章"' in updated
    assert 'behindDoc="0"' in updated
    assert 'allowOverlap="1"' in updated
    assert 'relativeHeight="4126"' in updated
    assert 'relativeHeight="8222"' in updated
    assert f"<wp:posOffset>{original_stamp_offset}</wp:posOffset>" in updated
    assert f"<wp:posOffset>{original_seller_stamp_offset}</wp:posOffset>" in updated
    assert not normalize_purchase_contract_layout(docx_path)
    with ZipFile(docx_path) as archive:
        assert archive.read("word/document.xml").decode("utf-8") == updated


def test_wechat_video_requires_cost_and_purchase_templates(tmp_path):
    cost = tmp_path / "cost.docx"
    purchase = tmp_path / "purchase.docx"
    cost.write_text("cost", encoding="utf-8")
    purchase.write_text("purchase", encoding="utf-8")

    assert required_contract_template_types("WECHAT_VIDEO") == (("cost", "成本合同"), ("purchase", "购买合同"))
    assert not all_required_contract_templates_configured(
        {contract_template_key("WECHAT_VIDEO", "cost"): cost},
        "WECHAT_VIDEO",
    )
    assert all_required_contract_templates_configured(
        {
            contract_template_key("WECHAT_VIDEO", "cost"): cost,
            contract_template_key("WECHAT_VIDEO", "purchase"): purchase,
        },
        "WECHAT_VIDEO",
    )
