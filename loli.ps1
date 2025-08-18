# デスクトップの背景に設定する画像のURL
$backgroundUrl = "https://i.ytimg.com/vi/Ci_zad39Uhw/maxresdefault.jpg"

# デスクトップのパス
$desktopPath = [Environment]::GetFolderPath("Desktop")

# 背景画像ダウンロード先のファイル名とパス
$backgroundPath = Join-Path -Path $desktopPath -ChildPath "DesktopBackground.jpg"

#背景画像をダウンロード
Write-Host "背景画像をダウンロードしています..."
try {
    Invoke-WebRequest -Uri $backgroundUrl -OutFile $backgroundPath -ErrorAction Stop
    Write-Host "背景画像のダウンロードが完了しました。"
} catch {
    Write-Host "背景画像のダウンロードに失敗しました。" -ForegroundColor Red
    # スクリプトを終了せずに続行
}

# 画像をデスクトップの背景に設定
Write-Host "デスクトップの背景を設定しています..."
try {
    $code = @'
    using System;
    using System.Runtime.InteropServices;

    public class Wallpaper
    {
        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        private static extern int SystemParametersInfo(int uAction, int uParam, string lpvParam, int fuWinIni);

        public static void Set(string path)
        {
            SystemParametersInfo(20, 0, path, 0x01 | 0x02);
        }
    }
'@

    Add-Type -TypeDefinition $code -Language CSharp
    [Wallpaper]::Set($backgroundPath)
    Write-Host "デスクトップの背景が設定されました。"
} catch {
    Write-Host "デスクトップの背景設定に失敗しました。" -ForegroundColor Red
}

# デスクトップに元の画像をコピーする元のスクリプト
$imageUrl = "https://i1.sndcdn.com/artworks-oCwm1IEje17smF8F-sHKMRQ-t500x500.png"
$downloadPath = Join-Path -Path $desktopPath -ChildPath "ui.png"

Write-Host "元の画像をダウンロードしています..."
try {
    Invoke-WebRequest -Uri $imageUrl -OutFile $downloadPath -ErrorAction Stop
    Write-Host "ダウンロードが完了しました。"
} catch {
    Write-Host "画像のダウンロードに失敗しました。" -ForegroundColor Red
    return
}

# 画像を500個コピー
Write-Host "処理中です..."
for ($i = 1; $i -le 500; $i++) {
    $copyPath = Join-Path -Path $desktopPath -ChildPath "ui_$i.png"
    Copy-Item -Path $downloadPath -Destination $copyPath -Force
}

Write-Host "すべての処理が完了しました。デスクトップを確認してください。画像:https://soundcloud.com/himago-japan/lori-flap , https://www.youtube.com/watch?v=Ci_zad39Uhw"
