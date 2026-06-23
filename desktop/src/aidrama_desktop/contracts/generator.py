from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from docx import Document


CONTRACT_MEDIA_PLATFORMS = ("WECHAT_VIDEO",)
CONTRACT_TEMPLATE_TYPES = ("cost", "purchase")
CONTRACT_TEMPLATE_TYPE_LABELS = {
    "cost": "成本合同",
    "purchase": "购买合同",
}
CONTRACT_PLATFORM_TEMPLATE_TYPES = {
    "WECHAT_VIDEO": ("cost", "purchase"),
    "TIKTOK": ("purchase",),
    "DOUYIN": ("purchase",),
}


def contract_template_key(platform: str, contract_type: str) -> str:
    return f"{platform.lower()}:{contract_type}"


def required_contract_template_types(platform: str) -> tuple[tuple[str, str], ...]:
    types = CONTRACT_PLATFORM_TEMPLATE_TYPES.get(platform, ("purchase",))
    return tuple((contract_type, CONTRACT_TEMPLATE_TYPE_LABELS[contract_type]) for contract_type in types)


def all_required_contract_templates_configured(templates: dict[str, Path | str | None], platform: str) -> bool:
    for contract_type, _label in required_contract_template_types(platform):
        value = templates.get(contract_template_key(platform, contract_type))
        if not value or not Path(value).exists():
            return False
    return True


@dataclass(frozen=True)
class ContractRenderInput:
    contract_type: str
    drama_title: str
    episode_count: str
    price: str
    buyer: str
    seller: str
    sign_date: str = ""
    episode_minutes: str = ""

    def placeholders(self) -> dict[str, str]:
        return {
            "contractType": self.contract_type,
            "dramaTitle": self.drama_title,
            "episodeCount": self.episode_count,
            "episodeMinutes": self.episode_minutes,
            "price": self.price,
            "buyer": self.buyer,
            "seller": self.seller,
            "date": format_contract_date(self.sign_date),
        }


@dataclass(frozen=True)
class ContractMaterial:
    contract_type: str
    label: str
    docx_path: Path
    image_paths: list[Path]


@dataclass(frozen=True)
class ContractMaterialBundle:
    materials: list[ContractMaterial]

    def metadata(self) -> dict[str, object]:
        result: dict[str, object] = {"contractMaterials": self.materials}
        for material in self.materials:
            if material.contract_type == "purchase":
                result["purchaseContractDocx"] = material.docx_path
                result["purchaseContractImages"] = material.image_paths
                result["buyDramaContractImages"] = material.image_paths
            elif material.contract_type == "cost":
                result["costContractDocx"] = material.docx_path
                result["costContractImages"] = material.image_paths
                result["costConfigReportImages"] = material.image_paths
        return result


def default_contract_templates() -> dict[str, Path | None]:
    return {
        contract_template_key(platform, contract_type): None
        for platform in CONTRACT_MEDIA_PLATFORMS
        for contract_type in CONTRACT_TEMPLATE_TYPES
    }


class ContractConfigStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Path | None]:
        if not self.path.exists():
            return default_contract_templates()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_contract_templates()
        templates = default_contract_templates()
        for key in templates:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                templates[key] = Path(value)
        for legacy_key in CONTRACT_TEMPLATE_TYPES:
            value = data.get(legacy_key)
            migrated_key = contract_template_key("WECHAT_VIDEO", legacy_key)
            if templates.get(migrated_key) is None and isinstance(value, str) and value.strip():
                templates[migrated_key] = Path(value)
        return templates

    def save(self, templates: dict[str, Path | str | None]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, str] = {}
        for key in default_contract_templates():
            value = templates.get(key)
            data[key] = str(value) if value else ""
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_contract_filename(filename: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", filename).strip("_") or "contract"


def copy_contract_template(source: Path, template_dir: Path, name: str) -> Path:
    if source.suffix.lower() != ".docx":
        raise ValueError("请选择 .docx 格式的 Word 模板。")
    if not source.exists():
        raise FileNotFoundError(f"模板不存在：{source}")
    template_dir.mkdir(parents=True, exist_ok=True)
    target = template_dir / f"{safe_contract_filename(name)}.docx"
    shutil.copy2(source, target)
    return target


def build_contract_template_download_path(target_dir: Path, key: str, template: dict[str, object]) -> Path:
    source_name = str(template.get("name") or template.get("fileName") or key)
    file_name = safe_contract_filename(source_name)
    if not file_name.lower().endswith(".docx"):
        file_name = f"{file_name}.docx"
    prefix = safe_contract_filename(key)
    return target_dir / f"{prefix}-{file_name}"


def replace_contract_text(text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return values.get(key, "")

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", replace, text)


def format_contract_date(value: str = "") -> str:
    clean = value.strip()
    if not clean:
        parsed = date.today()
    else:
        normalized = (
            clean.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace(".", "-")
        )
        normalized = re.sub(r"\s+", "", normalized)
        match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
        if not match:
            return clean
        year, month, day = (int(part) for part in match.groups())
        try:
            parsed = date(year, month, day)
        except ValueError:
            return clean
    return f"{parsed.year:04d} 年 {parsed.month:02d} 月 {parsed.day:02d} 日"


def replace_paragraph_text(paragraph, values: dict[str, str]) -> None:
    original = paragraph.text
    replaced = replace_contract_text(original, values)
    if replaced == original:
        return
    for run in paragraph.runs:
        run.text = ""
    if paragraph.runs:
        paragraph.runs[0].text = replaced
    else:
        paragraph.add_run(replaced)


def render_contract_docx(template: Path, output: Path, data: ContractRenderInput) -> Path:
    if not template.exists():
        raise FileNotFoundError(f"请先配置 Word 模板：{template}")
    output.parent.mkdir(parents=True, exist_ok=True)
    document = Document(template)
    values = data.placeholders()
    for paragraph in document.paragraphs:
        replace_paragraph_text(paragraph, values)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_paragraph_text(paragraph, values)
    document.save(output)
    return output


def build_contract_output_path(output_dir: Path, data: ContractRenderInput) -> Path:
    filename = safe_contract_filename(f"{data.contract_type}-{data.drama_title}-{data.sign_date or date.today().isoformat()}")
    return output_dir / f"{filename}.docx"


def render_contract_material_bundle(
    templates: dict[str, Path | str | None],
    platform: str,
    output_dir: Path,
    data_factory: Callable[[str, str], ContractRenderInput],
    image_converter: Callable[[Path, Path, str | None], list[Path]] | None = None,
) -> ContractMaterialBundle:
    if not all_required_contract_templates_configured(templates, platform):
        missing = [
            label
            for contract_type, label in required_contract_template_types(platform)
            if not templates.get(contract_template_key(platform, contract_type))
            or not Path(templates[contract_template_key(platform, contract_type)]).exists()
        ]
        raise RuntimeError(f"请先在合同配置中配置：{'、'.join(missing)}。")

    converter = image_converter or export_contract_docx_images
    materials: list[ContractMaterial] = []
    for contract_type, label in required_contract_template_types(platform):
        template = Path(templates[contract_template_key(platform, contract_type)])
        data = data_factory(contract_type, label)
        docx_path = render_contract_docx(template, build_contract_output_path(output_dir / "docx", data), data)
        image_paths = converter(docx_path, output_dir / "images", safe_contract_filename(f"{contract_type}-{data.drama_title}"))
        materials.append(ContractMaterial(contract_type, label, docx_path, image_paths))
    return ContractMaterialBundle(materials)


def export_contract_docx_images(docx_path: Path, image_dir: Path, image_stem: str | None = None) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    stem = image_stem or docx_path.stem
    try:
        pdf_path = convert_docx_to_pdf(docx_path, image_dir)
    except RuntimeError:
        quicklook = quicklook_docx_to_image(docx_path, image_dir, stem)
        if quicklook:
            return [quicklook]
        raise
    try:
        return convert_pdf_to_pngs(pdf_path, image_dir, stem)
    except RuntimeError:
        quicklook = quicklook_docx_to_image(docx_path, image_dir, stem)
        if quicklook:
            return [quicklook]
        raise


def convert_docx_to_pdf(docx_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    soffice = find_command("soffice", ["/Applications/LibreOffice.app/Contents/MacOS/soffice"])
    if not soffice:
        raise RuntimeError("无法将 Word 合同转换为图片，请先安装 LibreOffice。")
    command = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(docx_path),
    ]
    run_command(command, "Word 合同转 PDF 失败")
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if not pdf_path.exists():
        matches = list(output_dir.glob(f"{docx_path.stem}*.pdf"))
        if matches:
            pdf_path = matches[0]
    if not pdf_path.exists():
        raise RuntimeError("Word 合同转 PDF 后没有找到输出文件。")
    return pdf_path


def convert_pdf_to_pngs(pdf_path: Path, image_dir: Path, image_stem: str) -> list[Path]:
    pdftoppm = find_command("pdftoppm")
    if pdftoppm:
        prefix = image_dir / safe_contract_filename(image_stem)
        run_command([pdftoppm, "-png", str(pdf_path), str(prefix)], "PDF 合同转图片失败")
        images = sorted(image_dir.glob(f"{prefix.name}-*.png"))
        if images:
            return images

    sips = find_command("sips")
    if sips:
        target = image_dir / f"{safe_contract_filename(image_stem)}.png"
        run_command([sips, "-s", "format", "png", str(pdf_path), "--out", str(target)], "PDF 合同转图片失败")
        if target.exists():
            return [target]
    raise RuntimeError("无法将 PDF 合同转换为图片，请安装 poppler(pdftoppm)。")


def quicklook_docx_to_image(docx_path: Path, image_dir: Path, image_stem: str) -> Path | None:
    qlmanage = find_command("qlmanage")
    if not qlmanage:
        return None
    run_command([qlmanage, "-t", "-s", "1800", "-o", str(image_dir), str(docx_path)], "Quick Look 生成合同图片失败")
    generated = image_dir / f"{docx_path.name}.png"
    if not generated.exists():
        return None
    target = image_dir / f"{safe_contract_filename(image_stem)}.png"
    if generated != target:
        if target.exists():
            target.unlink()
        generated.rename(target)
    return target


def find_command(name: str, candidates: list[str] | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates or []:
        if Path(candidate).exists():
            return candidate
    return None


def run_command(command: list[str], failure_message: str) -> None:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"{failure_message}：{detail}" if detail else failure_message)
