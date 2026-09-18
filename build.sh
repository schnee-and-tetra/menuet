#!/bin/bash
set -e

VERSION="1.0.0"

# AppDirをクリーンな状態にする
rm -rf AppDir
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/menuet
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps

# Pythonパッケージ本体を usr/share/menuet にコピー
cp -r menuet/* AppDir/usr/share/menuet/

# プロジェクトルート直下の mo フォルダを配置
if [ -d "mo" ]; then
    cp -r mo AppDir/usr/
fi

# assets/ の中身をコピー
mkdir -p AppDir/usr/share/menuet/assets
cp -r assets/* AppDir/usr/share/menuet/assets/

# デスクトップファイルとアイコンを適切な場所に配置
cp menuet.png AppDir/usr/share/icons/hicolor/256x256/apps/
cp menuet.png AppDir/
cp menuet.desktop AppDir/usr/share/applications/
cp menuet.desktop AppDir/

# 起動用スクリプトを usr/bin に配置して実行権限を付与
cp bin/menuet AppDir/usr/bin/
chmod +x AppDir/usr/bin/menuet
cat << 'EOF' > AppDir/AppRun
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PYTHONPATH="$HERE/usr/share/menuet:$PYTHONPATH"
exec python3 "$HERE/usr/bin/menuet"
EOF
chmod +x AppDir/AppRun


echo "AppImage を生成します..."
# appimagetool がシステムにインストールされているかチェック
if command -v appimagetool &> /dev/null; then
    # 既存のAppImage（同名ファイル）があれば削除しておく
    rm -f *.AppImage

    # 環境変数を指定して AppImage を作成
    VERSION="$VERSION" ARCH=x86_64 appimagetool AppDir
    echo "✅ AppImage の作成が完了しました！"
else
    echo "❌ エラー: 'appimagetool' コマンドが見つかりません。"
    exit 1
fi