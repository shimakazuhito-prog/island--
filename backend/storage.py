"""報告書の保存・読み込み（SQLiteデータベース）"""
from pathlib import Path
import json
import re
import sqlite3
from datetime import datetime
from typing import Optional

from config import settings

# テーブル定義
_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    client_name TEXT NOT NULL,
    target_month TEXT NOT NULL,
    byoujou TEXT NOT NULL DEFAULT '',
    riha TEXT NOT NULL DEFAULT '',
    kaigo TEXT NOT NULL DEFAULT '',
    sonohoka TEXT NOT NULL DEFAULT '',
    source_files_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_created_at ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_reports_client_month ON reports(client_name, target_month);
"""


def _db_path() -> Path:
    p = Path(settings.reports_db)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    """DBの1行をAPI用の辞書に変換（キーは従来どおり）"""
    source_files = []
    try:
        source_files = json.loads(row["source_files_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "id": row["id"],
        "client_name": row["client_name"] or "",
        "target_month": row["target_month"] or "",
        "病状の経過": row["byoujou"] or "",
        "看護リハビリテーションの内容": row["riha"] or "",
        "家庭での介護の状況": row["kaigo"] or "",
        "その他": row["sonohoka"] or "",
        "source_files": source_files,
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def _normalize_report_data(data: dict) -> dict:
    """病状の経過にJSON全体が入ってしまった既存データを、3項目に分離して返す（移行データ用）"""
    byoujou = (data.get("病状の経過") or "").strip()
    riha = (data.get("看護リハビリテーションの内容") or "").strip()
    kaigo = (data.get("家庭での介護の状況") or "").strip()
    if not riha and not kaigo and "看護リハビリテーションの内容" in byoujou and "家庭での介護の状況" in byoujou:
        try:
            raw = byoujou
            if not raw.strip().startswith("{"):
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    raw = m.group(0)
            raw = re.sub(r",\s*}", "}", raw)
            raw = re.sub(r",\s*]", "]", raw)
            parsed = json.loads(raw)
            data["病状の経過"] = parsed.get("病状の経過", "")
            data["看護リハビリテーションの内容"] = parsed.get("看護リハビリテーションの内容", "")
            data["家庭での介護の状況"] = parsed.get("家庭での介護の状況", "")
        except (json.JSONDecodeError, TypeError):
            pattern = r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"'
            for m in re.finditer(pattern, byoujou):
                key, value = m.group(1), m.group(2)
                value = value.replace("\\n", "\n").replace('\\"', '"')
                if key == "病状の経過":
                    data["病状の経過"] = value
                elif key == "看護リハビリテーションの内容":
                    data["看護リハビリテーションの内容"] = value
                elif key == "家庭での介護の状況":
                    data["家庭での介護の状況"] = value
    return data


def _migrate_json_to_db(conn: sqlite3.Connection) -> None:
    """既存のJSONファイルをDBに1回だけ取り込む"""
    cur = conn.execute("SELECT COUNT(*) FROM reports")
    if cur.fetchone()[0] > 0:
        return
    dir_path = Path(settings.reports_dir)
    if not dir_path.exists():
        return
    for f in dir_path.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["id"] = f.stem
            data = _normalize_report_data(data)
            conn.execute(
                """INSERT OR IGNORE INTO reports
                   (id, client_name, target_month, byoujou, riha, kaigo, sonohoka, source_files_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("id", ""),
                    data.get("client_name", ""),
                    data.get("target_month", ""),
                    data.get("病状の経過", ""),
                    data.get("看護リハビリテーションの内容", ""),
                    data.get("家庭での介護の状況", ""),
                    data.get("その他", ""),
                    json.dumps(data.get("source_files", []), ensure_ascii=False),
                    data.get("created_at", datetime.now().isoformat()),
                    data.get("updated_at", data.get("created_at", datetime.now().isoformat())),
                ),
            )
        except Exception:
            continue
    conn.commit()


def list_reports() -> list[dict]:
    """保存済み報告書一覧（新しい順）"""
    conn = _get_conn()
    try:
        _migrate_json_to_db(conn)
        cur = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC"
        )
        return [_row_to_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_report(report_id: str) -> Optional[dict]:
    """1件取得"""
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def save_report(
    report_id: str,
    client_name: str,
    target_month: str,
    content: dict[str, str],
    source_files: list[str],
    other_notes: str = "",
) -> dict:
    """報告書を保存（上書き）"""
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT created_at FROM reports WHERE id = ?", (report_id,))
        row = cur.fetchone()
        created_at = row[0] if row else now
        conn.execute(
            """INSERT INTO reports (id, client_name, target_month, byoujou, riha, kaigo, sonohoka, source_files_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 client_name=excluded.client_name,
                 target_month=excluded.target_month,
                 byoujou=excluded.byoujou,
                 riha=excluded.riha,
                 kaigo=excluded.kaigo,
                 sonohoka=excluded.sonohoka,
                 source_files_json=excluded.source_files_json,
                 updated_at=excluded.updated_at""",
            (
                report_id,
                client_name,
                target_month,
                content.get("病状の経過", ""),
                content.get("看護リハビリテーションの内容", ""),
                content.get("家庭での介護の状況", ""),
                other_notes,
                json.dumps(source_files, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": report_id,
        "client_name": client_name,
        "target_month": target_month,
        "病状の経過": content.get("病状の経過", ""),
        "看護リハビリテーションの内容": content.get("看護リハビリテーションの内容", ""),
        "家庭での介護の状況": content.get("家庭での介護の状況", ""),
        "その他": other_notes,
        "source_files": source_files,
        "created_at": created_at,
        "updated_at": now,
    }


def delete_report(report_id: str) -> bool:
    """報告書を削除"""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def find_duplicate(client_name: str, target_month: str, exclude_id: Optional[str] = None) -> Optional[dict]:
    """同一利用者・同一対象月の報告書が既にあるか確認"""
    conn = _get_conn()
    try:
        if exclude_id:
            cur = conn.execute(
                "SELECT * FROM reports WHERE client_name = ? AND target_month = ? AND id != ? LIMIT 1",
                (client_name, target_month, exclude_id),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM reports WHERE client_name = ? AND target_month = ? LIMIT 1",
                (client_name, target_month),
            )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()
