import os
import whisper
from pydub import AudioSegment

def mp3_to_wav(mp3_file, wav_file):
    """
    MP3ファイルをWAV形式に変換
    """
    audio = AudioSegment.from_mp3(mp3_file)
    audio.export(wav_file, format="wav")

def transcribe_audio_with_whisper(wav_file, model_name="base"):
    """
    Whisperを使用して音声を文字起こし
    """
    print(f"Whisperモデル '{model_name}' をロード中...")
    model = whisper.load_model(model_name)  # モデルをロード（例: "base", "small", "medium", "large"）
    print("文字起こしを実行中...")
    result = model.transcribe(wav_file, language="ja")  # 日本語を指定
    return result["text"]

if __name__ == "__main__":
    # 入力MP3ファイルと出力WAVファイルのパス
    mp3_file = "mirai.mp3"  # 入力するMP3ファイル
    wav_file = "output.wav"  # 一時的に作成するWAVファイル

    # MP3をWAVに変換
    print("MP3をWAVに変換中...")
    mp3_to_wav(mp3_file, wav_file)

    # Whisperを使用して音声を文字起こし
    print("Whisperを使用して文字起こしを実行中...")
    transcription = transcribe_audio_with_whisper(wav_file, model_name="large")  # モデル名を指定（例: "base", "small", "medium", "large"）

    # 結果を表示
    print("文字起こし結果:")
    print(transcription)

    # 一時ファイルを削除
    os.remove(wav_file)