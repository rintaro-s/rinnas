# 画像のURL
$imageUrl = "https://i1.sndcdn.com/artworks-oCwm1IEje17smF8F-sHKMRQ-t500x500.png"

# デスクトップのパス
$desktopPath = [Environment]::GetFolderPath("Desktop")

# ダウンロード先のファイル名とパス
$downloadPath = Join-Path -Path $desktopPath -ChildPath "Minna-no-Ginko_original.png"

#画像をダウンロード
Write-Host "画像をダウンロードしています..."
try {
    Invoke-WebRequest -Uri $imageUrl -OutFile $downloadPath -ErrorAction Stop
    Write-Host "ダウンロードが完了しました。"
} catch {
    Write-Host "画像のダウンロードに失敗しました。" -ForegroundColor Red
    return
}

# 画像を100個コピー
Write-Host "処理中です"
for ($i = 1; $i -le 500; $i++) {
    # ファイル名にコピー番号を追加
    $copyPath = Join-Path -Path $desktopPath -ChildPath "Minna-no-Ginko_$i.png"
    
    Copy-Item -Path $downloadPath -Destination $copyPath -Force
}

Write-Host "すべての処理が完了しました。デスクトップを確認してください。"
