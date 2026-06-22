from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from docx import Document


CONTRACT_TEMPLATE_KEYS = ("cost", "purchase")


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


def default_contract_templates() -> dict[str, Path | None]:
    return {key: None for key in CONTRACT_TEMPLATE_KEYS}


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
        return templates

    def save(self, templates: dict[str, Path | str | None]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, str] = {}
        for key in CONTRACT_TEMPLATE_KEYS:
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
