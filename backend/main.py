"""
訪問看護 月次報告書 自動作成 API

・PDFアップロード → テキスト抽出 → LLMで3項目要約 → 保存
・重複チェック（利用者名・対象月）
・報告書一覧・取得・更新・削除
"""
import socket
import uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import settings
from pdf_processor import extract_text_from_pdf
from report_generator import summarize_with_llm
from storage import list_reports, get_report, save_report, delete_report, find_duplicate
from extract_info import extract_client_name_and_month, split_bulk_pdf_text

app = FastAPI(title="訪問看護 月次報告書 自動作成")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# アップロード一時保存
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 他端末用の共有URL（LANのIPで組み立て）
SERVER_PORT = 8000


def _get_lan_ip() -> Optional[str]:
    """このPCのLAN用IP（他端末からアクセスできるアドレス）を取得する。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


@app.get("/api/server-info")
async def server_info():
    """他端末で開くとき用の共有URLを返す。同じWi-Fi用（LANのIP）と、外から用（PUBLIC_URL）を返す。"""
    lan_ip = _get_lan_ip()
    share_url = f"http://{lan_ip}:{SERVER_PORT}" if lan_ip else None
    public_url = (settings.public_url or "").strip() or None
    return {"share_url": share_url, "lan_ip": lan_ip, "port": SERVER_PORT, "public_url": public_url}


@app.post("/api/extract-info")
async def extract_info(file: UploadFile = File(...)):
    """PDFから利用者氏名・対象月を読み取り、フォーム用に返す。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルを選択してください")
    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    try:
        contents = await file.read()
        tmp_path.write_bytes(contents)
        text = extract_text_from_pdf(tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    client_name, target_month = extract_client_name_and_month(text)
    return {"client_name": client_name or "", "target_month": target_month or ""}


@app.post("/api/split-bulk-pdf")
async def split_bulk_pdf(file: UploadFile = File(...)):
    """一括印刷PDFを人ごとに分割し、各人の氏名・対象月・テキストを返す。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルを選択してください")
    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    try:
        contents = await file.read()
        tmp_path.write_bytes(contents)
        full_text = extract_text_from_pdf(tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    if not full_text.strip():
        raise HTTPException(status_code=400, detail="PDFからテキストを読み取れませんでした。")
    persons = split_bulk_pdf_text(full_text)
    if not persons:
        raise HTTPException(status_code=400, detail="一括印刷の区切り（利用者氏名）を検出できませんでした。")
    return {"persons": persons, "count": len(persons)}


@app.post("/api/reports/generate")
async def generate_report(
    file: UploadFile = File(...),
    client_name: str = Form(..., description="利用者名"),
    target_month: str = Form(..., description="対象月（例: 2025-03）"),
    other_notes: str = Form("", description="その他（必ず入れたいこと）"),
    overwrite: str = Form("", description="上書きする場合は 1"),
):
    """PDFを1つアップロードし、報告書を生成して保存。既に同利用者・同月の報告があれば重複として返す。overwrite=1 の場合は上書き作成。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルを選択してください")

    dup = find_duplicate(client_name, target_month)
    if dup and (overwrite or "").strip() != "1":
        return {
            "duplicate": True,
            "message": "すでに作られています。既存を開くか、上書きして新しく作成できます。",
            "existing_report": {"id": dup["id"], "client_name": dup["client_name"], "target_month": dup["target_month"]},
            "report": dup,
        }

    # 上書きの場合は既存の report_id を使う
    report_id = dup["id"] if dup and (overwrite or "").strip() == "1" else uuid.uuid4().hex

    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    try:
        contents = await file.read()
        tmp_path.write_bytes(contents)
        text = extract_text_from_pdf(tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="PDFからテキストを読み取れませんでした。スキャンされた画像のみのPDFの場合は、OCR対応の追加が必要です。",
        )

    try:
        content = summarize_with_llm(text, other_notes=other_notes or "")
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    saved = save_report(
        report_id=report_id,
        client_name=client_name,
        target_month=target_month,
        content=content,
        source_files=[file.filename or "upload.pdf"],
        other_notes=other_notes or "",
    )
    return {"duplicate": False, "report": saved}


@app.post("/api/reports/generate-from-text")
async def generate_report_from_text(
    client_name: str = Form(...),
    target_month: str = Form(...),
    text: str = Form(..., description="記録テキスト（一括PDFの1人分など）"),
    other_notes: str = Form(""),
    overwrite: str = Form(""),
):
    """テキストから報告書を生成（一括印刷PDFを人ごとに分けたとき用）。PDFは使わない。"""
    dup = find_duplicate(client_name, target_month)
    if dup and (overwrite or "").strip() != "1":
        return {
            "duplicate": True,
            "message": "すでに作られています。既存を開くか、上書きして新しく作成できます。",
            "existing_report": {"id": dup["id"], "client_name": dup["client_name"], "target_month": dup["target_month"]},
            "report": dup,
        }
    report_id = dup["id"] if dup and (overwrite or "").strip() == "1" else uuid.uuid4().hex
    if not text.strip():
        raise HTTPException(status_code=400, detail="テキストが空です。")
    try:
        content = summarize_with_llm(text, other_notes=other_notes or "")
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    saved = save_report(
        report_id=report_id,
        client_name=client_name,
        target_month=target_month,
        content=content,
        source_files=["一括印刷PDFより"],
        other_notes=other_notes or "",
    )
    return {"duplicate": False, "report": saved}


@app.post("/api/reports/generate-multi")
async def generate_report_multi(
    files: list[UploadFile] = File(...),
    client_name: str = Form(...),
    target_month: str = Form(...),
    other_notes: str = Form(""),
    overwrite: str = Form(""),
):
    """複数PDFをアップロードし、結合して1つの報告書を生成。overwrite=1 で上書き作成。"""
    if not files:
        raise HTTPException(status_code=400, detail="PDFを1つ以上選択してください")

    dup = find_duplicate(client_name, target_month)
    if dup and (overwrite or "").strip() != "1":
        return {
            "duplicate": True,
            "message": "すでに作られています。既存を開くか、上書きして新しく作成できます。",
            "existing_report": {"id": dup["id"], "client_name": dup["client_name"], "target_month": dup["target_month"]},
            "report": dup,
        }

    report_id = dup["id"] if dup and (overwrite or "").strip() == "1" else uuid.uuid4().hex
    all_text = []
    filenames = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            continue
        tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
        try:
            contents = await file.read()
            tmp_path.write_bytes(contents)
            text = extract_text_from_pdf(tmp_path)
            if text.strip():
                all_text.append(text)
                filenames.append(file.filename or "upload.pdf")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    if not all_text:
        raise HTTPException(status_code=400, detail="有効なPDFテキストが取得できませんでした。")

    combined = "\n\n---\n\n".join(all_text)
    content = summarize_with_llm(combined, other_notes=other_notes or "")
    saved = save_report(
        report_id=report_id,
        client_name=client_name,
        target_month=target_month,
        content=content,
        source_files=filenames,
        other_notes=other_notes or "",
    )
    return {"duplicate": False, "report": saved}


@app.get("/api/reports")
def api_list_reports():
    """報告書一覧（店舗内共有：全件）"""
    return {"reports": list_reports()}


@app.get("/api/reports/check-duplicate")
def api_check_duplicate(client_name: str, target_month: str):
    """作成前に重複のみ確認したい場合"""
    dup = find_duplicate(client_name, target_month)
    if dup:
        return {"duplicate": True, "report": dup}
    return {"duplicate": False}


@app.get("/api/reports/{report_id}")
def api_get_report(report_id: str):
    """1件取得"""
    r = get_report(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    return r


@app.put("/api/reports/{report_id}")
async def api_update_report(
    report_id: str,
    client_name: str = Form(None),
    target_month: str = Form(None),
    病状の経過: str = Form(None),
    看護リハビリテーションの内容: str = Form(None),
    家庭での介護の状況: str = Form(None),
    その他: str = Form(None),
):
    """内容を修正して保存"""
    existing = get_report(report_id)
    if not existing:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")

    content = {
        "病状の経過": 病状の経過 if 病状の経過 is not None else existing.get("病状の経過", ""),
        "看護リハビリテーションの内容": 看護リハビリテーションの内容 if 看護リハビリテーションの内容 is not None else existing.get("看護リハビリテーションの内容", ""),
        "家庭での介護の状況": 家庭での介護の状況 if 家庭での介護の状況 is not None else existing.get("家庭での介護の状況", ""),
    }
    other_notes = その他 if その他 is not None else existing.get("その他", "")
    updated = save_report(
        report_id=report_id,
        client_name=client_name or existing["client_name"],
        target_month=target_month or existing["target_month"],
        content=content,
        source_files=existing.get("source_files", []),
        other_notes=other_notes,
    )
    return updated


@app.delete("/api/reports/{report_id}")
def api_delete_report(report_id: str):
    """報告書を削除"""
    if not get_report(report_id):
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    delete_report(report_id)
    return {"ok": True}


# フロントエンドを配信（静的ファイル）
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")
    @app.get("/report/{report_id}")
    def report_page(report_id: str):
        return FileResponse(FRONTEND_DIR / "index.html")
    # トンネルURLなどで /upload や /list 等のパスで開いてもアプリを表示する（SPA用キャッチオール）
    @app.get("/{rest:path}")
    def spa_catch_all(rest: str):
        return FileResponse(FRONTEND_DIR / "index.html")
