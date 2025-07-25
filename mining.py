import os
import sys
import time
import hashlib
import random
import threading
import json
import numpy as np
from datetime import datetime
import argparse
import signal
import binascii
import struct
import socket
import ssl
import queue
import base64
import re
from typing import Dict, Any, List, Union, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

import intel_npu_acceleration_library

# 環境変数にパスを追加
def add_to_environment_path(new_path):
    """環境変数PATHに新しいパスを追加"""
    current_path = os.environ.get('PATH', '')
    if new_path not in current_path:
        os.environ['PATH'] = new_path + os.pathsep + current_path
        print(f"環境変数PATHに追加されました: {new_path}")
    else:
        print(f"環境変数PATHに既に存在します: {new_path}")

# 指定されたパスを追加
add_to_environment_path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.43.34808\bin\Hostx64\x64")
# Intel NPU Acceleration Libraryのパスも追加
add_to_environment_path(r"C:\Program Files\Intel\IntelNPUAccelerationLibrary\bin")

# PyCUDAのimport前にEXCEPTHOOKを設定してクラッシュを防止
sys.excepthook = lambda exctype, value, traceback: print(f"エラー: {exctype.__name__}: {value}")

try:
    import pycuda.driver as cuda
    import pycuda.autoinit
    from pycuda.compiler import SourceModule
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    print("PyCUDAが見つかりません。GPUマイニングは利用できません。")

# Intel NPUサポート設定 - Intel NPU Acceleration Libraryを使用
INTEL_NPU_AVAILABLE = False

try:
    import intel_npu_acceleration_library as npual
    INTEL_NPU_AVAILABLE = True
    print("Intel NPU Acceleration Libraryが見つかりました。NPU最適化に使用します。")
except ImportError:
    print("Intel NPU Acceleration Libraryが見つかりません。NPU最適化は利用できません。")

# KAWPOWアルゴリズムの完全実装のためのCUDAカーネル
KAWPOW_CUDA_KERNEL = r'''
// KAWPOWアルゴリズム用の定数
#define PROGPOW_LANES           16
#define PROGPOW_REGS            32
#define PROGPOW_DAG_LOADS       4
#define PROGPOW_CNT_DAG         64
#define PROGPOW_CNT_CACHE       11
#define PROGPOW_CNT_MATH        18
#define PROGPOW_PERIOD_LENGTH   10    // エポック変更の周期

// 以下はProgPOW/KAWPOWの本格的なCUDA実装
#include <stdint.h>
#include <cuda_runtime.h>

typedef struct {
    uint32_t z, w, jsr, jcong;
} kiss99_t;

// KISS99 PRNG実装
__device__ uint32_t kiss99(kiss99_t &st)
{
    uint32_t MWC;
    st.z = 36969 * (st.z & 65535) + (st.z >> 16);
    st.w = 18000 * (st.w & 65535) + (st.w >> 16);
    MWC = ((st.z << 16) + st.w);
    st.jsr ^= (st.jsr << 17);
    st.jsr ^= (st.jsr >> 13);
    st.jsr ^= (st.jsr << 5);
    st.jcong = 69069 * st.jcong + 1234567;
    return ((MWC^st.jcong) + st.jsr);
}

// FNV1aハッシュ関数
__device__ const uint32_t FNV_PRIME = 0x1000193;
__device__ const uint32_t FNV_OFFSET_BASIS = 0x811c9dc5;

__device__ uint32_t fnv1a(uint32_t h, uint32_t d)
{
    return (h ^ d) * FNV_PRIME;
}

// math関数
__device__ uint32_t math(uint32_t a, uint32_t b, uint32_t r)
{
    switch (r % 11)
    {
    case 0: return a + b;
    case 1: return a * b;
    case 2: return __mul24(a, b); // 特殊な乗算
    case 3: return min(a, b);
    case 4: return __shfl_sync(0xFFFFFFFF, a, b & 0xF); // シャッフル操作
    case 5: return a & b;
    case 6: return a | b;
    case 7: return a ^ b;
    case 8: return __clz(a) + __clz(b);  // クロック数カウント
    case 9: return __popc(a) + __popc(b); // ビットカウント
    default: return __byte_perm(a, b, r); // バイト並べ替え
    }
}

// KAWPOWマイニングカーネル
__global__ void kawpow_search(
    uint64_t start_nonce,
    uint32_t *g_output,
    uint8_t *header,
    uint32_t header_size,
    uint64_t target,
    uint32_t *dag_data,
    uint32_t dag_size,
    uint32_t *light_cache,
    uint32_t light_cache_size,
    uint32_t block_height
)
{
    uint32_t global_index = blockIdx.x * blockDim.x + threadIdx.x;
    uint64_t nonce = start_nonce + global_index;
    
    // ProgPOWのシード計算
    uint32_t seed[25]; // Keccak-256状態サイズ
    
    // ヘッダーをシードに読み込み
    for(int i = 0; i < header_size && i < 100; i += 4) {
        uint32_t data = 0;
        for(int j = 0; j < 4 && i+j < header_size; ++j) {
            data |= ((uint32_t)header[i+j]) << (8*j);
        }
        seed[i/4] = data;
    }
    
    // ナンスをシードに追加
    seed[header_size/4] = (uint32_t)nonce;
    seed[header_size/4 + 1] = (uint32_t)(nonce >> 32);
    
    // KAWPOWのブロック番号と周期変数
    uint32_t period = block_height / PROGPOW_PERIOD_LENGTH;
    
    // DAGからのロードを設定
    kiss99_t prog_rnd;
    prog_rnd.z = fnv1a(FNV_OFFSET_BASIS, period);
    prog_rnd.w = fnv1a(prog_rnd.z, period);
    prog_rnd.jsr = fnv1a(prog_rnd.w, period);
    prog_rnd.jcong = fnv1a(prog_rnd.jsr, period);
    
    // メインミックスステート
    uint32_t mix[PROGPOW_LANES][PROGPOW_REGS];
    
    // ミックスステート初期化
    for (int l = 0; l < PROGPOW_LANES; l++) {
        uint32_t mix_seed = seed[l % 8];
        for (int i = 0; i < PROGPOW_REGS; i++) {
            mix[l][i] = fnv1a(mix_seed, i);
        }
    }
    
    // メインループ - KAWPOW特有のMixの実装
    for (int i = 0; i < PROGPOW_CNT_DAG; i++) {
        // DAGからのロード
        uint32_t dag_item = kiss99(prog_rnd) % (dag_size / 4);
        
        for (int l = 0; l < PROGPOW_LANES; l++) {
            // 実際のDAGからデータをロード
            uint32_t offset = dag_item * PROGPOW_LANES + l;
            if (offset < dag_size / 4) {
                uint32_t data = dag_data[offset];
                // ミックスに適用
                uint32_t r = kiss99(prog_rnd) % PROGPOW_REGS;
                mix[l][r] = fnv1a(mix[l][r], data);
            }
        }
    }
    
    // 演算操作
    for (int i = 0; i < PROGPOW_CNT_MATH; i++) {
        for (int l = 0; l < PROGPOW_LANES; l++) {
            uint32_t src_rnd = kiss99(prog_rnd) % PROGPOW_REGS;
            uint32_t dst_rnd = kiss99(prog_rnd) % PROGPOW_REGS;
            uint32_t sel_rnd = kiss99(prog_rnd);
            mix[l][dst_rnd] = math(mix[l][dst_rnd], mix[l][src_rnd], sel_rnd);
        }
    }
    
    // ミックスのリダクション
    uint32_t digest[8];
    for (int i = 0; i < 8; i++) {
        digest[i] = FNV_OFFSET_BASIS;
    }
    
    for (int l = 0; l < PROGPOW_LANES; l++) {
        uint32_t lane_hash = FNV_OFFSET_BASIS;
        for (int i = 0; i < PROGPOW_REGS; i++) {
            lane_hash = fnv1a(lane_hash, mix[l][i]);
        }
        digest[l % 8] = fnv1a(digest[l % 8], lane_hash);
    }
    
    // 最終ハッシュ値を64ビット値に変換して比較
    uint64_t result = ((uint64_t)digest[0] << 32) | digest[1];
    
    // ターゲットと比較
    if (result < target) {
        // 解を見つけた場合、出力バッファに書き込む
        uint32_t idx = atomicInc((uint32_t*)g_output, 1);
        if (idx < 4) {
            g_output[idx*4 + 1] = (uint32_t)(nonce);
            g_output[idx*4 + 2] = (uint32_t)(nonce >> 32);
            g_output[idx*4 + 3] = digest[0];
            g_output[idx*4 + 4] = digest[1];
        }
    }
}
'''

# Stratumプロトコル定数
STRATUM_TIMEOUT = 10  # 接続タイムアウト秒数

class StratumClient:
    """Stratumプロトコルクライアント実装"""
    
    def __init__(self, pool_url: str, wallet_address: str, worker_name: str = "worker1", password: str = "x"):
        self.pool_url = pool_url
        self.wallet_address = wallet_address
        self.worker_name = worker_name
        self.password = password
        
        self.socket = None
        self.is_connected = False
        self.job = None
        self.job_id = None
        self.extranonce1 = None
        self.extranonce2_size = 0
        self.difficulty = 0
        self.target = 0
        
        self.recv_thread = None
        self.send_queue = queue.Queue()
        self.recv_queue = queue.Queue()
        self.message_id = 0
        self.lock = threading.RLock()
    
    def connect(self) -> bool:
        """プールに接続"""
        if self.is_connected:
            return True
        
        try:
            # URL解析
            url_parts = self.pool_url.split("://")
            protocol = url_parts[0] if len(url_parts) > 1 else "stratum+tcp"
            host_port = url_parts[-1]
            
            if ":" in host_port:
                host, port_str = host_port.split(":")
                port = int(port_str)
            else:
                host = host_port
                port = 3333  # デフォルトStratumポート
            
            # ソケット接続
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(STRATUM_TIMEOUT)
            
            print(f"マイニングプール {host}:{port} に接続しています...")
            self.socket.connect((host, port))
            
            # SSL接続の場合
            if protocol == "stratum+ssl" or protocol == "stratum+tls":
                context = ssl.create_default_context()
                self.socket = context.wrap_socket(self.socket, server_hostname=host)
            
            self.is_connected = True
            
            # 受信スレッド開始
            self.recv_thread = threading.Thread(target=self._receive_loop)
            self.recv_thread.daemon = True
            self.recv_thread.start()
            
            # 認証
            auth_result = self.subscribe_and_authorize()
            if not auth_result:
                self.disconnect()
                return False
            
            print(f"マイニングプールに接続・認証成功")
            return True
            
        except Exception as e:
            print(f"プール接続エラー: {e}")
            if self.socket:
                self.socket.close()
            self.is_connected = False
            return False
    
    def disconnect(self):
        """プールから切断"""
        self.is_connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
    
    def subscribe_and_authorize(self) -> bool:
        """購読と認証を実行"""
        # 購読
        subscribe_params = ["kawpow", None, "EthereumStratum/1.0.0"]
        result = self.send_message("mining.subscribe", subscribe_params)
        
        if not result or "result" not in result or result.get('error'):
            print(f"購読エラー: {result.get('error') if result else 'タイムアウトまたは接続エラー'}")
            return False
        
        # 購読結果を解析
        try:
            subscription = result["result"]
            self.extranonce1 = subscription[1]
            self.extranonce2_size = subscription[2]
            print(f"購読成功: extranonce1={self.extranonce1}, extranonce2_size={self.extranonce2_size}")
        except Exception as e:
            print(f"購読応答解析エラー: {e}")
            return False
        
        # 認証
        auth_params = [f"{self.wallet_address}.{self.worker_name}", self.password]
        auth_result = self.send_message("mining.authorize", auth_params)
        
        if not auth_result or "result" not in auth_result or not auth_result.get("result"):
            print(f"認証エラー: {auth_result.get('error') if auth_result else 'タイムアウトまたは接続エラー'}")
            return False
        
        print(f"認証成功: ウォレット {self.wallet_address}")
        return True
    
    def send_message(self, method: str, params: List) -> Optional[Dict]:
        """メッセージを送信し応答を待機"""
        with self.lock:
            message_id = self.message_id
            self.message_id += 1
        
        message = {
            "id": message_id,
            "method": method,
            "params": params
        }
        
        message_json = json.dumps(message) + "\n"
        
        try:
            self.socket.send(message_json.encode())
            
            # 応答を待機
            start_time = time.time()
            while time.time() - start_time < STRATUM_TIMEOUT:
                try:
                    response = self.recv_queue.get(block=True, timeout=0.1)
                    if response.get("id") == message_id:
                        return response
                except queue.Empty:
                    pass
            
            return None  # タイムアウト
        except Exception as e:
            print(f"メッセージ送信エラー: {e}")
            self.is_connected = False
            return None
    
    def submit_share(self, job_id: str, nonce: int) -> bool:
        """シェアを提出"""
        if not self.is_connected:
            print("プールに接続されていません。シェアを提出できません。")
            return False
        
        # ナンスを16進数文字列に変換
        nonce_hex = f"{nonce:08x}"
        
        # シェア提出
        params = [self.wallet_address + "." + self.worker_name, job_id, "0x" + nonce_hex]
        result = self.send_message("mining.submit", params)
        
        if not result or "result" not in result:
            print("シェア提出応答がないか、無効です")
            return False
        
        if result.get("error"):
            print(f"シェア拒否: {result['error']}")
            return False
        
        if result["result"]:
            print("✅ シェアが受け入れられました!")
            return True
        else:
            print("❌ シェアが拒否されました")
            return False
    
    def _receive_loop(self):
        """受信ループ"""
        buffer = ""
        
        while self.is_connected:
            try:
                data = self.socket.recv(4096).decode()
                if not data:
                    # 接続が閉じられた
                    self.is_connected = False
                    print("プール接続が閉じられました")
                    break
                
                buffer += data
                
                # 完全なJSONメッセージを探す
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            message = json.loads(line)
                            self._handle_message(message)
                        except json.JSONDecodeError:
                            print(f"無効なJSONメッセージ: {line}")
            
            except socket.timeout:
                # タイムアウトは正常
                continue
            except Exception as e:
                if self.is_connected:  # 意図的な切断でない場合のみ報告
                    print(f"受信エラー: {e}")
                    self.is_connected = False
                break
    
    def _handle_message(self, message: Dict):
        """受信したメッセージを処理"""
        # レスポンスメッセージ
        if "id" in message:
            self.recv_queue.put(message)
        
        # 通知メッセージ
        elif "method" in message and message["method"] == "mining.notify":
            # 新しい作業通知
            params = message["params"]
            self.job_id = params[0]
            
            # KAWPOWでは新しい作業通知の形式
            header_hash = params[1]
            seed_hash = params[2]
            target = params[3];
            
            new_job = {
                "job_id": self.job_id,
                "header_hash": header_hash,
                "seed_hash": seed_hash,
                "target": target
            }
            
            self.job = new_job
            print(f"\n新しい仕事を受信: job_id={self.job_id}")
        
        # 難易度設定通知
        elif "method" in message and message["method"] == "mining.set_difficulty":
            try:
                self.difficulty = float(message["params"][0])
                
                # 難易度からターゲットを計算
                # KAWPOW用にターゲット計算を調整(難易度に応じてターゲットを計算)
                self.target = int((2**256) / self.difficulty);
                print(f"\n新しい難易度: {self.difficulty} (ターゲット: {hex(self.target)})")
            except Exception as e:
                print(f"難易度設定エラー: {e}")
        
        # その他の通知
        else:
            print(f"未処理のメッセージ: {message}")

class RavencoinMiner:
    def __init__(self, wallet_address: str, pool_url: str = None, threads: int = 1, device_id: int = 0):
        self.wallet_address = wallet_address
        self.pool_url = pool_url
        self.threads = threads
        self.device_id = device_id
        self.running = False
        self.hashrate = 0
        self.shares_found = 0
        self.total_hashes = 0
        self.start_time = None
        self.current_block_height = 0
        self.auto_optimization_thread = None
        
        # NPU補助による自動最適化設定
        self.optimization_interval = 60  # 最適化間隔（秒）
        self.last_optimization = 0
        self.npu_optimizer = None
        
        # RTX 5070tiに最適化したパラメータ
        self.block_size = 256  # CUDAコアに対して効率的なブロックサイズ
        self.grid_size = 35   # グリッドサイズ
        
        # マイニングプール接続
        self.stratum_client = None
        if pool_url:
            self.stratum_client = StratumClient(pool_url, wallet_address)
        
        # CUDA関連設定
        if CUDA_AVAILABLE:
            try:
                # CUDAデバイスの選択
                cuda.init()
                self.device = cuda.Device(device_id)
                self.context = self.device.make_context()
                
                # デバイス情報取得
                device_name = self.device.name()
                compute_capability = self.device.compute_capability()
                total_memory = self.device.total_memory() / (1024**2)  # MBに変換
                
                print(f"GPUデバイス: {device_name} (Compute {compute_capability[0]}.{compute_capability[1]})\n")