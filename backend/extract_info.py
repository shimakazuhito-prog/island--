"""PDFテキストから利用者氏名・対象月を抽出する。一括印刷PDFを人ごとに分割する。"""
import re
from typing import Optional


def _normalize_name_for_merge(s: Optional[str]) -> str:
    """同一人物判定用：氏名の前後空白を除き、全角スペースを半角に揃える。"""
    if not s or not s.strip():
        return ""
    t = s.strip()
    t = re.sub(r"\u3000", " ", t)
    return t


def split_bulk_pdf_text(full_text: str) -> list[dict]:
    """
    一括印刷PDFのテキストを「利用者氏名」の出現ごとにブロック分割し、
    氏名・対象月が同じブロックは同一人物として1つにまとめる（PDFが複数枚でも同一人なら結合）。
    返すリストの各要素は {"text": その人の記録テキスト（結合済み）, "client_name": 氏名 or None, "target_month": YYYY-MM or None}
    """
    if not full_text or not full_text.strip():
        return []
    delimiter = re.compile(r"\n\s*(?:利用者氏名|利用者名)\s*\n", re.IGNORECASE)
    parts = delimiter.split(full_text)
    segments = []
    for segment in parts:
        segment = segment.strip()
        if not segment or len(segment) < 50:
            continue
        if not re.match(r"^(利用者氏名|利用者名)\s*\n", segment):
            segment = "利用者氏名\n" + segment
        name, month = extract_client_name_and_month(segment)
        segments.append({
            "text": segment,
            "client_name": name,
            "target_month": month,
        })
    # 氏名・対象月が同じブロックを同一人物とみなして結合する
    key_to_parts: dict[tuple[str, str], list[dict]] = {}
    for s in segments:
        name_key = _normalize_name_for_merge(s["client_name"])
        month_key = (s["target_month"] or "").strip()
        key = (name_key, month_key)
        if key not in key_to_parts:
            key_to_parts[key] = []
        key_to_parts[key].append(s)
    results = []
    for (name_key, month_key), group in key_to_parts.items():
        combined_text = "\n\n---\n\n".join(p["text"] for p in group)
        first = group[0]
        results.append({
            "text": combined_text,
            "client_name": first["client_name"],
            "target_month": first["target_month"] or None,
        })
    return results


def extract_client_name_and_month(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    訪問看護記録のテキストから利用者氏名と対象月（YYYY-MM）を推測する。
    返す値は (利用者氏名, 対象月)。取れない場合は None。
    """
    if not text or not text.strip():
        return None, None

    client_name = _extract_client_name(text)
    target_month = _extract_target_month(text)
    return client_name, target_month


def _extract_client_name(text: str) -> Optional[str]:
    """利用者氏名らしき文字列を抽出。複数候補の場合は最初にマッチしたものを返す。"""
    # 訪問看護・記録書Ⅱ形式: 「利用者氏名」の次の行に氏名（例: 赤尾　綾子（アカオ　アヤコ）様（82歳））
    patterns = [
        r"利用者氏名\s*\n\s*([^\n\r]+)",
        r"利用者名\s*\n\s*([^\n\r]+)",
        r"利用者氏名\s*[：:]\s*([^\n\r]+)",
        r"利用者名\s*[：:]\s*([^\n\r]+)",
        r"氏名\s*[：:]\s*([^\n\r]+)",
        r"名前\s*[：:]\s*([^\n\r]+)",
        r"患者名\s*[：:]\s*([^\n\r]+)",
        r"対象者名\s*[：:]\s*([^\n\r]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            # 「名前（ふりがな）様（年齢）」の形式なら名前部分だけ取る
            if "（" in raw:
                raw = raw.split("（")[0].strip()
            # 全角スペースを半角に
            name = re.sub(r"\u3000", " ", raw)
            if 1 <= len(name) <= 30 and not re.match(r"^[\s\-_・.]+$", name):
                return name
    return None


def _extract_target_month(text: str) -> Optional[str]:
    """テキスト内の日付から対象月 YYYY-MM を推測。訪問日を優先し、なければ他の日付。"""
    # 訪問看護・記録書Ⅱ: 「訪問日時」の次の行が「令和8年2月4日(水)」形式 → 訪問日を優先
    visit = re.search(r"訪問日時\s*\n\s*令和\s*(\d+)年\s*(\d{1,2})月", text)
    if visit:
        r_year, mon = int(visit.group(1)), int(visit.group(2))
        if 1 <= mon <= 12 and 1 <= r_year <= 50:
            return f"{2018 + r_year}-{mon:02d}"
    # その他: 令和X年Y月, 20xx年x月 など（最初にマッチしたもの）
    reiwa = re.search(r"令和\s*(\d+)年\s*(\d{1,2})月", text)
    if reiwa:
        r_year, mon = int(reiwa.group(1)), int(reiwa.group(2))
        if 1 <= mon <= 12 and 1 <= r_year <= 50:
            return f"{2018 + r_year}-{mon:02d}"
    for pat in [
        r"(20\d{2})年\s*(\d{1,2})月",
        r"(20\d{2})[/\-](\d{1,2})[/\-]",
        r"(20\d{2})[/\-](\d{1,2})\b",
    ]:
        m = re.search(pat, text)
        if m:
            month = int(m.group(2))
            if 1 <= month <= 12:
                return f"{m.group(1)}-{month:02d}"
    return None
