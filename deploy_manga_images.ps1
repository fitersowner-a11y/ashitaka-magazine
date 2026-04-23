# =============================================================================
# 初心者ガイド漫画画像の配置スクリプト（v2）
# =============================================================================
# 画像の永続化フロー:
#   1. このスクリプトで beginner-guide/images/ (リポジトリ管理) に配置
#   2. git add & commit & push
#   3. GitHub Actions が build.py を実行し public/beginner-guide/images/ にコピー
#   4. GitHub Pages で公開される
#
# 使い方:
#   1. デスクトップに「manga_src」フォルダを作り、画像を入れる
#   2. PowerShell でリポジトリ直下から実行:
#        .\deploy_manga_images.ps1
#   3. 確認後 git add beginner-guide/images/ && git commit && git push
# =============================================================================

# ----- 設定 -----
$SrcDir  = "$env:USERPROFILE\OneDrive\デスクトップ\manga_src"
# public/ ではなくリポジトリ管理の静的アセットディレクトリへ配置する
$DestBase = "$PSScriptRoot\beginner-guide\images"

# ----- ファイル名マッピング（ソースファイル名 → コピー先の相対パス） -----
# コピー先のサブディレクトリはデータの slug 名に合わせること
$Mapping = @{
    "ChatGPT_Image_2026年4月23日_10_44_30.png"     = @(
        "ep01-reservation-notes\page-01.png",
        "ep01-reservation-notes\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_10_31_56.png"     = @(
        "ep02-reservation-flow\page-01.png",
        "ep02-reservation-flow\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_10_49_34.png"     = @(
        "ep03-manner-basics\page-01.png",
        "ep03-manner-basics\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_11_31_08.png"     = @(
        "ep04-price-guide\page-01.png",
        "ep04-price-guide\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_11_25_30__3_.png" = @(
        "ep05-area-choice\page-01.png",
        "ep05-area-choice\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_11_25_30__2_.png" = @(
        "ep06-shinjuku\page-01.png",
        "ep06-shinjuku\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_11_06_27.png"     = @(
        "ep07-ikebukuro\page-01.png",
        "ep07-ikebukuro\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_10_57_44.png"     = @(
        "ep08-ebisu\page-01.png",
        "ep08-ebisu\cover.png"
    )
    "ChatGPT_Image_2026年4月23日_11_25_30__1_.png" = @(
        "ep09-akiba-shinbashi\page-01.png",
        "ep09-akiba-shinbashi\cover.png"
    )
    # キャラ設定画（series-cover.png はシリーズ表紙として流用）
    "ChatGPT_Image_2026年4月23日_11_25_30__4_.png" = @(
        "characters\series-cover.png",
        "characters\shisho.png",
        "characters\kohai.png"
    )
}

# ----- 実行 -----
Write-Host "=== 初心者ガイド画像配置スクリプト v2 ===" -ForegroundColor Cyan
Write-Host "Source : $SrcDir"
Write-Host "Dest   : $DestBase"
Write-Host "※ public/ ではなくリポジトリ管理フォルダへ配置します" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $SrcDir)) {
    Write-Host "ERROR: ソースフォルダが見つかりません: $SrcDir" -ForegroundColor Red
    Write-Host "デスクトップに 'manga_src' フォルダを作り画像を入れてから再実行してください。" -ForegroundColor Yellow
    exit 1
}

$successCount = 0
$errorCount   = 0

foreach ($srcName in $Mapping.Keys) {
    $srcPath = Join-Path $SrcDir $srcName

    if (-not (Test-Path $srcPath)) {
        Write-Host "[SKIP] ソースファイルなし: $srcName" -ForegroundColor Yellow
        $errorCount++
        continue
    }

    foreach ($destRelative in $Mapping[$srcName]) {
        $destPath = Join-Path $DestBase $destRelative
        $destDir  = Split-Path $destPath -Parent

        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }

        try {
            Copy-Item -Path $srcPath -Destination $destPath -Force
            Write-Host "[OK]   $srcName -> $destRelative" -ForegroundColor Green
            $successCount++
        } catch {
            Write-Host "[FAIL] $srcName -> $destRelative : $_" -ForegroundColor Red
            $errorCount++
        }
    }
}

Write-Host ""
Write-Host "=== 完了 ===" -ForegroundColor Cyan
Write-Host "成功: $successCount / 失敗: $errorCount"
Write-Host ""
Write-Host "次のステップ:" -ForegroundColor Yellow
Write-Host "  1. ローカル確認:"
Write-Host "       python build.py"
Write-Host "       python -m http.server 8000 -d public"
Write-Host "       ブラウザで http://localhost:8000/beginner-guide/ を開く"
Write-Host "  2. 問題なければ git にコミット:"
Write-Host "       git add beginner-guide/images/"
Write-Host "       git commit -m 'feat: 初心者ガイド漫画画像を追加'"
Write-Host "       git push origin main"
Write-Host "  3. GitHub Actions (3-5分) 完了後に本番で確認"
