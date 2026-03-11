"""訪問看護記録のテキストから、月次報告書の3項目を要約する"""
import json
import re
from openai import OpenAI, RateLimitError, AuthenticationError, APIStatusError

from config import settings


# 要約のシステムプロンプト（3項目を明確に区別する）
SYSTEM_PROMPT = """あなたは訪問看護の月次報告書を作成する担当者です。記録を読んで、次の3項目を「必ず別々の内容」でまとめてください。

【ボリューム】各項目は必ず3〜5行で書く。記録にないことを捏造（嘘）してはいけないが、記録にある内容を要約して「3〜5行」のボリュームになるよう十分に書く。1〜2行で終わらせず、該当する記述があれば3〜5行にまとめる。

【重要】3項目の意味と書き方：
・病状の経過 ＝ 記録から「利用者の症状・訴え・身体の経過」を漏れなく書く。日々の様子に加え、入院・受診・検査・体調の変化など「いつもと違うこと」があったら必ず入れる。例：吐き気、息苦しさ、動悸、BNP等の数値、食事・排便・内服の状況、入院の有無・時期・理由、受診結果など。看護師が「何をしたか」は書かない。3〜5行でボリュームを出す。
・看護リハビリテーションの内容 ＝ 記録に書いてある「スタッフが実施したこと」をそのまま記載する。清拭、マッサージ、ROM訓練、ストレッチ、歩行訓練、入浴介助、服薬セット、観察など、記録から何をやったかを具体的に書く。症状の説明は書かない。3〜5行でボリュームを出す。
・家庭での介護の状況 ＝ 家族の介護、同居の有無、在宅での過ごし方など。記録に該当内容が少ない場合のみ「特記事項なし」等で短くする。記録に書いてあれば3〜5行で書く。

「病状の経過」と「看護リハビリテーションの内容」を同じ文や同じ内容にしないでください。病状は利用者の状態、リハ内容は記録に基づく実施内容を分けて書いてください。

ユーザーが「その他で必ず入れたいこと」を指定した場合、その内容は3項目のいずれか（病状の経過・看護リハビリの内容・家庭での介護の状況）の該当する項目に含めてください。その他を独立した項目として出力せず、必ず3項目のJSONのみで出力してください。

出力は次のJSON形式のみ。余計な説明は不要。各項目は3〜5行のボリュームで。
{"病状の経過": "3〜5行", "看護リハビリテーションの内容": "3〜5行", "家庭での介護の状況": "3〜5行"}
"""


def summarize_with_llm(raw_text: str, other_notes: str = "") -> dict[str, str]:
    """要約する。other_notes は3項目のいずれかに反映する（その他として独立出力しない）。"""
    mode = (settings.summarize_mode or "api").strip().lower()

    if mode == "rule":
        return _summarize_rule_based(raw_text, other_notes)
    if mode == "ollama":
        return _summarize_ollama(raw_text, other_notes)
    if settings.openai_api_key:
        return _summarize_api(raw_text, other_notes)
    return _summarize_rule_based(raw_text, other_notes)


def _summarize_rule_based(raw_text: str, other_notes: str = "") -> dict[str, str]:
    """AIなし。記録の見出しから該当箇所を抜き出して3項目に振り分ける。other_notes は病状の経過に追記。"""
    # 訪問看護・記録書Ⅱの見出しパターンでブロックを取得（■見出し の次の行から次の■まで）
    blocks = []
    for m in re.finditer(r"■([^\n]+)\n([^\n■]*(?:\n[^\n■]*)*)", raw_text):
        title, body = m.group(1).strip(), m.group(2).strip()
        if not body or len(body) < 3:
            continue
        blocks.append((title, body))

    def pick(keywords: list[str], max_chars: int = 800) -> str:
        parts = []
        for title, body in blocks:
            if any(k in title for k in keywords):
                parts.append(body)
        s = " ".join(parts).replace("\n", " ").strip()
        while "  " in s:
            s = s.replace("  ", " ")
        return s[:max_chars] + ("…" if len(s) > max_chars else "") if s else ""

    # 病状＝観察・バイタル・服薬・医療など／リハ＝リハビリ・ROM・歩行など／介護＝排泄・食事・入浴・環境など
    byoujou = pick(["観察", "バイタル", "病状", "症状", "痛み", "服薬", "医療の実施"])
    riha = pick(["リハビリ", "ROM", "歩行", "訓練", "ストレッチ", "体操", "筋力", "バランス"])
    kaigo = pick(["排泄", "食事", "入浴", "清拭", "環境", "介護", "家族"])

    byoujou = byoujou or "（記録から該当する見出しを検索しましたが、該当箇所が少ないため手動で追記してください。）"
    if other_notes and other_notes.strip():
        byoujou = (byoujou + "\n\n" + other_notes.strip()).strip()
    return {
        "病状の経過": byoujou,
        "看護リハビリテーションの内容": riha or "（同上）",
        "家庭での介護の状況": kaigo or "（同上）",
    }


def _summarize_ollama(raw_text: str, other_notes: str = "") -> dict[str, str]:
    """ローカルOllamaで要約。http://localhost:11434 が起動していること。"""
    base = (settings.openai_base_url or "http://localhost:11434/v1").rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1" if not base.endswith("/") else base + "v1"
    client = OpenAI(api_key="ollama", base_url=base)
    model = settings.openai_model or "llama3.2"
    max_chars = 12000
    if len(raw_text) > max_chars:
        raw_text = raw_text[:max_chars] + "\n\n（以下省略）"
    user_content = raw_text
    if other_notes and other_notes.strip():
        user_content = raw_text + "\n\n【必ず入れたいこと（上記3項目のいずれかに含めること）】\n" + other_notes.strip()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
    except Exception as e:
        raise RuntimeError(
            f"Ollamaに接続できません。ターミナルで「ollama run llama3.2」を実行し、Ollamaを起動してください。（詳細: {e}）"
        ) from e
    content = (response.choices[0].message.content or "").strip()
    return _parse_llm_json_response(content)


def _summarize_api(raw_text: str, other_notes: str = "") -> dict[str, str]:
    """OpenAI互換API（Gemini / Groq / OpenAI 等）で要約。"""
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
    )
    max_chars = 12000
    if len(raw_text) > max_chars:
        raw_text = raw_text[:max_chars] + "\n\n（以下省略）"
    user_content = raw_text
    if other_notes and other_notes.strip():
        user_content = raw_text + "\n\n【必ず入れたいこと（上記3項目のいずれかに含めること）】\n" + other_notes.strip()
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
    except RateLimitError:
        raise RuntimeError(
            "APIの利用上限に達しました。しばらく待ってから再試行するか、.env で SUMMARIZE_MODE=rule にするとAIなしで報告書を作成できます。"
        )
    except AuthenticationError:
        raise RuntimeError(
            "APIキーが無効です。.env の OPENAI_API_KEY を確認するか、SUMMARIZE_MODE=rule でAIなしにできます。"
        )
    except APIStatusError as e:
        raise RuntimeError(
            f"APIエラーが発生しました（{e.status_code}）: {e.message}"
        ) from e
    content = response.choices[0].message.content.strip()
    return _parse_llm_json_response(content)


def _parse_llm_json_response(content: str) -> dict[str, str]:
    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        content = json_match.group(0)
    # 末尾カンマを除いてからパース（LLMがよく付ける）
    content_fixed = re.sub(r",\s*}", "}", content)
    content_fixed = re.sub(r",\s*]", "]", content_fixed)
    try:
        data = json.loads(content_fixed)
    except json.JSONDecodeError:
        # パース失敗時は全文を1項目に入れず、正規表現で3項目を抽出する
        data = _extract_three_fields_from_json_string(content_fixed)
    return {
        "病状の経過": (data.get("病状の経過") or "").strip(),
        "看護リハビリテーションの内容": (data.get("看護リハビリテーションの内容") or "").strip(),
        "家庭での介護の状況": (data.get("家庭での介護の状況") or "").strip(),
    }


def _extract_three_fields_from_json_string(s: str) -> dict[str, str]:
    """JSONとしてパースできなかった文字列から、3項目の値を正規表現で取り出す。"""
    result = {"病状の経過": "", "看護リハビリテーションの内容": "", "家庭での介護の状況": ""}
    # 各キーに対応する "〜" の値を取得（エスケープされた " にも対応）
    pattern = r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"'
    for m in re.finditer(pattern, s):
        key, value = m.group(1), m.group(2)
        value = value.replace("\\n", "\n").replace('\\"', '"')
        if key in result:
            result[key] = value
    return result


def _placeholder_report() -> dict[str, str]:
    """APIキー未設定時用のプレースホルダー"""
    return {
        "病状の経過": "（要約するには .env で SUMMARIZE_MODE=rule（AIなし）または APIキー／Ollama を設定してください。）",
        "看護リハビリテーションの内容": "同上",
        "家庭での介護の状況": "同上",
    }
