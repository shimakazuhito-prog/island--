#!/bin/bash
# サーバー（./run.sh）を別ターミナルで起動したうえで、このスクリプトを実行すると
# インターネットから誰でも開けるURLが表示されます。
# Node.js が入っていれば: npx localtunnel --port 8000

cd "$(dirname "$0")"

echo "=========================================="
echo "  公開用URLを取得します（ポート 8000）"
echo "  事前に別ターミナルで ./run.sh を起動してください。"
echo "=========================================="

if command -v npx &>/dev/null; then
  echo ""
  echo "以下のURLを共有すると、誰でも開けます（同じWi-Fiでなくても可）："
  echo ""
  npx --yes localtunnel --port 8000
else
  echo ""
  echo "Node.js が入っていません。以下のいずれかで公開URLを取得できます。"
  echo ""
  echo "【方法1】Node.js を入れたあと、再度このスクリプトを実行"
  echo "  https://nodejs.org からインストール"
  echo ""
  echo "【方法2】ngrok を使う（https://ngrok.com で無料登録）"
  echo "  ngrok をインストール後: ngrok http 8000"
  echo ""
  exit 1
fi
