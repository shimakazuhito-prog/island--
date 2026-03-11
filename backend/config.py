"""設定（環境変数でAPIキー等を指定）"""
from pathlib import Path
from pydantic_settings import BaseSettings

# プロジェクト直下の .env も読む（backend/ から起動時）
_root_env = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # LLM要約用（OpenAI API互換 / Ollama / ルールベース）
    openai_api_key: str = ""
    openai_base_url: str = ""  # 空なら OpenAI 本家。Ollama なら http://localhost:11434/v1
    openai_model: str = "gpt-4o-mini"

    # 要約モード: "api" = APIキー使用, "ollama" = ローカルOllama, "rule" = AIなし（キーワードで抜き出し）
    summarize_mode: str = "api"  # api / ollama / rule

    # 報告書保存先（JSON時代の名残・移行用。メインは reports_db）
    reports_dir: str = "./data/reports"

    # 報告書用SQLiteデータベース（1ファイルで完結）
    reports_db: str = "./data/reports.db"

    # 外から開く用URL（./run-tunnel.sh で表示された https://xxxx.loca.lt 等を .env に書くと画面上に表示）
    public_url: str = ""

    class Config:
        env_file = [str(_root_env), ".env"]  # プロジェクト直下 → backend/ の順で読む
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
