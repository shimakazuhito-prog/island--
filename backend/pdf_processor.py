"""PDFからテキストを抽出する"""
from pathlib import Path
import fitz  # PyMuPDF


def extract_text_from_pdf(file_path: str | Path) -> str:
    """PDFファイルからテキストを抽出する。スキャンPDFは未対応（OCRは別途検討）。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("PDFファイルを指定してください")

    doc = fitz.open(path)
    parts = []
    try:
        for page in doc:
            text = page.get_text()
            if text.strip():
                parts.append(text.strip())
    finally:
        doc.close()

    return "\n\n".join(parts) if parts else ""
