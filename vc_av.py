import sounddevice as sd
import numpy as np
import torch
from pyannote.audio import Pipeline
import time

# --- 設定項目 ---
# 1. Hugging Faceのアクセストークン
HF_TOKEN = "YOUR_HUGGINGFACE_TOKEN" 

# 2. オーディオデバイス名 (次のセクションの方法で確認)
# PCの音声を拾うループバックデバイス名
INPUT_DEVICE_NAME = "CABLE Output (VB-Audio Virtual Cable)" 
# 処理後の音声を出す仮想デバイス名
OUTPUT_DEVICE_NAME = "CABLE Input (VB-Audio Virtual Cable)" 

# 3. 音声処理の設定
SAMPLE_RATE = 16000  # pyannote.audioが要求するサンプルレート
CHUNK_SECONDS = 3    # 何秒ごとに処理するか (PCスペックに応じて調整)
CHUNK_SAMPLES = int(CHUNK_SECONDS * SAMPLE_RATE)
TARGET_RMS = 0.08    # 目標とする音の大きさ (0.0 ~ 1.0で調整)
SMOOTHING_FACTOR = 0.2 # 音量変更を滑らかにするための係数

# グローバル変数
pipeline = None
device = None
current_gains = {} # 話者ごとの現在のゲインを保持

def find_device_id(name, kind):
    """デバイス名からIDを検索する"""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if name in dev['name'] and dev[f'max_{kind}_channels'] > 0:
            print(f"✅ {kind}デバイス発見: {dev['name']}")
            return i
    return None

def normalize_loudness(audio_chunk, speaker_id):
    """話者ごとに音量を正規化する"""
    global current_gains

    # 現在の音量(RMS)を計算
    rms = np.sqrt(np.mean(audio_chunk**2))
    if rms < 0.001: # 無音に近い場合は処理しない
        return audio_chunk

    # 目標とするゲインを計算
    target_gain = TARGET_RMS / rms
    
    # 現在のゲインを取得（初回は1.0）
    last_gain = current_gains.get(speaker_id, 1.0)
    
    # ゲインを滑らかに変化させる
    smoothed_gain = last_gain * (1 - SMOOTHING_FACTOR) + target_gain * SMOOTHING_FACTOR
    
    # ゲインが大きくなりすぎないように制限 (クリッピング防止)
    gain_to_apply = min(smoothed_gain, 3.0) 
    
    current_gains[speaker_id] = gain_to_apply
    
    # 音量を調整
    normalized_chunk = audio_chunk * gain_to_apply
    
    # クリッピング防止
    return np.clip(normalized_chunk, -1.0, 1.0)

def audio_callback(indata, outdata, frames, time, status):
    """音声データを受け取り、処理して出力するコールバック関数"""
    if status:
        print(status)

    try:
        # NumPy配列をPyTorchテンソルに変換
        audio_tensor = torch.from_numpy(indata.flatten().astype(np.float32)).to(device)
        audio_data = {"waveform": audio_tensor.unsqueeze(0), "sample_rate": SAMPLE_RATE}

        # 話者ダイアライゼーションを実行
        diarization = pipeline(audio_data)
        
        processed_audio = np.copy(indata.flatten())

        # 話者ごとに処理
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            # print(f"話者 {speaker} が {turn.start:.1f}s から {turn.end:.1f}s まで発言")
            
            start_sample = int(turn.start * SAMPLE_RATE)
            end_sample = int(turn.end * SAMPLE_RATE)
            
            # 範囲外のセグメントは無視
            if start_sample >= len(processed_audio) or end_sample > len(processed_audio):
                continue
                
            speaker_chunk = processed_audio[start_sample:end_sample]

            if speaker_chunk.size > 0:
                normalized_chunk = normalize_loudness(speaker_chunk, speaker)
                processed_audio[start_sample:end_sample] = normalized_chunk
        
        outdata[:] = processed_audio.reshape(-1, 1)

    except Exception as e:
        print(f"エラー発生: {e}")
        outdata.fill(0)


def main():
    """メイン処理"""
    global pipeline, device
    
    print("🚀 初期化を開始します...")
    
    # GPUが利用可能か確認
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print("✅ GPU (CUDA) を利用します。")
    else:
        print("⚠️ GPU (CUDA) が見つかりません。CPUで実行します（処理が遅くなる可能性があります）。")
        device = torch.device("cpu")

    # 話者分類パイプラインをロード
    print("🗣️ 話者分類モデルをロード中...")
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HF_TOKEN
        ).to(device)
        print("✅ モデルのロード完了。")
    except Exception as e:
        print(f"❌ モデルのロードに失敗しました: {e}")
        print("Hugging Faceのアクセストークンが正しいか、ライセンスに同意済みか確認してください。")
        return

    # オーディオデバイスIDを検索
    input_id = find_device_id(INPUT_DEVICE_NAME, 'input')
    output_id = find_device_id(OUTPUT_DEVICE_NAME, 'output')

    if input_id is None or output_id is None:
        print("❌ オーディオデバイスが見つかりませんでした。")
        print("利用可能なデバイス一覧:")
        print(sd.query_devices())
        return

    # 音声ストリームを開始
    print("\n🎧 音声処理を開始します。Ctrl+Cで終了します。")
    try:
        with sd.Stream(
            device=(input_id, output_id),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            blocksize=CHUNK_SAMPLES,
            callback=audio_callback
        ):
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 プログラムを終了します。")
    except Exception as e:
        print(f"ストリームエラー: {e}")

if __name__ == "__main__":
    main()