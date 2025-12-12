#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政治戦略シミュレーター - Interactive Political Strategy Game
プレイヤー主導型リアルタイム政治ゲーム with 完全LLM統合
"""

import os
import sys
import json
import time
import random
import requests
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, Counter
import math
import re
import threading
import queue

# 設定
LMSTUDIO_API_URL = "http://localhost:1234/v1/chat/completions"
SAVE_DIR = os.path.join(os.path.dirname(__file__), "saves")
os.makedirs(SAVE_DIR, exist_ok=True)

# ゲーム設定
GAME_SPEED_OPTIONS = {
    "1": {"name": "リアルタイム", "multiplier": 1.0},
    "2": {"name": "2倍速", "multiplier": 2.0},
    "3": {"name": "4倍速", "multiplier": 4.0},
    "4": {"name": "一時停止", "multiplier": 0.0}
}

# ========================
# Enum定義
# ========================

class PoliticalIdeology(Enum):
    """政治思想"""
    EXTREME_LEFT = 1      # 極左
    LEFT = 2              # 左派
    CENTER_LEFT = 3       # 中道左派
    CENTER = 4            # 中道
    CENTER_RIGHT = 5      # 中道右派
    RIGHT = 6             # 右派
    EXTREME_RIGHT = 7     # 極右

class PolicyArea(Enum):
    """政策分野"""
    ECONOMY = "経済"
    EDUCATION = "教育"
    HEALTHCARE = "医療"
    DEFENSE = "防衛"
    ENVIRONMENT = "環境"
    WELFARE = "福祉"
    INFRASTRUCTURE = "インフラ"
    TECHNOLOGY = "科学技術"
    CULTURE = "文化"
    LABOR = "労働"
    AGRICULTURE = "農業"
    TRADE = "貿易"
    ENERGY = "エネルギー"
    IMMIGRATION = "移民"
    JUSTICE = "司法"
    
class MinistryType(Enum):
    """省庁タイプ"""
    FINANCE = "財務省"
    FOREIGN_AFFAIRS = "外務省"
    DEFENSE = "防衛省"
    HEALTH = "厚生労働省"
    ECONOMY = "経済産業省"
    EDUCATION = "文部科学省"
    LAND = "国土交通省"
    AGRICULTURE = "農林水産省"
    ENVIRONMENT = "環境省"
    INTERNAL_AFFAIRS = "総務省"
    JUSTICE = "法務省"
    
class FactionType(Enum):
    """派閥タイプ"""
    CONSERVATIVE = "保守派"
    LIBERAL = "改革派"
    REGIONAL = "地方派"
    YOUNG = "若手派"
    VETERAN = "ベテラン派"
    
class ElectionType(Enum):
    """選挙タイプ"""
    GENERAL = "総選挙"
    UPPER_HOUSE = "参議院選"
    LOCAL = "地方選"
    PARTY_LEADER = "総裁選"
    
class BillStatus(Enum):
    """法案状態"""
    DRAFT = "草案"
    COMMITTEE = "委員会審議中"
    LOWER_HOUSE = "衆議院審議中"
    UPPER_HOUSE = "参議院審議中"
    PASSED = "可決"
    REJECTED = "否決"
    ABANDONED = "廃案"

# ========================
# 新しいゲームイベント系
# ========================

class EventType(Enum):
    """イベント種類"""
    CRISIS = "危機"
    OPPORTUNITY = "好機"
    SCANDAL = "スキャンダル"
    INTERNATIONAL = "国際情勢"
    ECONOMIC = "経済変動"
    NATURAL_DISASTER = "自然災害"
    SOCIAL_ISSUE = "社会問題"
    MEDIA_ATTENTION = "メディア注目"

class EventUrgency(Enum):
    """イベント緊急度"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class GameEvent:
    """ゲームイベント"""
    id: str
    title: str
    description: str
    event_type: EventType
    urgency: EventUrgency
    duration_days: int
    created_at: datetime
    expires_at: datetime
    consequences: Dict[str, float] = field(default_factory=dict)
    player_response: Optional[str] = None
    ai_analysis: Optional[str] = None
    resolved: bool = False
    
@dataclass
class PlayerAction:
    """プレイヤーアクション"""
    action_type: str
    target: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    cost: float = 0.0
    expected_outcome: Optional[str] = None

class GameState(Enum):
    """ゲーム状態"""
    PLAYING = "進行中"
    PAUSED = "一時停止"
    EVENT_RESPONSE = "イベント対応中"
    CRISIS_MODE = "危機管理中"
    ELECTION_PERIOD = "選挙期間"

# ========================
# データクラス
# ========================

@dataclass
class Politician:
    """政治家"""
    id: str
    name: str
    age: int
    party: str
    faction: str
    ideology: PoliticalIdeology
    district: str  # 選挙区
    
    # 能力値
    charisma: float  # カリスマ性 (0-100)
    policy_skill: float  # 政策立案能力
    negotiation: float  # 交渉力
    speech: float  # 演説力
    management: float  # 管理能力
    
    # 専門分野
    specialties: List[PolicyArea] = field(default_factory=list)
    
    # 政治的状態
    position: str = "平議員"  # 総理、大臣、委員長など
    ministry: Optional[str] = None
    support_rate: float = 50.0
    scandal_risk: float = 5.0
    loyalty_to_leader: float = 70.0
    
    # 経歴
    terms_served: int = 1  # 当選回数
    cabinet_experience: int = 0  # 入閣回数
    
    # 人間関係
    allies: List[str] = field(default_factory=list)
    rivals: List[str] = field(default_factory=list)
    
@dataclass
class Faction:
    """派閥"""
    name: str
    leader_id: str
    members: List[str]
    ideology: PoliticalIdeology
    faction_type: FactionType
    funds: float  # 派閥資金
    influence: float  # 影響力
    cohesion: float  # 結束力
    
@dataclass
class PoliticalParty:
    """政党"""
    name: str
    short_name: str
    founded_year: int
    ideology: PoliticalIdeology
    
    # 議席数
    lower_house_seats: int = 0
    upper_house_seats: int = 0
    total_seats: int = 0
    
    # 政党状態
    support_rate: float = 30.0
    party_leader_id: Optional[str] = None
    secretary_general_id: Optional[str] = None
    
    # 組織
    factions: List[str] = field(default_factory=list)
    members: List[str] = field(default_factory=list)
    
    # 資金
    party_funds: float = 100.0
    donations: float = 0.0
    
    # 政策
    manifesto: List[str] = field(default_factory=list)
    
@dataclass
class Prefecture:
    """都道府県"""
    name: str
    population: int
    gdp: float
    unemployment_rate: float
    
    # 政治状況
    support_rates: Dict[str, float] = field(default_factory=dict)  # 政党ごと
    support_rate: float = 45.0  # 与党支持率
    happiness: float = 6.5
    ideology_tendency: PoliticalIdeology = PoliticalIdeology.CENTER
    
    # 経済
    major_industries: List[str] = field(default_factory=list)
    growth_rate: float = 1.0
    tax_revenue: float = 0.0
    
    # 選挙区
    electoral_districts: int = 1  # 小選挙区数
    
@dataclass
class Country:
    """外国"""
    name: str
    relationship: float  # -100 to 100
    economic_power: float
    military_power: float
    ideology: PoliticalIdeology
    trade_volume: float
    territorial_disputes: bool
    alliance_level: int  # 0-5
    
    # 外交状態
    embassy_level: int = 3  # 1-5
    trade_agreement: bool = False
    defense_pact: bool = False
    visa_waiver: bool = False
    
    # 経済
    gdp: float = 1000.0
    currency_rate: float = 1.0
    
@dataclass
class Bill:
    """法案"""
    id: str
    name: str
    description: str
    area: PolicyArea
    sponsor: str  # 提出者ID
    sponsor_type: str  # "内閣" or "議員"
    
    # 法案内容
    budget_required: float = 0.0
    expected_effects: Dict[str, float] = field(default_factory=dict)
    
    # 審議状況
    status: BillStatus = BillStatus.DRAFT
    support_count: int = 0
    opposition_count: int = 0
    public_support: float = 50.0
    
    # 委員会
    committee: str = ""
    committee_votes_for: int = 0
    committee_votes_against: int = 0
    
    # 本会議
    lower_house_votes_for: int = 0
    lower_house_votes_against: int = 0
    upper_house_votes_for: int = 0
    upper_house_votes_against: int = 0
    
    submitted_date: Optional[datetime] = None
    passed_date: Optional[datetime] = None
    
@dataclass
class Policy:
    """実施中の政策"""
    name: str
    area: PolicyArea
    cost: float
    effect_on_economy: float
    effect_on_happiness: float
    effect_on_support: float
    implementation_time: int
    
    sponsor_ministry: Optional[str] = None
    public_support: float = 50.0
    
@dataclass
class CabinetMember:
    """閣僚"""
    name: str
    ministry: str
    competence: float
    loyalty: float
    scandal_risk: float
    politician_id: Optional[str] = None
    appointed_date: datetime = field(default_factory=datetime.now)
    approval_rating: float = 50.0
    
@dataclass
class Committee:
    """国会委員会"""
    name: str
    area: PolicyArea
    chairman_id: Optional[str] = None
    members: List[str] = field(default_factory=list)
    current_bills: List[str] = field(default_factory=list)

# ========================
# セーブ/ロードシステム
# ========================

class SaveManager:
    """セーブデータ管理"""
    
    @staticmethod
    def save_game(game_state: 'PoliticalSimulator', slot_name: str = None):
        """ゲームをセーブ"""
        if slot_name is None:
            slot_name = f"save_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        save_path = os.path.join(SAVE_DIR, f"{slot_name}.pkl")
        
        try:
            with open(save_path, 'wb') as f:
                pickle.dump({
                    'version': '3.0',
                    'saved_at': datetime.now(),
                    'game_state': game_state
                }, f)
            
            # メタデータも保存
            meta_path = os.path.join(SAVE_DIR, f"{slot_name}.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'slot_name': slot_name,
                    'saved_at': datetime.now().isoformat(),
                    'turn': game_state.turn,
                    'date': game_state.date.isoformat(),
                    'party_name': game_state.player_party.name,
                    'support_rate': game_state.domestic.national_support,
                    'prime_minister': game_state.player_name
                }, f, ensure_ascii=False, indent=2)
            
            return True, save_path
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def load_game(slot_name: str) -> Optional['PoliticalSimulator']:
        """ゲームをロード"""
        save_path = os.path.join(SAVE_DIR, f"{slot_name}.pkl")
        
        if not os.path.exists(save_path):
            return None
        
        try:
            with open(save_path, 'rb') as f:
                data = pickle.load(f)
                return data['game_state']
        except Exception as e:
            print(f"ロードエラー: {e}")
            return None
    
    @staticmethod
    def list_saves() -> List[Dict]:
        """セーブデータ一覧を取得"""
        saves = []
        for filename in os.listdir(SAVE_DIR):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        saves.append(meta)
                except:
                    pass
        return sorted(saves, key=lambda x: x.get('saved_at', ''), reverse=True)
    
    @staticmethod
    def delete_save(slot_name: str) -> bool:
        """セーブデータを削除"""
        try:
            pkl_path = os.path.join(SAVE_DIR, f"{slot_name}.pkl")
            json_path = os.path.join(SAVE_DIR, f"{slot_name}.json")
            
            if os.path.exists(pkl_path):
                os.remove(pkl_path)
            if os.path.exists(json_path):
                os.remove(json_path)
            return True
        except:
            return False


# ========================
# ゲーム初期設定システム
# ========================

class GameInitializer:
    """ゲーム初期化"""
    
    @staticmethod
    def clear_screen():
        """画面クリア"""
        os.system('clear' if os.name != 'nt' else 'cls')
    
    @staticmethod
    def print_title():
        """タイトル表示"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("""
 ██████╗  ██████╗ ██╗   ██╗ ██████╗  █████╗ ███╗   ███╗███████╗
██╔════╝ ██╔═══██╗██║   ██║██╔════╝ ██╔══██╗████╗ ████║██╔════╝
██║  ███╗██║   ██║██║   ██║██║  ███╗███████║██╔████╔██║█████╗  
██║   ██║██║   ██║╚██╗ ██╔╝██║   ██║██╔══██║██║╚██╔╝██║██╔══╝  
╚██████╔╝╚██████╔╝ ╚████╔╝ ╚██████╔╝██║  ██║██║ ╚═╝ ██║███████╗
 ╚═════╝  ╚═════╝   ╚═══╝   ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝
        """)
        print("                日本政治シミュレーター v3.0")
        print("=" * 80)
    
    @staticmethod
    def show_main_menu() -> str:
        """メインメニュー"""
        GameInitializer.print_title()
        print("\n【メインメニュー】")
        print("1. 新規ゲーム開始")
        print("2. セーブデータをロード")
        print("3. セーブデータ管理")
        print("4. ゲーム説明")
        print("0. 終了")
        print("\n" + "=" * 80)
        return input("選択: ").strip()
    
    @staticmethod
    def create_new_game() -> Optional['PoliticalSimulator']:
        """新規ゲーム作成"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【新規ゲーム作成】")
        print("=" * 80)
        
        # プレイヤー名
        print("\nあなたの名前を入力してください:")
        player_name = input("> ").strip()
        if not player_name:
            player_name = "政治家"
        
        # 政党名
        print("\n政党名を入力してください:")
        print("（例: 自由民主党、立憲民主党、日本新党など）")
        party_name = input("> ").strip()
        if not party_name:
            party_name = "新政党"
        
        # 政党略称
        print("\n政党の略称を入力してください（3文字推奨）:")
        short_name = input("> ").strip()
        if not short_name:
            short_name = party_name[:3]
        
        # イデオロギー選択
        print("\n政党の政治思想を選択してください:")
        print("1. 極左 - 急進的な左派政策")
        print("2. 左派 - リベラル、革新的")
        print("3. 中道左派 - 穏健なリベラル")
        print("4. 中道 - バランス重視")
        print("5. 中道右派 - 穏健な保守")
        print("6. 右派 - 保守、伝統重視")
        print("7. 極右 - 急進的な右派政策")
        
        ideology_map = {
            "1": PoliticalIdeology.EXTREME_LEFT,
            "2": PoliticalIdeology.LEFT,
            "3": PoliticalIdeology.CENTER_LEFT,
            "4": PoliticalIdeology.CENTER,
            "5": PoliticalIdeology.CENTER_RIGHT,
            "6": PoliticalIdeology.RIGHT,
            "7": PoliticalIdeology.EXTREME_RIGHT
        }
        
        ideology_choice = input("> ").strip()
        ideology = ideology_map.get(ideology_choice, PoliticalIdeology.CENTER)
        
        # 公約設定
        print("\n" + "=" * 80)
        print("【選挙公約設定】")
        print("=" * 80)
        print("総裁選に向けて、主要な公約を3つ設定してください。")
        print("（例: 消費税減税、教育無償化、防衛費増額など）")
        
        manifesto = []
        for i in range(3):
            print(f"\n公約 {i+1}:")
            pledge = input("> ").strip()
            if pledge:
                manifesto.append(pledge)
            else:
                manifesto.append(f"政策{i+1}")
        
        # 難易度選択
        print("\n" + "=" * 80)
        print("【難易度選択】")
        print("1. イージー - 初期支持率高め、イベント少なめ")
        print("2. ノーマル - 標準的な難易度")
        print("3. ハード - 低支持率スタート、厳しいイベント")
        print("4. エクストリーム - 地獄の難易度")
        
        difficulty = input("> ").strip()
        
        # 確認
        print("\n" + "=" * 80)
        print("【設定確認】")
        print("=" * 80)
        print(f"プレイヤー名: {player_name}")
        print(f"政党名: {party_name} ({short_name})")
        print(f"思想: {ideology.name}")
        print(f"公約: {', '.join(manifesto)}")
        print(f"難易度: {difficulty}")
        print("\nこの設定でゲームを開始しますか？ (y/n)")
        
        if input("> ").strip().lower() != 'y':
            return None
        
        # ゲーム作成
        game = PoliticalSimulator(
            player_name=player_name,
            party_name=party_name,
            party_short_name=short_name,
            ideology=ideology,
            manifesto=manifesto,
            difficulty=difficulty
        )
        
        return game
    
    @staticmethod
    def show_tutorial():
        """チュートリアル表示"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【ゲーム説明】")
        print("=" * 80)
        print("""
このゲームは、日本の政治家として国を運営する超本格的シミュレーターです。

【ゲーム目標】
✓ 国民支持率 80%以上を達成
✓ 国民幸福度 8.0以上を達成

【ゲームの流れ】
1. 総裁選で勝利して政党のリーダーになる（チュートリアル）
2. 衆議院選挙で過半数を獲得して政権を取る
3. 内閣を組織し、法案を成立させる
4. 外交、経済、社会政策を駆使して国を発展させる
5. 支持率を維持しながら目標達成を目指す

【主要システム】
- 国会システム: 法案審議、委員会、採決
- 選挙システム: 総選挙、参議院選、総裁選
- 内閣運営: 組閣、閣議、官僚との調整
- 外交システム: 各国との関係、貿易、同盟
- 経済シミュレーション: GDP、失業率、財政
- 派閥政治: 党内派閥の調整、人事
- メディア対応: 演説、記者会見、スキャンダル
- LLM連携: 自然言語での政策立案

【操作方法】
- 数字キーでメニュー選択
- 詳細な状況確認と戦略的判断が重要
- セーブは随時可能（savesフォルダに保存）

【難易度】
このゲームは非常にリアルなシミュレーションです。
支持率は簡単に下がり、法案成立も困難です。
様々な要素を総合的に判断し、戦略的にプレイしてください。
        """)
        print("=" * 80)
        input("\nEnterキーで戻る...")


# ========================
# 総裁選システム（チュートリアル）
# ========================

class LeadershipElection:
    """総裁選システム"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
        self.candidates = []
        self.player_support = 0.0
        
    def run_tutorial_election(self) -> bool:
        """総裁選チュートリアル実行"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【総裁選挙 - チュートリアル】")
        print("=" * 80)
        print(f"\n{self.game.player_party.name}の党首選挙が始まります！")
        print("あなたは新人候補として、ベテラン議員たちと戦います。")
        time.sleep(2)
        
        # ライバル候補生成
        self._generate_rival_candidates()
        
        # 選挙運動フェーズ
        print("\n" + "=" * 80)
        print("【第1段階: 選挙運動】")
        print("=" * 80)
        print("演説と政策アピールで支持を集めましょう！")
        time.sleep(1)
        
        for round_num in range(3):
            if not self._campaign_round(round_num + 1):
                return False
        
        # 投票フェーズ
        return self._voting_phase()
    
    def _generate_rival_candidates(self):
        """ライバル候補生成"""
        rival_names = ["田中太郎", "佐藤花子", "鈴木一郎"]
        
        for i, name in enumerate(rival_names):
            self.candidates.append({
                'name': name,
                'support': random.uniform(15, 25),
                'charisma': random.uniform(60, 90),
                'experience': random.randint(3, 8)
            })
        
        self.player_support = 20.0  # プレイヤーの初期支持
    
    def _campaign_round(self, round_num: int) -> bool:
        """選挙運動ラウンド"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print(f"【選挙運動 第{round_num}ラウンド】")
        print("=" * 80)
        
        # 現在の支持率
        print("\n現在の支持率:")
        print(f"  あなた: {self.player_support:.1f}%")
        for cand in self.candidates:
            print(f"  {cand['name']}: {cand['support']:.1f}%")
        
        print("\n" + "-" * 80)
        print("行動を選択してください:")
        print("1. 政策演説を行う（公約をアピール）")
        print("2. 派閥回りをする（議員に直接アピール）")
        print("3. メディア対応（記者会見）")
        print("4. SNS戦略（若年層にアピール）")
        
        choice = input("\n選択: ").strip()
        
        # 行動による支持率変動
        gain = 0
        
        if choice == "1":
            print("\n📢 政策演説を実施...")
            print(f"公約: {', '.join(self.game.player_party.manifesto)}")
            gain = random.uniform(3, 8)
            print(f"有権者に好評でした！ +{gain:.1f}%")
            
        elif choice == "2":
            print("\n🤝 派閥回りを実施...")
            gain = random.uniform(2, 6)
            print(f"議員たちの支持を取り付けました！ +{gain:.1f}%")
            
        elif choice == "3":
            print("\n📰 記者会見を実施...")
            gain = random.uniform(1, 7)
            print(f"メディア露出が増えました！ +{gain:.1f}%")
            
        elif choice == "4":
            print("\n📱 SNS戦略を展開...")
            gain = random.uniform(2, 5)
            print(f"若年層の支持を獲得！ +{gain:.1f}%")
        else:
            print("\n何もしませんでした...")
            gain = 0
        
        self.player_support += gain
        
        # ライバルも活動
        for cand in self.candidates:
            cand['support'] += random.uniform(1, 5)
        
        time.sleep(2)
        return True
    
    def _voting_phase(self) -> bool:
        """投票フェーズ"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【投票日】")
        print("=" * 80)
        print("\n開票が進んでいます...")
        time.sleep(2)
        
        # 最終支持率計算
        total = self.player_support + sum(c['support'] for c in self.candidates)
        player_percentage = (self.player_support / total) * 100
        
        print("\n" + "=" * 80)
        print("【開票結果】")
        print("=" * 80)
        
        results = [(self.game.player_name, self.player_support)]
        for cand in self.candidates:
            results.append((cand['name'], cand['support']))
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        for i, (name, support) in enumerate(results, 1):
            percentage = (support / total) * 100
            bar = "█" * int(percentage / 2)
            marker = "👑" if name == self.game.player_name else ""
            print(f"{i}位: {name:10s} {bar} {percentage:.1f}% {marker}")
        
        print("\n" + "=" * 80)
        
        # 勝敗判定
        if results[0][0] == self.game.player_name:
            print("\n🎉🎉🎉 当選！おめでとうございます！🎉🎉🎉")
            print(f"\nあなたは{self.game.player_party.name}の新党首に選出されました！")
            print("これより、政権奪取を目指します...")
            time.sleep(3)
            return True
        else:
            print("\n😢 残念...当選できませんでした")
            print(f"\n{results[0][0]}が新党首に選ばれました。")
            print("ゲームオーバーです。最初からやり直してください。")
            time.sleep(3)
            return False


# ========================
# 経済システム
# ========================

class EconomicSystem:
    """経済システム"""
    def __init__(self):
        self.gdp = 550.0  # 兆円
        self.growth_rate = 0.8
        self.inflation_rate = 2.0
        self.unemployment_rate = 2.4
        self.national_debt = 1200.0  # 兆円
        self.tax_revenue = 60.0  # 兆円
        self.budget = 110.0  # 兆円
        self.interest_rate = 0.1
        self.stock_index = 28000
        self.yen_rate = 150.0
        
    def simulate_quarter(self, policies: List[Policy]) -> Dict:
        # 複雑な経済シミュレーション
        policy_effect = sum(p.effect_on_economy for p in policies)
        
        # GDP成長率計算
        base_growth = random.gauss(0.5, 0.3)
        policy_growth = policy_effect * 0.1
        external_shock = random.gauss(0, 0.2)
        self.growth_rate = base_growth + policy_growth + external_shock
        
        # GDPアップデート
        self.gdp *= (1 + self.growth_rate / 400)
        
        # インフレ計算
        money_supply_effect = (self.budget - self.tax_revenue) / self.gdp * 10
        self.inflation_rate = max(0, 2.0 + money_supply_effect + random.gauss(0, 0.3))
        
        # 失業率計算
        employment_effect = -policy_effect * 0.05
        self.unemployment_rate = max(0.5, self.unemployment_rate + employment_effect + random.gauss(0, 0.1))
        
        # 国債計算
        deficit = self.budget - self.tax_revenue
        self.national_debt += deficit * 0.25  # 四半期
        
        # 税収計算（GDPに連動）
        self.tax_revenue = self.gdp * 0.11 * (1 + random.gauss(0, 0.02))
        
        # 株価計算
        stock_change = self.growth_rate * 100 + random.gauss(0, 500)
        self.stock_index += stock_change
        self.stock_index = max(10000, self.stock_index)
        
        # 為替レート
        interest_diff = (self.interest_rate - 2.0) * 5
        self.yen_rate += random.gauss(interest_diff, 2)
        self.yen_rate = max(100, min(200, self.yen_rate))
        
        return {
            "gdp_growth": self.growth_rate,
            "inflation": self.inflation_rate,
            "unemployment": self.unemployment_rate,
            "stock_change": stock_change
        }

class DiplomacySystem:
    def __init__(self):
        self.countries = self._initialize_countries()
        
    def _initialize_countries(self) -> Dict[str, Country]:
        return {
            "USA": Country("アメリカ", 70, 100, 100, PoliticalIdeology.CENTER_RIGHT, 200, False, 5),
            "China": Country("中国", -20, 95, 90, PoliticalIdeology.EXTREME_LEFT, 350, True, 1),
            "South Korea": Country("韓国", 40, 50, 30, PoliticalIdeology.CENTER, 80, True, 3),
            "Russia": Country("ロシア", -40, 60, 80, PoliticalIdeology.RIGHT, 30, True, 1),
            "EU": Country("EU", 60, 85, 50, PoliticalIdeology.CENTER_LEFT, 150, False, 4),
            "Australia": Country("オーストラリア", 65, 40, 25, PoliticalIdeology.CENTER_RIGHT, 60, False, 4),
            "India": Country("インド", 50, 70, 45, PoliticalIdeology.CENTER, 50, False, 3),
            "North Korea": Country("北朝鮮", -80, 10, 40, PoliticalIdeology.EXTREME_LEFT, 5, True, 0),
            "Taiwan": Country("台湾", 75, 45, 30, PoliticalIdeology.CENTER, 90, False, 3),
            "ASEAN": Country("ASEAN", 55, 60, 20, PoliticalIdeology.CENTER, 120, False, 3),
        }
    
    def simulate_international_events(self) -> List[str]:
        events = []
        for name, country in self.countries.items():
            # ランダムイベント
            if random.random() < 0.1:
                event_type = random.choice([
                    "economic_crisis", "political_change", "military_tension", 
                    "trade_negotiation", "territorial_dispute", "alliance_proposal"
                ])
                
                if event_type == "economic_crisis":
                    country.economic_power *= 0.9
                    events.append(f"{name}で経済危機発生！")
                elif event_type == "military_tension":
                    country.relationship -= 10
                    events.append(f"{name}との軍事的緊張が高まっています")
                elif event_type == "trade_negotiation":
                    events.append(f"{name}が貿易交渉を提案しています")
                    
        return events
    
    def conduct_diplomacy(self, country_name: str, action: str, intensity: float) -> Dict:
        if country_name not in self.countries:
            return {"success": False, "message": "国が見つかりません"}
        
        country = self.countries[country_name]
        result = {"success": True, "message": ""}
        
        if action == "improve_relations":
            change = intensity * 5
            country.relationship += change
            country.relationship = min(100, country.relationship)
            result["message"] = f"{country_name}との関係が{change:.1f}改善しました"
        elif action == "trade_agreement":
            if country.relationship > 30:
                country.trade_volume *= (1 + intensity * 0.1)
                result["message"] = f"{country_name}と貿易協定を締結しました"
            else:
                result["success"] = False
                result["message"] = "関係が悪すぎて交渉が失敗しました"
        elif action == "military_cooperation":
            if country.relationship > 50:
                country.alliance_level = min(5, country.alliance_level + 1)
                result["message"] = f"{country_name}との軍事協力を強化しました"
            else:
                result["success"] = False
                result["message"] = "信頼関係が不足しています"
                
        return result

class DomesticSystem:
    """内政システム"""

    def __init__(self):
        self.prefectures = self._initialize_prefectures()
        self.national_support = 45.0
        self.national_happiness = 6.5
        self.parties: List[PoliticalParty] = []
        self.cabinet: List[CabinetMember] = []
        self.player_party_name: Optional[str] = None
        self.turns_since_election = 0

    def setup_initial_state(self, player_party: PoliticalParty) -> None:
        """政党や内閣の初期状態を構築"""
        self.player_party_name = player_party.name
        # 既存政党を生成し、プレイヤー政党を含める
        existing_parties = self._generate_initial_parties()
        self.parties = [player_party] + existing_parties
        self._distribute_prefecture_support(player_party)
        self._update_national_support(player_party)
        # 現在の与党（最大議席政党）で暫定内閣を構成
        ruling_party = max(self.parties, key=lambda p: p.lower_house_seats)
        self.cabinet = self._generate_caretaker_cabinet(ruling_party.name)

    def _initialize_prefectures(self) -> Dict[str, Prefecture]:
        prefs: Dict[str, Prefecture] = {}
        pref_data = [
            ("東京", 14000000, 120, 2.1, PoliticalIdeology.CENTER, ["金融", "IT", "サービス"], 6),
            ("大阪", 8800000, 42, 2.8, PoliticalIdeology.CENTER_RIGHT, ["製造業", "商業"], 4),
            ("愛知", 7500000, 41, 2.0, PoliticalIdeology.CENTER_RIGHT, ["自動車", "製造業"], 3),
            ("神奈川", 9200000, 38, 2.3, PoliticalIdeology.CENTER, ["製造業", "IT"], 4),
            ("北海道", 5200000, 20, 3.5, PoliticalIdeology.CENTER_LEFT, ["農業", "観光"], 3),
            ("福岡", 5100000, 21, 2.7, PoliticalIdeology.CENTER, ["サービス業", "製造業"], 3),
            ("沖縄", 1450000, 5, 3.8, PoliticalIdeology.LEFT, ["観光", "基地関連"], 1),
        ]

        for name, pop, gdp, unemp, ideology, industries, districts in pref_data:
            prefs[name] = Prefecture(
                name=name,
                population=pop,
                gdp=gdp,
                unemployment_rate=unemp,
                support_rates={},
                support_rate=random.gauss(45, 5),
                happiness=random.gauss(6.5, 0.5),
                ideology_tendency=ideology,
                major_industries=industries,
                electoral_districts=districts
            )
        return prefs

    def _generate_initial_parties(self) -> List[PoliticalParty]:
        """主要政党の初期値を生成"""
        party_templates = [
            {
                "name": "自由保守党",
                "short": "保守",
                "ideology": PoliticalIdeology.RIGHT,
                "lower": 260,
                "upper": 110,
                "support": 38.0
            },
            {
                "name": "立憲民主連合",
                "short": "立民",
                "ideology": PoliticalIdeology.CENTER_LEFT,
                "lower": 110,
                "upper": 80,
                "support": 24.0
            },
            {
                "name": "改革未来党",
                "short": "改革",
                "ideology": PoliticalIdeology.LEFT,
                "lower": 35,
                "upper": 25,
                "support": 8.5
            },
            {
                "name": "国民協働党",
                "short": "国協",
                "ideology": PoliticalIdeology.CENTER,
                "lower": 25,
                "upper": 18,
                "support": 6.5
            },
            {
                "name": "保守維新会",
                "short": "維新",
                "ideology": PoliticalIdeology.CENTER_RIGHT,
                "lower": 20,
                "upper": 12,
                "support": 7.0
            }
        ]

        parties: List[PoliticalParty] = []
        for template in party_templates:
            party = PoliticalParty(
                name=template["name"],
                short_name=template["short"],
                founded_year=1955,
                ideology=template["ideology"],
                lower_house_seats=template["lower"],
                upper_house_seats=template["upper"],
                total_seats=template["lower"] + template["upper"],
                support_rate=template["support"],
                manifesto=["経済成長", "社会保障", "外交安保"]
            )
            parties.append(party)

        return parties

    def _distribute_prefecture_support(self, player_party: PoliticalParty) -> None:
        """都道府県ごとの支持率を初期化"""
        parties = self.parties
        for pref in self.prefectures.values():
            support_map: Dict[str, float] = {}
            for party in parties:
                base = party.support_rate + random.gauss(0, 5)
                support_map[party.name] = max(5.0, min(70.0, base))

            # 正規化して合計100に調整
            total = sum(support_map.values())
            if total == 0:
                total = 1
            for party_name in support_map:
                support_map[party_name] = support_map[party_name] / total * 100

            pref.support_rates = support_map
            pref.support_rate = support_map.get(player_party.name, 20.0)
            pref.tax_revenue = pref.gdp * 0.08 * random.uniform(0.9, 1.1)

    def _generate_caretaker_cabinet(self, ruling_party_name: str) -> List[CabinetMember]:
        """暫定内閣を構成"""
        ministries = [
            "内閣官房", "財務", "外務", "防衛", "厚生労働", "経済産業",
            "文部科学", "国土交通", "農林水産", "環境", "総務", "デジタル"
        ]
        cabinet: List[CabinetMember] = []
        for ministry in ministries:
            name = f"{ministry}大臣"
            cabinet.append(
                CabinetMember(
                    name=name,
                    ministry=ministry,
                    competence=random.gauss(70, 10),
                    loyalty=random.gauss(65, 15),
                    scandal_risk=max(1.0, random.gauss(5, 2)),
                    politician_id=f"{ruling_party_name}_{ministry}"
                )
            )
        return cabinet

    def _update_national_support(self, player_party: PoliticalParty) -> None:
        if not self.prefectures:
            self.national_support = player_party.support_rate
            return
        average = sum(pref.support_rate for pref in self.prefectures.values()) / len(self.prefectures)
        self.national_support = max(10.0, min(90.0, average))
        player_party.support_rate = self.national_support

    def simulate_public_opinion(
        self,
        player_party: PoliticalParty,
        opposition_parties: List[PoliticalParty],
        policies: List[Policy],
        economic_data: Dict,
        diplomatic_events: List[str]
    ) -> None:
        """複数要素を考慮した世論シミュレーション"""

        base_change = random.gauss(0, 1.5)

        economic_effect = 0.0
        if economic_data["gdp_growth"] > 2:
            economic_effect += 1.5
        elif economic_data["gdp_growth"] < 0:
            economic_effect -= 2.5

        if economic_data["unemployment"] > 3.5:
            economic_effect -= 1.5
        elif economic_data["unemployment"] < 2.0:
            economic_effect += 1.0

        policy_effect = sum(p.effect_on_support for p in policies)
        diplomatic_effect = -len([e for e in diplomatic_events if "緊張" in e or "危機" in e])

        scandal_effect = 0.0
        for member in self.cabinet:
            if random.random() < member.scandal_risk / 100:
                penalty = random.uniform(3, 8)
                scandal_effect -= penalty
                print(f"\n⚠️ {member.name}のスキャンダルが発覚！ 支持率-{penalty:.1f}%")

        total_change = base_change + economic_effect + policy_effect + diplomatic_effect + scandal_effect
        player_party.support_rate = max(8.0, min(85.0, player_party.support_rate + total_change))
        self._update_national_support(player_party)

        # 幸福度
        happiness_change = sum(p.effect_on_happiness for p in policies) * 0.08
        happiness_change += economic_data["gdp_growth"] * 0.04
        happiness_change += random.gauss(0, 0.1)
        self.national_happiness = max(3.0, min(10.0, self.national_happiness + happiness_change))

        # 都道府県別アップデート
        for pref in self.prefectures.values():
            player_pref_change = total_change * random.gauss(0.9, 0.2)
            pref.support_rate = max(5.0, min(90.0, pref.support_rate + player_pref_change))
            pref.support_rates[player_party.name] = pref.support_rate

            # 野党支持率を調整
            for party in opposition_parties:
                if party.name == player_party.name:
                    continue
                delta = random.gauss(-player_pref_change / 3, 1.0)
                current = pref.support_rates.get(party.name, party.support_rate)
                new_support = max(2.0, min(70.0, current + delta))
                pref.support_rates[party.name] = new_support

        # 野党支持率も全国平均を更新
        for party in opposition_parties:
            if party.name == player_party.name:
                continue
            regional_average = sum(pref.support_rates.get(party.name, party.support_rate) for pref in self.prefectures.values())
            party.support_rate = max(3.0, min(55.0, regional_average / len(self.prefectures)))

        self.turns_since_election += 1

class LLMIntegration:
    def __init__(self, api_url: str = LMSTUDIO_API_URL):
        self.api_url = api_url
        self.available = self._test_connection()
        if self.available:
            print("✅ LLM接続成功 - 高度なAI分析が利用可能です")
        else:
            print("⚠️ LLM接続失敗 - 基本分析モードで動作します")
        
    def _test_connection(self) -> bool:
        try:
            response = requests.post(
                self.api_url,
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10
                },
                timeout=3
            )
            return response.status_code == 200
        except:
            return False
    
    def analyze_policy_impact(self, policy_description: str, context: Dict) -> Dict:
        if not self.available:
            return self._fallback_analysis(policy_description)
        
        prompt = f"""あなたは政治経済の専門家です。以下の政策の影響を分析してください。

政策: {policy_description}

現在の状況:
- GDP成長率: {context['gdp_growth']:.1f}%
- 失業率: {context['unemployment']:.1f}%
- 支持率: {context['support']:.1f}%
- 国家債務: {context['debt']:.0f}兆円

以下の項目について-10から+10で評価してください:
1. 経済への影響
2. 国民の幸福度への影響
3. 支持率への影響
4. 実施コスト(兆円単位)

JSON形式で回答してください:
{{"economy": 数値, "happiness": 数値, "support": 数値, "cost": 数値, "analysis": "詳細分析"}}"""

        try:
            response = requests.post(
                self.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # JSON抽出
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except Exception as e:
            print(f"LLM分析エラー: {e}")
        
        return self._fallback_analysis(policy_description)
    
    def _fallback_analysis(self, policy: str) -> Dict:
        # LLM接続失敗時のフォールバック
        return {
            "economy": random.gauss(0, 3),
            "happiness": random.gauss(0, 3),
            "support": random.gauss(0, 3),
            "cost": random.uniform(1, 10),
            "analysis": "LLM接続不可。基本分析を使用しています。"
        }
    
    def parse_llm_response(self, text: str) -> tuple[str, str]:
        """
        LLMの応答から<think></think>タグを分離
        Returns: (思考プロセス, 実際の発言)
        """
        import re
        
        # <think>...</think>タグを検索
        think_pattern = r'<think>(.*?)</think>'
        think_matches = re.findall(think_pattern, text, re.DOTALL)
        
        # <think>タグを除去して実際の発言部分を抽出
        clean_text = re.sub(think_pattern, '', text, flags=re.DOTALL).strip()
        
        # 思考プロセスをまとめる
        thinking = '\n'.join(think_matches) if think_matches else ""
        
        return thinking, clean_text
    
    def analyze_speech_impact(self, speech_content: str, audience_type: str, context: Dict) -> Dict:
        """演説内容を分析して政治的影響を評価"""
        if not self.available:
            return self._fallback_speech_analysis(speech_content)
        
        prompt = f"""あなたは政治分析の専門家です。以下の演説内容を分析してください。

演説内容: {speech_content}
聴衆タイプ: {audience_type}
現在の支持率: {context.get('support', 30):.1f}%

この演説について以下を分析してJSON形式で回答してください:
1. 論理性（0-100）: 論拠の明確さと筋道
2. 感情的訴求力（0-100）: 聴衆の心に響く度合い
3. 政策実現性（0-100）: 提案の実現可能性
4. リスク要素（0-100）: 炎上や批判のリスク
5. 支持率への影響（-10から+10）
6. 特定層への効果（JSON）

{{"logic": 数値, "emotion": 数値, "feasibility": 数値, "risk": 数値, "support_change": 数値, "demographic_effects": {{"youth": 数値, "elderly": 数値, "business": 数値, "workers": 数値}}, "analysis": "詳細分析"}}"""

        try:
            response = requests.post(
                self.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.6,
                    "max_tokens": 800
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.parse_llm_response(content)
                
                # JSON抽出
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    if thinking:
                        result["thinking_process"] = thinking
                    return result
        except Exception as e:
            print(f"演説分析エラー: {e}")
        
        return self._fallback_speech_analysis(speech_content)
    
    def _fallback_speech_analysis(self, speech: str) -> Dict:
        """LLM接続失敗時の基本分析"""
        length_bonus = min(2.0, len(speech) / 200)  # 長いほど効果的
        return {
            "logic": random.randint(40, 80),
            "emotion": random.randint(30, 90),
            "feasibility": random.randint(50, 85),
            "risk": random.randint(10, 60),
            "support_change": random.uniform(-2, 4) + length_bonus,
            "demographic_effects": {
                "youth": random.uniform(-1, 3),
                "elderly": random.uniform(-1, 3),
                "business": random.uniform(-2, 4),
                "workers": random.uniform(-1, 3)
            },
            "analysis": "基本分析モード（LLM未接続）"
        }

    def generate_speech(self, topic: str, context: Dict) -> str:
        if not self.available:
            return f"{topic}について演説を行いました。（LLM未接続）"
        
        prompt = f"""あなたは日本の首相です。以下のテーマで演説を作成してください。

テーマ: {topic}
支持率: {context['support']:.1f}%
経済成長率: {context['gdp_growth']:.1f}%

300文字程度の演説を作成してください。"""

        try:
            response = requests.post(
                self.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
        except:
            pass
        
        return f"{topic}について力強い演説を行いました。"
    
    def analyze_political_stance_impact(self, content: str, context: Dict) -> Dict:
        """発言内容の政治的立場・論理性・感情訴求を詳細分析"""
        if not self.available:
            return self._fallback_stance_analysis(content)
        
        prompt = f"""あなたは政治学者です。以下の政治的発言を多角的に分析してください。

発言内容: {content}
現在の支持率: {context.get('support', 30):.1f}%
政治情勢: {context.get('situation', '通常時')}

以下の項目を詳細に分析し、JSON形式で回答してください:

1. 政治的立場分析（0-100）:
   - 保守性: 伝統的価値への傾倒度
   - 革新性: 変革・改革への指向度  
   - 現実性: 実現可能性・現実路線度
   - 理想性: 理念・ビジョンの強度

2. 論理構成分析（0-100）:
   - 論理的整合性: 筋道の一貫性
   - 根拠の具体性: データや事例の豊富さ
   - 反論への備え: 想定反論への対処
   - 結論の明確性: 主張の分かりやすさ

3. 感情的要素（0-100）:
   - 共感訴求: 国民感情への響き度
   - 危機感喚起: 緊急性の演出度
   - 希望提示: 明るい未来への言及
   - 信頼感醸成: リーダーシップの印象

4. 各層への影響予測（-10から+10）:
   - 保守層、リベラル層、無党派層、若年層、高齢層、経済界、労働者

{{"conservative_stance": 数値, "progressive_stance": 数値, "realistic_stance": 数値, "idealistic_stance": 数値, "logical_consistency": 数値, "evidence_strength": 数値, "counter_preparedness": 数値, "clarity": 数値, "empathy_appeal": 数値, "urgency_creation": 数値, "hope_presentation": 数値, "trust_building": 数値, "demographic_impact": {{"conservative": 数値, "liberal": 数値, "independent": 数値, "youth": 数値, "elderly": 数値, "business": 数値, "workers": 数値}}, "overall_effectiveness": 数値, "risk_assessment": "リスク評価", "strategic_advice": "戦略的アドバイス", "analysis": "総合分析"}}"""

        try:
            response = requests.post(
                self.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 1200
                },
                timeout=35
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.parse_llm_response(content)
                
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    if thinking:
                        result["thinking_process"] = thinking
                    return result
        except Exception as e:
            print(f"政治的立場分析エラー: {e}")
        
        return self._fallback_stance_analysis(content)
    
    def _fallback_stance_analysis(self, content: str) -> Dict:
        """LLM接続失敗時の基本立場分析"""
        content_length = len(content)
        
        return {
            "conservative_stance": random.randint(20, 80),
            "progressive_stance": random.randint(20, 80),
            "realistic_stance": random.randint(40, 85),
            "idealistic_stance": random.randint(30, 70),
            "logical_consistency": random.randint(45, 85),
            "evidence_strength": random.randint(30, 80),
            "counter_preparedness": random.randint(35, 75),
            "clarity": random.randint(50, 85),
            "empathy_appeal": random.randint(40, 80),
            "urgency_creation": random.randint(20, 70),
            "hope_presentation": random.randint(30, 80),
            "trust_building": random.randint(40, 85),
            "demographic_impact": {
                "conservative": random.uniform(-2, 4),
                "liberal": random.uniform(-2, 4),
                "independent": random.uniform(-1, 3),
                "youth": random.uniform(-2, 5),
                "elderly": random.uniform(-1, 3),
                "business": random.uniform(-3, 4),
                "workers": random.uniform(-2, 3)
            },
            "overall_effectiveness": random.randint(45, 85),
            "risk_assessment": "標準的リスク",
            "strategic_advice": "バランスの取れた発言を心がけてください",
            "analysis": "基本分析モード（LLM未接続）"
        }


# ========================
# リアルタイムイベント管理システム
# ========================

class EventManager:
    """リアルタイムでイベントを管理し、プレイヤーに戦略的判断を求める"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
        self.active_events: List[GameEvent] = []
        self.event_queue: queue.Queue = queue.Queue()
        self.llm = game.llm
        self.event_counter = 0
        
    def generate_dynamic_event(self) -> Optional[GameEvent]:
        """現在の政治状況に基づいてLLMで動的イベントを生成"""
        if not self.llm.available:
            return self._generate_fallback_event()
        
        context = self._build_context()
        
        prompt = f"""あなたは政治情勢分析の専門家です。現在の日本の政治状況に基づいて、リアルな政治イベントを1つ生成してください。

現在の状況:
- プレイヤー政党支持率: {self.game.player_party.support_rate:.1f}%
- 政権党: {'与党' if self.game.is_prime_minister else '野党'}
- 経済成長率: {self.game.economy.growth_rate:.1f}%
- 失業率: {self.game.economy.unemployment_rate:.1f}%
- 現在の日付: {self.game.date.strftime('%Y年%m月%d日')}

以下のようなリアルな政治イベントを生成してJSON形式で回答してください:

{{"title": "イベントタイトル", "description": "詳細な説明（200文字程度）", "event_type": "CRISIS/OPPORTUNITY/SCANDAL/INTERNATIONAL/ECONOMIC/NATURAL_DISASTER/SOCIAL_ISSUE/MEDIA_ATTENTION", "urgency": "LOW/MEDIUM/HIGH/CRITICAL", "duration_days": 数値, "potential_responses": ["選択肢1", "選択肢2", "選択肢3"], "consequences": {{"support_change_range": [-5, 5], "economic_impact_range": [-3, 3]}}, "ai_advice": "戦略的アドバイス"}}"""

        try:
            response = requests.post(
                self.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 800
                },
                timeout=25
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.llm.parse_llm_response(content)
                
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    event_data = json.loads(json_match.group())
                    return self._create_event_from_llm_data(event_data, thinking)
        except Exception as e:
            print(f"イベント生成エラー: {e}")
        
        return self._generate_fallback_event()
    
    def _build_context(self) -> Dict:
        """現在のゲーム状況をコンテキストとして構築"""
        return {
            "support_rate": self.game.player_party.support_rate,
            "is_pm": self.game.is_prime_minister,
            "economy": {
                "growth": self.game.economy.growth_rate,
                "unemployment": self.game.economy.unemployment_rate,
                "debt": self.game.economy.national_debt
            },
            "date": self.game.date,
            "turn": self.game.turn
        }
    
    def _create_event_from_llm_data(self, data: Dict, thinking: str = "") -> GameEvent:
        """LLMデータからGameEventを作成"""
        self.event_counter += 1
        event_id = f"event_{self.event_counter}_{int(time.time())}"
        
        # Enumに変換
        try:
            event_type = EventType[data["event_type"]]
        except KeyError:
            event_type = EventType.SOCIAL_ISSUE
        
        try:
            urgency = EventUrgency[data["urgency"]]
        except KeyError:
            urgency = EventUrgency.MEDIUM
        
        duration = data.get("duration_days", 7)
        
        return GameEvent(
            id=event_id,
            title=data["title"],
            description=data["description"],
            event_type=event_type,
            urgency=urgency,
            duration_days=duration,
            created_at=self.game.date,
            expires_at=self.game.date + timedelta(days=duration),
            consequences=data.get("consequences", {}),
            ai_analysis=thinking + "\n\nAIアドバイス: " + data.get("ai_advice", "")
        )
    
    def _generate_fallback_event(self) -> GameEvent:
        """LLM接続失敗時の基本イベント生成"""
        events = [
            {
                "title": "経済指標の変動",
                "description": "最新の経済指標が発表され、政府の経済政策への評価が注目されています。",
                "type": EventType.ECONOMIC,
                "urgency": EventUrgency.MEDIUM
            },
            {
                "title": "国際会議への招待",
                "description": "重要な国際会議への参加要請があり、外交方針の表明が求められています。",
                "type": EventType.INTERNATIONAL,
                "urgency": EventUrgency.HIGH
            },
            {
                "title": "社会問題の浮上",
                "description": "新たな社会問題が世論の注目を集め、政府の対応が期待されています。",
                "type": EventType.SOCIAL_ISSUE,
                "urgency": EventUrgency.MEDIUM
            }
        ]
        
        selected = random.choice(events)
        self.event_counter += 1
        
        return GameEvent(
            id=f"fallback_{self.event_counter}",
            title=selected["title"],
            description=selected["description"],
            event_type=selected["type"],
            urgency=selected["urgency"],
            duration_days=random.randint(3, 14),
            created_at=self.game.date,
            expires_at=self.game.date + timedelta(days=random.randint(3, 14))
        )
    
    def present_event_to_player(self, event: GameEvent) -> str:
        """イベントをプレイヤーに提示し、対応を求める"""
        print("\n" + "=" * 80)
        print("【緊急事態発生】" if event.urgency.value >= 3 else "【新たな状況】")
        print("=" * 80)
        print(f"事案: {event.title}")
        print(f"詳細: {event.description}")
        print(f"緊急度: {event.urgency.name} (期限: {event.expires_at.strftime('%Y/%m/%d')})")
        
        if event.ai_analysis:
            print(f"\nAI分析: {event.ai_analysis}")
        
        print("\n" + "-" * 60)
        print("あなたの対応方針を自由に入力してください:")
        print("(具体的な行動や声明内容など、Enter2回で決定)")
        print("-" * 60)
        
        # プレイヤーの応答を取得
        response_lines = []
        empty_count = 0
        while True:
            line = input()
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
                response_lines.append(line)
        
        player_response = '\n'.join(response_lines)
        if not player_response.strip():
            player_response = "状況を注視し、慎重に対応していく。"
            print("(無回答のため標準対応)")
        
        # LLMで対応を分析
        self._analyze_player_response(event, player_response)
        return player_response
    
    def _analyze_player_response(self, event: GameEvent, response: str):
        """プレイヤーの対応をLLMで分析し、結果を適用"""
        if not self.llm.available:
            self._apply_fallback_consequences(event, response)
            return
        
        prompt = f"""政治評論家として、以下の政治イベントに対するプレイヤーの対応を評価してください。

イベント: {event.title}
状況: {event.description}
プレイヤーの対応: {response}

現在の政治状況:
- 支持率: {self.game.player_party.support_rate:.1f}%
- 地位: {'首相' if self.game.is_prime_minister else '野党党首'}

この対応について以下を分析してJSON形式で回答してください:
1. 対応の適切さ (0-100)
2. 政治的リスク (0-100)
3. 支持率への影響 (-15から+15)
4. 経済への影響 (-5から+5)
5. 国民の反応
6. メディアの反応
7. 野党の反応

{{"appropriateness": 数値, "political_risk": 数値, "support_impact": 数値, "economic_impact": 数値, "public_reaction": "国民の反応", "media_reaction": "メディアの反応", "opposition_reaction": "野党の反応", "analysis": "総合評価"}}"""

        try:
            response_obj = requests.post(
                self.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.6,
                    "max_tokens": 700
                },
                timeout=25
            )
            
            if response_obj.status_code == 200:
                content = response_obj.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.llm.parse_llm_response(content)
                
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    self._apply_event_consequences(event, response, analysis)
                    return
        except Exception as e:
            print(f"対応分析エラー: {e}")
        
        self._apply_fallback_consequences(event, response)
    
    def _apply_event_consequences(self, event: GameEvent, response: str, analysis: Dict):
        """分析結果に基づいて結果を適用"""
        print("\n" + "=" * 80)
        print("【対応結果】")
        print("=" * 80)
        
        # 支持率変動
        support_change = analysis.get("support_impact", 0)
        old_support = self.game.player_party.support_rate
        self.game.player_party.support_rate += support_change
        self.game.player_party.support_rate = max(5.0, min(95.0, self.game.player_party.support_rate))
        
        print(f"支持率変動: {old_support:.1f}% → {self.game.player_party.support_rate:.1f}% ({support_change:+.1f}%)")
        
        # 経済影響
        economic_impact = analysis.get("economic_impact", 0)
        if economic_impact != 0:
            self.game.economy.growth_rate += economic_impact * 0.1
            print(f"経済成長率への影響: {economic_impact:+.1f}%")
        
        # 各方面の反応
        print(f"\n国民の反応: {analysis.get('public_reaction', '概ね冷静')}")
        print(f"メディアの反応: {analysis.get('media_reaction', '注目している')}")
        print(f"野党の反応: {analysis.get('opposition_reaction', '批判的')}")
        
        print(f"\n総合評価: {analysis.get('analysis', '標準的な対応')}")
        
        # イベントを解決済みにマーク
        event.resolved = True
        event.player_response = response
        
        time.sleep(3)
    
    def _apply_fallback_consequences(self, event: GameEvent, response: str):
        """LLM接続失敗時の基本結果適用"""
        # 基本的な結果計算
        response_quality = min(100, len(response) / 5)  # 回答の長さで質を判定
        
        support_change = random.uniform(-2, 4) * (response_quality / 100)
        
        old_support = self.game.player_party.support_rate
        self.game.player_party.support_rate += support_change
        self.game.player_party.support_rate = max(5.0, min(95.0, self.game.player_party.support_rate))
        
        print(f"\n対応結果: 支持率 {old_support:.1f}% → {self.game.player_party.support_rate:.1f}% ({support_change:+.1f}%)")
        
        event.resolved = True
        event.player_response = response
        time.sleep(2)
    
    def update_events(self):
        """アクティブなイベントを更新"""
        current_time = self.game.date
        
        # 期限切れイベントを削除
        self.active_events = [e for e in self.active_events if e.expires_at > current_time]
        
        # 新しイベント生成の判定
        if random.random() < 0.3 and len(self.active_events) < 3:  # 30%の確率で新イベント
            new_event = self.generate_dynamic_event()
            if new_event:
                self.active_events.append(new_event)
                return new_event
        
        return None


# ========================
# 国民感情シミュレーター
# ========================

class PublicOpinionSimulator:
    """LLMを使って国民の反応をリアルタイムでシミュレート"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
        self.llm = game.llm
        self.recent_actions = []  # 最近のプレイヤーアクション履歴
        
    def simulate_public_reaction(self, action_description: str, context: Dict = None) -> Dict:
        """プレイヤーの行動に対する国民の反応をLLMでシミュレート"""
        if not self.llm.available:
            return self._fallback_public_reaction(action_description)
        
        context = context or {}
        
        prompt = f"""あなたは世論調査の専門家です。日本国民の声を代表して、政治家の以下の行動に対する一般市民の反応を分析してください。

政治家の行動: {action_description}

現在の状況:
- 政治家の現在支持率: {self.game.player_party.support_rate:.1f}%
- 地位: {'首相' if self.game.is_prime_minister else '野党党首'}
- 経済状況: GDP成長率{self.game.economy.growth_rate:.1f}%, 失業率{self.game.economy.unemployment_rate:.1f}%
- 時期: {self.game.date.strftime('%Y年%m月')}

以下の観点から国民の反応を分析し、JSON形式で回答してください:

1. 各層の反応 (支持率変動 -10から+10):
   - 若年層 (20-30代)
   - 中年層 (40-50代) 
   - 高齢層 (60代以上)
   - 都市部住民
   - 地方住民
   - 経営者層
   - 会社員層
   - 主婦層

2. 感情的反応:
   - 好感度変化
   - 信頼度変化
   - 期待度変化

{{"demographic_reactions": {{"youth": 数値, "middle_age": 数値, "elderly": 数値, "urban": 数値, "rural": 数値, "business_owners": 数値, "employees": 数値, "housewives": 数値}}, "emotional_impact": {{"likability": 数値, "trust": 数値, "expectation": 数値}}, "overall_sentiment": "ポジティブ/ニュートラル/ネガティブ", "key_concerns": ["懸念1", "懸念2"], "supportive_points": ["支持点1", "支持点2"], "public_voice": "国民の声の例", "predicted_consequences": "今後の影響予測"}}"""

        try:
            response = requests.post(
                self.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 900
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.llm.parse_llm_response(content)
                
                try:
                    import re
                    json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                        if thinking:
                            result["analysis_process"] = thinking
                        return result
                except json.JSONDecodeError:
                    print("JSONパースエラー、フォールバック使用")
                    pass
        except Exception as e:
            print(f"国民感情分析エラー: {e}")
        
        return self._fallback_public_reaction(action_description)
    
    def _fallback_public_reaction(self, action: str) -> Dict:
        """LLM接続失敗時の基本反応"""
        return {
            "demographic_reactions": {
                "youth": random.uniform(-2, 3),
                "middle_age": random.uniform(-2, 2),
                "elderly": random.uniform(-1, 2),
                "urban": random.uniform(-2, 3),
                "rural": random.uniform(-1, 2),
                "business_owners": random.uniform(-3, 4),
                "employees": random.uniform(-1, 2),
                "housewives": random.uniform(-1, 2)
            },
            "emotional_impact": {
                "likability": random.uniform(-2, 2),
                "trust": random.uniform(-2, 2),
                "expectation": random.uniform(-1, 3)
            },
            "overall_sentiment": random.choice(["ポジティブ", "ニュートラル", "ネガティブ"]),
            "key_concerns": ["経済への影響", "政策の実効性"],
            "supportive_points": ["決断力", "リーダーシップ"],
            "public_voice": "様々な意見が聞かれます",
            "predicted_consequences": "しばらく注視が必要"
        }
    
    def generate_detailed_citizen_comments(self, action_description: str, reaction: Dict) -> List[Dict]:
        """市民の詳細なコメントを生成"""
        if not self.llm.available:
            return self._fallback_citizen_comments(action_description)
        
        prompt = f"""あなたは日本の様々な立場の市民です。政治家の以下の行動に対して、リアルで多様な市民の声を生成してください。

政治家の行動: {action_description}
全体的な世論: {reaction.get('overall_sentiment', 'ニュートラル')}

以下のような異なる属性を持つ5-8人の市民からの具体的なコメントを生成してください:
- 年齢層: 20代、30代、40代、50代、60代以上
- 職業: 会社員、主婦、学生、経営者、公務員、農家など
- 地域: 都市部、地方
- 政治的立場: 支持、中立、反対

各コメントは以下のJSON形式で出力してください:
[
{{"speaker": "属性（例：30代会社員・東京）", "comment": "具体的なコメント40-80文字", "stance": "支持/中立/反対"}},
{{"speaker": "属性", "comment": "コメント", "stance": "支持/中立/反対"}}
]

リアルで自然な日本語のコメントにしてください。"""

        try:
            response = requests.post(
                self.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 800
                },
                timeout=25
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.llm.parse_llm_response(content)
                
                try:
                    import re
                    json_match = re.search(r'\[.*\]', clean_response, re.DOTALL)
                    if json_match:
                        comments = json.loads(json_match.group())
                        # 有効なコメント形式かチェック
                        valid_comments = []
                        for comment in comments:
                            if isinstance(comment, dict) and 'speaker' in comment and 'comment' in comment:
                                valid_comments.append(comment)
                        return valid_comments[:8] if valid_comments else self._fallback_citizen_comments(action_description)
                except json.JSONDecodeError:
                    print("JSONパースエラー、フォールバック使用")
                    pass
        except Exception as e:
            print(f"市民コメント生成エラー: {e}")
        
        return self._fallback_citizen_comments(action_description)
    
    def _fallback_citizen_comments(self, action: str) -> List[Dict]:
        """フォールバック用の市民コメント"""
        return [
            {"speaker": "30代会社員・東京", "comment": "政治家の言葉だけでは判断できない。結果を見たい", "stance": "中立"},
            {"speaker": "60代主婦・大阪", "comment": "もっと生活に直結する政策を考えてほしい", "stance": "中立"},
            {"speaker": "40代経営者・愛知", "comment": "経済への影響をしっかり検証してから実行して", "stance": "反対"},
            {"speaker": "20代学生・福岡", "comment": "若い世代の意見も取り入れてくれることを期待", "stance": "支持"}
        ]

    def display_public_reaction(self, reaction: Dict, action_description: str):
        """国民の反応を表示"""
        print("\n" + "=" * 80)
        print("【国民の声・世論動向】")
        print("=" * 80)
        print(f"対象行動: {action_description}")
        
        # 全体的な感情
        sentiment = reaction.get("overall_sentiment", "ニュートラル")
        print(f"\n全体的な世論: {sentiment}")
        
        # 層別反応
        demo_reactions = reaction.get("demographic_reactions", {})
        print(f"\n層別支持率変動:")
        demo_names = {
            "youth": "若年層",
            "middle_age": "中年層", 
            "elderly": "高齢層",
            "urban": "都市部",
            "rural": "地方",
            "business_owners": "経営者",
            "employees": "会社員",
            "housewives": "主婦"
        }
        
        for key, value in demo_reactions.items():
            name = demo_names.get(key, key)
            print(f"  {name}: {value:+.1f}%")
        
        # 詳細な市民コメントを生成・表示
        print(f"\n【市民の声】")
        citizen_comments = self.generate_detailed_citizen_comments(action_description, reaction)
        
        for i, comment_data in enumerate(citizen_comments, 1):
            speaker = comment_data.get("speaker", "市民")
            comment = comment_data.get("comment", "")
            stance = comment_data.get("stance", "中立")
            
            stance_icon = {"支持": "✓", "反対": "✗", "中立": "○"}.get(stance, "○")
            print(f"  {i}. [{stance_icon}] {speaker}: 「{comment}」")
        
        # 国民の声
        public_voice = reaction.get("public_voice", "")
        if public_voice:
            print(f"\n代表的な声: 「{public_voice}」")
        
        # 懸念と支持点
        concerns = reaction.get("key_concerns", [])
        supports = reaction.get("supportive_points", [])
        
        if concerns:
            print(f"\n主な懸念: {', '.join(concerns)}")
        if supports:
            print(f"支持される点: {', '.join(supports)}")
        
        # 今後の予測
        consequences = reaction.get("predicted_consequences", "")
        if consequences:
            print(f"\n影響予測: {consequences}")
        
        time.sleep(3)
    
    def calculate_support_change(self, reaction: Dict) -> float:
        """反応データから支持率変動を計算"""
        demo_reactions = reaction.get("demographic_reactions", {})
        
        # 各層の人口重み付け（概算）
        weights = {
            "youth": 0.25,      # 若年層25%
            "middle_age": 0.35, # 中年層35%  
            "elderly": 0.40,    # 高齢層40%
        }
        
        # 地域・職業での補正
        area_weights = {
            "urban": 0.6,       # 都市部60%
            "rural": 0.4        # 地方40%
        }
        
        # 加重平均で支持率変動を計算
        total_change = 0
        total_weight = 0
        
        for demo, change in demo_reactions.items():
            weight = weights.get(demo, 0.1)
            total_change += change * weight
            total_weight += weight
        
        if total_weight > 0:
            return total_change / total_weight
        return 0


# ========================
# 公共活動システム
# ========================

class PublicActivitySystem:
    """街頭演説、SNS、記者会見、討論会等の公共活動管理"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
        self.speech_history = []
        self.sns_posts = []
        self.press_conferences = []
        self.debates = []
    
    def street_speech(self):
        """街頭演説システム"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【街頭演説】")
        print("=" * 80)
        
        # 会場選択
        venues = [
            {"name": "新宿駅前", "crowd": "一般市民", "size": 500, "difficulty": 1.0},
            {"name": "渋谷ハチ公前", "crowd": "若年層中心", "size": 300, "difficulty": 1.2},
            {"name": "銀座中央通り", "crowd": "ビジネス層", "size": 200, "difficulty": 1.5},
            {"name": "商店街", "crowd": "地域住民", "size": 150, "difficulty": 0.8},
            {"name": "大学キャンパス", "crowd": "学生", "size": 400, "difficulty": 1.3},
            {"name": "工業地帯", "crowd": "労働者", "size": 250, "difficulty": 1.1}
        ]
        
        print("\n演説会場を選択してください:")
        for i, venue in enumerate(venues, 1):
            print(f"{i}. {venue['name']} (聴衆:{venue['crowd']} 予想人数:{venue['size']}人)")
        
        venue_choice = input("\n会場選択 (1-6): ").strip()
        if not venue_choice.isdigit() or not 1 <= int(venue_choice) <= 6:
            print("❌ 無効な選択です")
            return
        
        selected_venue = venues[int(venue_choice) - 1]
        
        print(f"\n📍 会場: {selected_venue['name']}")
        print(f"👥 聴衆: {selected_venue['crowd']} ({selected_venue['size']}人)")
        print("\n" + "-" * 80)
        print("💬 演説内容を自由に入力してください（Enter2回で終了）:")
        print("-" * 80)
        
        # 演説内容入力
        speech_lines = []
        empty_line_count = 0
        while True:
            line = input()
            if line.strip() == "":
                empty_line_count += 1
                if empty_line_count >= 2:
                    break
            else:
                empty_line_count = 0
                speech_lines.append(line)
        
        speech_content = '\n'.join(speech_lines)
        if not speech_content.strip():
            print("\n❌ 演説内容が入力されていません")
            return
        
        print("\n" + "=" * 80)
        print("【演説実行中】")
        print("=" * 80)
        print(f"🎤 あなたの演説:\n{speech_content}")
        print("\n⏳ 聴衆の反応を分析中...")
        time.sleep(2)
        
        # LLMによる演説分析
        context = {
            'support': self.game.player_party.support_rate,
            'venue': selected_venue['name'],
            'audience': selected_venue['crowd']
        }
        
        analysis = self.game.llm.analyze_speech_impact(speech_content, selected_venue['crowd'], context)
        
        # 結果表示
        self._display_speech_results(analysis, selected_venue, speech_content)
        
        # 支持率への影響適用
        self._apply_speech_effects(analysis, selected_venue)
        
        # 履歴保存
        self.speech_history.append({
            'date': self.game.date,
            'venue': selected_venue['name'],
            'content': speech_content,
            'analysis': analysis
        })
    
    def _display_speech_results(self, analysis: Dict, venue: Dict, speech: str):
        """演説結果の詳細表示"""
        print("\n" + "=" * 80)
        print("【演説結果分析】")
        print("=" * 80)
        
        # LLMの思考プロセスがあれば表示
        if analysis.get('thinking_process'):
            print("🧠 AI分析プロセス:")
            print(f"   {analysis['thinking_process']}")
            print()
        
        print("📊 演説評価:")
        print(f"  論理性: {analysis.get('logic', 50)}/100 {'⭐' * (analysis.get('logic', 50) // 20)}")
        print(f"  感情訴求: {analysis.get('emotion', 50)}/100 {'❤️' * (analysis.get('emotion', 50) // 20)}")
        print(f"  実現性: {analysis.get('feasibility', 50)}/100 {'✅' * (analysis.get('feasibility', 50) // 20)}")
        print(f"  リスク: {analysis.get('risk', 30)}/100 {'⚠️' * (analysis.get('risk', 30) // 20)}")
        
        print(f"\n🎯 支持率変動予測: {analysis.get('support_change', 0):+.1f}%")
        
        # 層別効果
        demo_effects = analysis.get('demographic_effects', {})
        print("\n👥 層別効果:")
        for group, effect in demo_effects.items():
            group_names = {
                'youth': '若年層',
                'elderly': '高齢者',
                'business': 'ビジネス層',
                'workers': '労働者'
            }
            print(f"  {group_names.get(group, group)}: {effect:+.1f}%")
        
        # 詳細分析
        print(f"\n📝 詳細分析:\n{analysis.get('analysis', '分析データなし')}")
        
        time.sleep(3)
    
    def _apply_speech_effects(self, analysis: Dict, venue: Dict):
        """演説効果を実際の支持率に反映"""
        base_effect = analysis.get('support_change', 0)
        venue_modifier = venue['difficulty']
        crowd_size_bonus = min(2.0, venue['size'] / 300)  # 人数ボーナス
        
        # 最終効果計算
        final_effect = (base_effect / venue_modifier) + (crowd_size_bonus * 0.5)
        
        # 支持率更新
        old_support = self.game.player_party.support_rate
        self.game.player_party.support_rate += final_effect
        self.game.player_party.support_rate = max(5.0, min(95.0, self.game.player_party.support_rate))
        
        # 結果通知
        change = self.game.player_party.support_rate - old_support
        print(f"\n📈 支持率変動: {old_support:.1f}% → {self.game.player_party.support_rate:.1f}% ({change:+.1f}%)")
        
        # 特別な反響
        if analysis.get('emotion', 50) > 85:
            print("🔥 聴衆が熱狂！動画が拡散される可能性があります")
            self.game.player_party.support_rate += 1.0
        elif analysis.get('risk', 30) > 70:
            print("⚠️ 発言が物議を醸しています...野党が攻撃材料にするかも")
            # 後でランダムイベントで攻撃される可能性
        
        time.sleep(2)
    
    def sns_campaign(self):
        """SNS運用システム"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【SNS戦略運用】")
        print("=" * 80)
        
        platforms = [
            {"name": "Twitter/X", "audience": "全世代", "reach": 1.0, "risk": 1.2},
            {"name": "Instagram", "audience": "若年層", "reach": 0.8, "risk": 0.9},
            {"name": "Facebook", "audience": "中高年", "reach": 0.7, "risk": 0.8},
            {"name": "TikTok", "audience": "Z世代", "reach": 1.3, "risk": 1.5},
            {"name": "YouTube", "audience": "幅広い層", "reach": 1.1, "risk": 0.7}
        ]
        
        print("\n投稿プラットフォームを選択:")
        for i, platform in enumerate(platforms, 1):
            print(f"{i}. {platform['name']} (対象:{platform['audience']} リーチ倍率:{platform['reach']:.1f}x リスク:{platform['risk']:.1f}x)")
        
        platform_choice = input("\nプラットフォーム選択 (1-5): ").strip()
        if not platform_choice.isdigit() or not 1 <= int(platform_choice) <= 5:
            print("❌ 無効な選択です")
            return
        
        selected_platform = platforms[int(platform_choice) - 1]
        
        print(f"\n📱 プラットフォーム: {selected_platform['name']}")
        print(f"🎯 主要対象: {selected_platform['audience']}")
        print("\n" + "-" * 80)
        print("✍️ 投稿内容を入力してください（Enter2回で終了）:")
        print("-" * 80)
        
        # 投稿内容入力
        post_lines = []
        empty_line_count = 0
        while True:
            line = input()
            if line.strip() == "":
                empty_line_count += 1
                if empty_line_count >= 2:
                    break
            else:
                empty_line_count = 0
                post_lines.append(line)
        
        post_content = '\n'.join(post_lines)
        if not post_content.strip():
            print("\n❌ 投稿内容が入力されていません")
            return
        
        print("\n" + "=" * 80)
        print("【SNS投稿分析中】")
        print("=" * 80)
        print(f"📝 投稿内容:\n{post_content}")
        print("\n⏳ バイラル度とリスクを分析中...")
        time.sleep(2)
        
        # LLMによるSNS投稿分析
        analysis = self._analyze_sns_post(post_content, selected_platform)
        
        # 結果表示と効果適用
        self._display_sns_results(analysis, selected_platform, post_content)
        self._apply_sns_effects(analysis, selected_platform)
        
        # 履歴保存
        self.sns_posts.append({
            'date': self.game.date,
            'platform': selected_platform['name'],
            'content': post_content,
            'analysis': analysis
        })
    
    def _analyze_sns_post(self, post_content: str, platform: Dict) -> Dict:
        """SNS投稿をLLMで分析"""
        if not self.game.llm.available:
            return self._fallback_sns_analysis(post_content, platform)
        
        prompt = f"""あなたはSNSマーケティングとリスク管理の専門家です。政治家の以下のSNS投稿を分析してください。

投稿内容: {post_content}
プラットフォーム: {platform['name']}
対象層: {platform['audience']}
現在の支持率: {self.game.player_party.support_rate:.1f}%

以下の項目を分析してJSON形式で回答してください:
1. バイラル潜在力（0-100）: 拡散される可能性
2. 炎上リスク（0-100）: 批判や炎上のリスク
3. エンゲージメント予測（0-100）: いいね・コメント等の反応
4. メッセージ明確性（0-100）: 伝えたい内容の明確さ
5. 感情的インパクト（0-100）: 読み手の心に響く度合い
6. 支持率への影響（-10から+10）
7. 年齢層別効果
8. リスク要因の詳細

{{"viral_potential": 数値, "flame_risk": 数値, "engagement": 数値, "clarity": 数値, "emotional_impact": 数値, "support_change": 数値, "age_effects": {{"teens": 数値, "twenties": 数値, "thirties": 数値, "forties": 数値, "fifties_plus": 数値}}, "risk_factors": ["リスク1", "リスク2"], "positive_factors": ["プラス1", "プラス2"], "analysis": "詳細分析"}}"""

        try:
            response = requests.post(
                self.game.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.6,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.game.llm.parse_llm_response(content)
                
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    if thinking:
                        result["thinking_process"] = thinking
                    return result
        except Exception as e:
            print(f"SNS分析エラー: {e}")
        
        return self._fallback_sns_analysis(post_content, platform)
    
    def _fallback_sns_analysis(self, post: str, platform: Dict) -> Dict:
        """LLM接続失敗時の基本SNS分析"""
        post_length = len(post)
        
        # プラットフォーム特性を考慮
        if platform['name'] == 'TikTok':
            viral_bonus = 20
            flame_risk = 40
        elif platform['name'] == 'Twitter/X':
            viral_bonus = 15
            flame_risk = 35
        else:
            viral_bonus = 10
            flame_risk = 25
        
        return {
            "viral_potential": min(90, viral_bonus + random.randint(20, 60)),
            "flame_risk": min(90, flame_risk + random.randint(0, 30)),
            "engagement": random.randint(40, 80),
            "clarity": random.randint(50, 85),
            "emotional_impact": random.randint(30, 80),
            "support_change": random.uniform(-3, 5),
            "age_effects": {
                "teens": random.uniform(-1, 4),
                "twenties": random.uniform(-1, 3),
                "thirties": random.uniform(-2, 2),
                "forties": random.uniform(-2, 2),
                "fifties_plus": random.uniform(-3, 1)
            },
            "risk_factors": ["表現の誤解", "政敵の攻撃材料"],
            "positive_factors": ["親しみやすさ", "率直さ"],
            "analysis": "基本分析モード（LLM未接続）"
        }
    
    def _display_sns_results(self, analysis: Dict, platform: Dict, post: str):
        """SNS投稿結果の表示"""
        print("\n" + "=" * 80)
        print("【SNS投稿結果分析】")
        print("=" * 80)
        
        # 思考プロセス表示
        if analysis.get('thinking_process'):
            print("🧠 AI分析プロセス:")
            print(f"   {analysis['thinking_process']}")
            print()
        
        print("📊 投稿分析結果:")
        viral = analysis.get('viral_potential', 50)
        flame = analysis.get('flame_risk', 30)
        engagement = analysis.get('engagement', 60)
        
        print(f"  🚀 バイラル度: {viral}/100 {'🔥' * (viral // 20)}")
        print(f"  ⚠️ 炎上リスク: {flame}/100 {'💥' * (flame // 20)}")
        print(f"  👍 エンゲージメント: {engagement}/100 {'❤️' * (engagement // 20)}")
        print(f"  📝 メッセージ明確性: {analysis.get('clarity', 70)}/100")
        print(f"  💫 感情的インパクト: {analysis.get('emotional_impact', 60)}/100")
        
        print(f"\n📈 支持率変動予測: {analysis.get('support_change', 0):+.1f}%")
        
        # 年齢層別効果
        age_effects = analysis.get('age_effects', {})
        if age_effects:
            print("\n👥 年齢層別効果:")
            age_names = {
                'teens': '10代',
                'twenties': '20代',
                'thirties': '30代',
                'forties': '40代',
                'fifties_plus': '50代以上'
            }
            for age, effect in age_effects.items():
                print(f"  {age_names.get(age, age)}: {effect:+.1f}%")
        
        # リスクとポジティブ要因
        risks = analysis.get('risk_factors', [])
        positives = analysis.get('positive_factors', [])
        
        if risks:
            print(f"\n⚠️ 潜在リスク: {', '.join(risks)}")
        if positives:
            print(f"✅ プラス要因: {', '.join(positives)}")
        
        print(f"\n📝 詳細分析:\n{analysis.get('analysis', '分析データなし')}")
        
        time.sleep(3)
    
    def _apply_sns_effects(self, analysis: Dict, platform: Dict):
        """SNS効果を実際の支持率に反映"""
        base_effect = analysis.get('support_change', 0)
        platform_reach = platform['reach']
        platform_risk = platform['risk']
        
        # バイラル効果
        viral_bonus = 0
        if analysis.get('viral_potential', 50) > 80:
            viral_bonus = 2.0
            print("\n🚀 投稿がバイラル拡散！大きな話題になっています")
        elif analysis.get('viral_potential', 50) > 60:
            viral_bonus = 1.0
            print("\n📈 投稿が順調に拡散中")
        
        # 炎上リスク
        flame_penalty = 0
        if analysis.get('flame_risk', 30) > 70:
            flame_penalty = -2.0
            print("\n🔥 投稿が炎上！批判コメントが殺到しています")
        elif analysis.get('flame_risk', 30) > 50:
            flame_penalty = -0.5
            print("\n⚠️ 一部で批判的な反応も見られます")
        
        # 最終効果計算
        final_effect = (base_effect * platform_reach) + viral_bonus + flame_penalty
        
        # 支持率更新
        old_support = self.game.player_party.support_rate
        self.game.player_party.support_rate += final_effect
        self.game.player_party.support_rate = max(5.0, min(95.0, self.game.player_party.support_rate))
        
        change = self.game.player_party.support_rate - old_support
        print(f"\n📊 支持率変動: {old_support:.1f}% → {self.game.player_party.support_rate:.1f}% ({change:+.1f}%)")
        
        time.sleep(2)
    
    def press_conference(self):
        """記者会見システム"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【記者会見】")
        print("=" * 80)
        
        # 会見タイプ選択
        conference_types = [
            {"name": "定例記者会見", "difficulty": 1.0, "questions": 5, "time_limit": 60},
            {"name": "緊急記者会見", "difficulty": 1.3, "questions": 8, "time_limit": 45},
            {"name": "政策発表会見", "difficulty": 1.1, "questions": 6, "time_limit": 90},
            {"name": "国際会見（通訳付）", "difficulty": 1.5, "questions": 4, "time_limit": 120},
            {"name": "党首討論前会見", "difficulty": 1.4, "questions": 7, "time_limit": 30}
        ]
        
        print("\n記者会見の種類を選択:")
        for i, conf_type in enumerate(conference_types, 1):
            print(f"{i}. {conf_type['name']} (難易度:{conf_type['difficulty']:.1f}x 質問数:{conf_type['questions']} 制限時間:{conf_type['time_limit']}分)")
        
        type_choice = input("\n会見選択 (1-5): ").strip()
        if not type_choice.isdigit() or not 1 <= int(type_choice) <= 5:
            print("❌ 無効な選択です")
            return
        
        selected_type = conference_types[int(type_choice) - 1]
        
        print(f"\n🎤 {selected_type['name']}を開始します")
        print(f"📰 報道陣: 政治部記者、経済記者、外信記者など")
        print("\n" + "=" * 80)
        
        # 質疑応答セッション
        total_score = 0
        responses = []
        
        for q_num in range(1, selected_type['questions'] + 1):
            question = self._generate_reporter_question(q_num, selected_type)
            print(f"\n【質問 {q_num}】")
            print(f"記者: {question}")
            print("\n" + "-" * 60)
            print("🎤 あなたの回答（Enter2回で終了）:")
            print("-" * 60)
            
            # 回答入力
            answer_lines = []
            empty_line_count = 0
            while True:
                line = input()
                if line.strip() == "":
                    empty_line_count += 1
                    if empty_line_count >= 2:
                        break
                else:
                    empty_line_count = 0
                    answer_lines.append(line)
            
            answer = '\n'.join(answer_lines)
            if not answer.strip():
                answer = "ノーコメントです。"
                print("（無回答のため自動応答）")
            
            # 回答分析
            print("\n⏳ 回答を分析中...")
            time.sleep(1)
            
            answer_analysis = self._analyze_conference_answer(question, answer)
            score = self._display_answer_feedback(answer_analysis, q_num)
            
            total_score += score
            responses.append({
                'question': question,
                'answer': answer,
                'analysis': answer_analysis,
                'score': score
            })
            
            time.sleep(2)
        
        # 総合評価
        self._display_conference_results(total_score, selected_type, responses)
        
        # 履歴保存
        self.press_conferences.append({
            'date': self.game.date,
            'type': selected_type['name'],
            'responses': responses,
            'total_score': total_score
        })
    
    def _generate_reporter_question(self, q_num: int, conf_type: Dict) -> str:
        """記者質問を生成"""
        question_pools = {
            1: [
                "現在の経済政策についてどう評価されますか？",
                "支持率低下についてコメントをお願いします",
                "野党の批判にどう応えますか？",
                "今後の政権運営方針を教えてください"
            ],
            2: [
                "連立政権の結束について心配の声がありますが？",
                "外交問題での政府の立場を明確にしてください",
                "予算案の見通しはいかがですか？",
                "党内の意見対立についてどう思われますか？"
            ],
            3: [
                "国民から厳しい批判を受けていますが、どう受け止めますか？",
                "政策の効果が見えないとの指摘について",
                "解散総選挙の可能性はありますか？",
                "官僚との関係についてお聞かせください"
            ]
        }
        
        # より高度な質問を後半で
        pool_key = min(3, (q_num - 1) // 2 + 1)
        base_questions = question_pools.get(pool_key, question_pools[1])
        
        return random.choice(base_questions)
    
    def _analyze_conference_answer(self, question: str, answer: str) -> Dict:
        """記者会見の回答をLLMで分析"""
        if not self.game.llm.available:
            return self._fallback_conference_analysis(answer)
        
        prompt = f"""あなたは政治ジャーナリストです。記者会見での以下の質疑を分析してください。

質問: {question}
回答: {answer}
現在の支持率: {self.game.player_party.support_rate:.1f}%

以下の項目を0-100で評価し、JSON形式で回答してください:
1. 明確性: 質問に対する回答の明確さ
2. 説得力: 論理的で納得できる内容か
3. 透明性: 情報開示の度合い
4. 安定感: 政治家としての信頼性
5. メディア対応力: 記者との適切なやりとり
6. リスク管理: 問題発言や失言のリスク
7. 支持率への影響（-10から+10）

{{"clarity": 数値, "persuasiveness": 数値, "transparency": 数値, "stability": 数値, "media_skill": 数値, "risk": 数値, "support_impact": 数値, "media_reaction": "メディアの反応予測", "public_reception": "世論の受け止め方", "analysis": "詳細分析"}}"""

        try:
            response = requests.post(
                self.game.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 800
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.game.llm.parse_llm_response(content)
                
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    if thinking:
                        result["thinking_process"] = thinking
                    return result
        except Exception as e:
            print(f"記者会見分析エラー: {e}")
        
        return self._fallback_conference_analysis(answer)
    
    def _fallback_conference_analysis(self, answer: str) -> Dict:
        """LLM接続失敗時の基本分析"""
        answer_length = len(answer)
        
        # 回答長による基本評価
        length_bonus = min(20, answer_length / 20)
        
        return {
            "clarity": random.randint(40, 80) + int(length_bonus / 2),
            "persuasiveness": random.randint(30, 75),
            "transparency": random.randint(35, 70),
            "stability": random.randint(45, 85),
            "media_skill": random.randint(40, 80),
            "risk": random.randint(15, 45),
            "support_impact": random.uniform(-2, 3),
            "media_reaction": "注意深く報道される見込み",
            "public_reception": "概ね冷静に受け止められる",
            "analysis": "基本分析モード（LLM未接続）"
        }
    
    def _display_answer_feedback(self, analysis: Dict, q_num: int) -> float:
        """回答フィードバックの表示"""
        print(f"\n📊 質問{q_num}の評価:")
        
        clarity = analysis.get('clarity', 60)
        persuasiveness = analysis.get('persuasiveness', 55)
        transparency = analysis.get('transparency', 50)
        
        print(f"  明確性: {clarity}/100 {'⭐' * (clarity // 20)}")
        print(f"  説得力: {persuasiveness}/100 {'💪' * (persuasiveness // 20)}")
        print(f"  透明性: {transparency}/100 {'🔍' * (transparency // 20)}")
        print(f"  安定感: {analysis.get('stability', 65)}/100")
        print(f"  メディア対応: {analysis.get('media_skill', 60)}/100")
        
        risk = analysis.get('risk', 25)
        if risk > 60:
            print(f"  ⚠️ リスク: {risk}/100 （問題発言の可能性）")
        
        # 思考プロセス表示
        if analysis.get('thinking_process'):
            print(f"🧠 AI分析: {analysis['thinking_process']}")
        
        score = (clarity + persuasiveness + transparency + analysis.get('stability', 65)) / 4
        return score
    
    def _display_conference_results(self, total_score: float, conf_type: Dict, responses: list):
        """記者会見の総合結果表示"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【記者会見　総合結果】")
        print("=" * 80)
        
        avg_score = total_score / len(responses)
        difficulty_adjusted = avg_score / conf_type['difficulty']
        
        print(f"\n🎤 会見種別: {conf_type['name']}")
        print(f"📊 総合スコア: {avg_score:.1f}/100")
        print(f"🎯 難易度調整後: {difficulty_adjusted:.1f}/100")
        
        # ランク判定
        if difficulty_adjusted >= 85:
            rank = "S"
            print("\n🏆 評価: S級 - 完璧な記者会見！メディアから高評価")
            support_bonus = 3.0
        elif difficulty_adjusted >= 70:
            rank = "A"
            print("\n⭐ 評価: A級 - 優秀な対応でした")
            support_bonus = 2.0
        elif difficulty_adjusted >= 55:
            rank = "B"
            print("\n👍 評価: B級 - 標準的な対応")
            support_bonus = 1.0
        elif difficulty_adjusted >= 40:
            rank = "C"
            print("\n😐 評価: C級 - やや物足りない内容")
            support_bonus = 0.0
        else:
            rank = "D"
            print("\n😞 評価: D級 - 問題のある会見でした")
            support_bonus = -1.5
        
        # 支持率変動
        total_support_change = 0
        for response in responses:
            total_support_change += response['analysis'].get('support_impact', 0)
        
        final_support_change = (total_support_change / len(responses)) + support_bonus
        
        old_support = self.game.player_party.support_rate
        self.game.player_party.support_rate += final_support_change
        self.game.player_party.support_rate = max(5.0, min(95.0, self.game.player_party.support_rate))
        
        print(f"\n📈 支持率変動: {old_support:.1f}% → {self.game.player_party.support_rate:.1f}% ({final_support_change:+.1f}%)")
        
        # メディア反応
        print(f"\n📰 メディア反応:")
        if avg_score >= 75:
            print("  主要各紙が好意的に報道")
        elif avg_score >= 50:
            print("  標準的な報道、特に問題視されず")
        else:
            print("  一部で批判的な論調も見られる")
        
        time.sleep(4)
    
    def political_debate(self):
        """政治討論会システム"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【政治討論会】")
        print("=" * 80)
        
        # 討論相手選択
        available_opponents = []
        for party in self.game.domestic.parties:
            if party.name != self.game.player_party.name:
                available_opponents.append(party)
        
        if not available_opponents:
            print("❌ 討論できる相手がいません")
            return
        
        print("\n討論相手を選択してください:")
        for i, opponent in enumerate(available_opponents, 1):
            difficulty = self._calculate_opponent_difficulty(opponent)
            print(f"{i}. {opponent.name} 党首 (支持率:{opponent.support_rate:.1f}% 難易度:{'★' * difficulty})")
        
        opponent_choice = input("\n相手選択: ").strip()
        if not opponent_choice.isdigit() or not 1 <= int(opponent_choice) <= len(available_opponents):
            print("❌ 無効な選択です")
            return
        
        opponent = available_opponents[int(opponent_choice) - 1]
        
        # 討論テーマ選択
        debate_themes = [
            {"name": "経済政策", "topics": ["税制改革", "財政健全化", "雇用創出", "物価対策"]},
            {"name": "社会保障", "topics": ["年金制度", "医療制度", "介護制度", "少子化対策"]},
            {"name": "外交・安全保障", "topics": ["日米同盟", "近隣諸国関係", "防衛予算", "国際協力"]},
            {"name": "環境・エネルギー", "topics": ["脱炭素", "原子力政策", "再生エネルギー", "環境規制"]},
            {"name": "教育・科学技術", "topics": ["教育制度改革", "研究開発", "デジタル化", "人材育成"]}
        ]
        
        print(f"\n🎯 討論相手: {opponent.name}")
        print("\n討論テーマを選択:")
        for i, theme in enumerate(debate_themes, 1):
            print(f"{i}. {theme['name']} ({', '.join(theme['topics'][:2])}など)")
        
        theme_choice = input("\nテーマ選択 (1-5): ").strip()
        if not theme_choice.isdigit() or not 1 <= int(theme_choice) <= 5:
            print("❌ 無効な選択です")
            return
        
        selected_theme = debate_themes[int(theme_choice) - 1]
        
        print(f"\n📺 【{selected_theme['name']}討論会】開始")
        print(f"司会: 本日は{selected_theme['name']}をテーマに討論していただきます")
        print("=" * 80)
        
        # 討論セッション
        debate_rounds = 3
        player_total_score = 0
        opponent_total_score = 0
        debate_history = []
        
        for round_num in range(1, debate_rounds + 1):
            topic = selected_theme['topics'][round_num - 1] if round_num <= len(selected_theme['topics']) else random.choice(selected_theme['topics'])
            
            print(f"\n【ラウンド {round_num}: {topic}】")
            print(f"司会: {topic}についてご意見をお聞かせください")
            
            # プレイヤーの発言
            print(f"\n🎤 あなた({self.game.player_party.name})の番です")
            print("発言内容を入力してください（Enter2回で終了）:")
            print("-" * 60)
            
            player_statement_lines = []
            empty_line_count = 0
            while True:
                line = input()
                if line.strip() == "":
                    empty_line_count += 1
                    if empty_line_count >= 2:
                        break
                else:
                    empty_line_count = 0
                    player_statement_lines.append(line)
            
            player_statement = '\n'.join(player_statement_lines)
            if not player_statement.strip():
                player_statement = f"{topic}について検討が必要だと考えています。"
                print("（無回答のため自動応答）")
            
            print(f"\n💬 あなた: {player_statement}")
            
            # 相手の反論生成
            opponent_response = self._generate_opponent_response(opponent, topic, player_statement)
            print(f"\n💬 {opponent.name}: {opponent_response}")
            
            # プレイヤーの再反論
            print(f"\n🎤 {opponent.name}の発言に対する反論をどうぞ")
            print("反論内容を入力してください（Enter2回で終了）:")
            print("-" * 60)
            
            counter_lines = []
            empty_line_count = 0
            while True:
                line = input()
                if line.strip() == "":
                    empty_line_count += 1
                    if empty_line_count >= 2:
                        break
                else:
                    empty_line_count = 0
                    counter_lines.append(line)
            
            counter_argument = '\n'.join(counter_lines)
            if not counter_argument.strip():
                counter_argument = "様々な観点から慎重に検討していきたいと思います。"
                print("（無回答のため自動応答）")
            
            print(f"\n💬 あなた（反論）: {counter_argument}")
            
            # ラウンド評価
            print("\n⏳ ラウンドを分析中...")
            time.sleep(2)
            
            round_analysis = self._analyze_debate_round(
                topic, player_statement, counter_argument, 
                opponent_response, opponent, selected_theme['name']
            )
            
            player_score, opponent_score = self._display_round_results(round_analysis, round_num, opponent)
            
            player_total_score += player_score
            opponent_total_score += opponent_score
            
            debate_history.append({
                'round': round_num,
                'topic': topic,
                'player_statement': player_statement,
                'player_counter': counter_argument,
                'opponent_response': opponent_response,
                'analysis': round_analysis,
                'scores': {'player': player_score, 'opponent': opponent_score}
            })
            
            time.sleep(2)
        
        # 討論総合結果
        self._display_debate_final_results(player_total_score, opponent_total_score, opponent, selected_theme, debate_history)
        
        # 履歴保存
        self.debates.append({
            'date': self.game.date,
            'opponent': opponent.name,
            'theme': selected_theme['name'],
            'player_score': player_total_score,
            'opponent_score': opponent_total_score,
            'history': debate_history
        })
    
    def _calculate_opponent_difficulty(self, opponent: PoliticalParty) -> int:
        """討論相手の難易度計算"""
        support_factor = opponent.support_rate / 20  # 支持率による
        seat_factor = opponent.total_seats / 100     # 議席数による
        
        difficulty = support_factor + seat_factor
        return max(1, min(5, int(difficulty)))
    
    def _generate_opponent_response(self, opponent: PoliticalParty, topic: str, player_statement: str) -> str:
        """相手の応答をLLMで生成"""
        if not self.game.llm.available:
            return self._fallback_opponent_response(opponent, topic)
        
        # 政党のイデオロギーに基づいた立場設定
        ideology_positions = {
            PoliticalIdeology.LEFT: "左派・リベラル的立場から",
            PoliticalIdeology.CENTER_LEFT: "中道左派の立場から",
            PoliticalIdeology.CENTER: "中道・現実主義的立場から",
            PoliticalIdeology.CENTER_RIGHT: "中道右派の立場から",
            PoliticalIdeology.RIGHT: "保守・右派的立場から"
        }
        
        stance = ideology_positions.get(opponent.ideology, "野党の立場から")
        
        prompt = f"""あなたは日本の政党「{opponent.name}」の党首です。{stance}、以下の発言に対して反論してください。

テーマ: {topic}
相手の発言: {player_statement}
あなたの政党支持率: {opponent.support_rate:.1f}%

150文字程度で、政党の立場に基づいた具体的で建設的な反論をしてください。攻撃的になりすぎず、政策的な代案も含めてください。"""

        try:
            response = requests.post(
                self.game.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 300
                },
                timeout=25
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.game.llm.parse_llm_response(content)
                return clean_response.strip()
        except Exception as e:
            print(f"討論応答生成エラー: {e}")
        
        return self._fallback_opponent_response(opponent, topic)
    
    def _fallback_opponent_response(self, opponent: PoliticalParty, topic: str) -> str:
        """LLM接続失敗時の基本応答"""
        generic_responses = [
            f"私たち{opponent.name}は{topic}について異なる考えを持っています。",
            f"現政権の{topic}政策は不十分であり、我が党はより良い解決策を提案します。",
            f"{topic}の問題は深刻です。我が党の政策こそが真の解決をもたらします。",
            f"国民の皆様は{topic}について我が党の方針を支持してくださると確信しています。"
        ]
        return random.choice(generic_responses)
    
    def _analyze_debate_round(self, topic: str, player_statement: str, player_counter: str, 
                            opponent_response: str, opponent: PoliticalParty, theme: str) -> Dict:
        """討論ラウンドをLLMで分析"""
        if not self.game.llm.available:
            return self._fallback_debate_analysis()
        
        prompt = f"""あなたは政治討論の専門評価者です。以下の討論ラウンドを分析してください。

テーマ: {theme} - {topic}
プレイヤー最初発言: {player_statement}
相手({opponent.name})の反論: {opponent_response}
プレイヤー反駁: {player_counter}

以下の項目を0-100で評価し、JSON形式で回答してください:
1. プレイヤーの論理性: 発言の筋道と根拠
2. プレイヤーの説得力: 聴衆への訴求力
3. 相手への対応力: 反論への適切な対処
4. 政策的具体性: 実現可能な政策提案
5. 感情的訴求: 聴衆の心に響く度合い
6. 相手の強さ: 討論相手のパフォーマンス
7. 聴衆の反応予測
8. 勝敗判定（プレイヤー視点で-10から+10）

{{"player_logic": 数値, "player_persuasion": 数値, "counter_ability": 数値, "policy_specifics": 数値, "emotional_appeal": 数値, "opponent_strength": 数値, "audience_reaction": "聴衆の反応", "round_verdict": 数値, "key_moments": ["印象的な瞬間1", "印象的な瞬間2"], "analysis": "詳細分析"}}"""

        try:
            response = requests.post(
                self.game.llm.api_url,
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 900
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                thinking, clean_response = self.game.llm.parse_llm_response(content)
                
                import re
                json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    if thinking:
                        result["thinking_process"] = thinking
                    return result
        except Exception as e:
            print(f"討論分析エラー: {e}")
        
        return self._fallback_debate_analysis()
    
    def _fallback_debate_analysis(self) -> Dict:
        """LLM接続失敗時の基本分析"""
        return {
            "player_logic": random.randint(45, 85),
            "player_persuasion": random.randint(40, 80),
            "counter_ability": random.randint(35, 75),
            "policy_specifics": random.randint(40, 85),
            "emotional_appeal": random.randint(30, 80),
            "opponent_strength": random.randint(50, 85),
            "audience_reaction": "注意深く聞いている",
            "round_verdict": random.uniform(-3, 5),
            "key_moments": ["政策論争", "感情的な応酬"],
            "analysis": "基本分析モード（LLM未接続）"
        }
    
    def _display_round_results(self, analysis: Dict, round_num: int, opponent: PoliticalParty) -> tuple[float, float]:
        """ラウンド結果表示"""
        print(f"\n📊 ラウンド{round_num}評価:")
        
        # 思考プロセス表示
        if analysis.get('thinking_process'):
            print(f"🧠 AI評価プロセス: {analysis['thinking_process']}")
        
        player_logic = analysis.get('player_logic', 60)
        player_persuasion = analysis.get('player_persuasion', 55)
        
        print(f"  あなたの論理性: {player_logic}/100 {'⭐' * (player_logic // 20)}")
        print(f"  あなたの説得力: {player_persuasion}/100 {'💪' * (player_persuasion // 20)}")
        print(f"  反論対応力: {analysis.get('counter_ability', 50)}/100")
        print(f"  政策具体性: {analysis.get('policy_specifics', 60)}/100")
        print(f"  相手の強さ: {analysis.get('opponent_strength', 65)}/100")
        
        verdict = analysis.get('round_verdict', 0)
        if verdict > 3:
            result = "🟢 あなたの勝利"
            player_score = 2.0
            opponent_score = 0.5
        elif verdict > 0:
            result = "🟡 わずかにあなたが優勢"
            player_score = 1.5
            opponent_score = 1.0
        elif verdict > -3:
            result = "🟡 互角の戦い"
            player_score = 1.0
            opponent_score = 1.0
        else:
            result = "🔴 相手が優勢"
            player_score = 0.5
            opponent_score = 2.0
        
        print(f"\n🏆 ラウンド結果: {result}")
        print(f"👥 聴衆の反応: {analysis.get('audience_reaction', '注意深く聞いている')}")
        
        key_moments = analysis.get('key_moments', [])
        if key_moments:
            print(f"🎯 印象的な瞬間: {', '.join(key_moments)}")
        
        return player_score, opponent_score
    
    def _display_debate_final_results(self, player_total: float, opponent_total: float, 
                                    opponent: PoliticalParty, theme: Dict, history: list):
        """討論の最終結果表示"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【討論会　最終結果】")
        print("=" * 80)
        
        print(f"\n🎯 テーマ: {theme['name']}")
        print(f"🆚 対戦相手: {opponent.name}")
        print(f"\n📊 最終スコア")
        print(f"  あなた: {player_total:.1f}点")
        print(f"  {opponent.name}: {opponent_total:.1f}点")
        
        # 勝敗判定と支持率変動
        if player_total > opponent_total + 1:
            print("\n🏆 【勝利】見事な討論でした！")
            support_change = random.uniform(2.5, 4.5)
            print("メディアから高評価、世論も好意的")
        elif player_total > opponent_total:
            print("\n🟢 【優勢勝ち】良い戦いでした")
            support_change = random.uniform(1.0, 2.5)
        elif abs(player_total - opponent_total) <= 0.5:
            print("\n🟡 【引き分け】互角の討論")
            support_change = random.uniform(-0.5, 1.0)
        else:
            print("\n🔴 【敗北】相手の方が説得力がありました")
            support_change = random.uniform(-2.5, -0.5)
            print("メディアからは厳しい評価も...")
        
        # 支持率変動
        old_support = self.game.player_party.support_rate
        self.game.player_party.support_rate += support_change
        self.game.player_party.support_rate = max(5.0, min(95.0, self.game.player_party.support_rate))
        
        print(f"\n📈 支持率変動: {old_support:.1f}% → {self.game.player_party.support_rate:.1f}% ({support_change:+.1f}%)")
        
        # 相手政党への影響
        opponent_change = -support_change * 0.6  # 相手は逆効果
        opponent.support_rate += opponent_change
        opponent.support_rate = max(5.0, min(80.0, opponent.support_rate))
        
        print(f"📊 {opponent.name}支持率への影響: {opponent_change:+.1f}%")
        
        time.sleep(3)

# ========================
# 選挙システム
# ========================

class ElectionSystem:
    """選挙システム - 総選挙、参議院選、補欠選挙"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
        
    def run_general_election(self) -> Dict[str, int]:
        """衆議院総選挙を実施"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【衆議院総選挙】")
        print("=" * 80)
        print("\n解散総選挙が実施されます！")
        time.sleep(2)
        
        # 各政党の選挙戦略
        election_results = {}
        total_seats = 465
        
        # プレイヤー政党の選挙運動
        print("\n" + "=" * 80)
        print("【選挙運動期間】")
        print("=" * 80)
        
        for round_num in range(3):
            self._campaign_round_general(round_num + 1)
        
        # 開票
        print("\n" + "=" * 80)
        print("【開票速報】")
        print("=" * 80)
        time.sleep(1)
        
        # 投票率
        turnout = random.uniform(50, 70)
        print(f"\n投票率: {turnout:.1f}%")
        
        # 議席配分計算
        all_parties = self._get_all_parties()
        
        # 小選挙区289議席
        small_district_seats = self._calculate_small_district(all_parties)
        
        # 比例代表176議席
        proportional_seats = self._calculate_proportional(all_parties)
        
        # 合計
        for party_name in all_parties.keys():
            election_results[party_name] = (
                small_district_seats.get(party_name, 0) + 
                proportional_seats.get(party_name, 0)
            )
        
        # 結果表示
        print("\n" + "=" * 80)
        print("【確定議席】")
        print("=" * 80)
        
        sorted_results = sorted(election_results.items(), key=lambda x: x[1], reverse=True)
        for party_name, seats in sorted_results:
            percentage = (seats / total_seats) * 100
            bar = "█" * int(percentage / 2)
            is_player = "👑" if party_name == self.game.player_party.name else ""
            print(f"{party_name:15s} {seats:3d}議席 {bar} {percentage:.1f}% {is_player}")
        
        # 政党データ更新
        self._update_party_seats(election_results)
        
        # 政局判定
        self._analyze_election_result(election_results)
        
        time.sleep(3)
        return election_results
    
    def _campaign_round_general(self, round_num: int):
        """総選挙の選挙運動ラウンド"""
        print(f"\n【第{round_num}週】")
        print("選挙運動を行います:")
        print("1. 街頭演説（全国遊説）")
        print("2. 政策討論会（テレビ出演）")
        print("3. SNS戦略（ネット世論）")
        print("4. 組織票固め（支持団体）")
        
        choice = input("\n選択: ").strip()
        
        boost = 0
        if choice == "1":
            print("\n📢 全国各地で街頭演説...")
            boost = random.uniform(2, 5)
            print(f"聴衆から大きな拍手！ +{boost:.1f}%")
        elif choice == "2":
            print("\n📺 党首討論に出演...")
            boost = random.uniform(1, 6)
            print(f"視聴者の評価が上昇！ +{boost:.1f}%")
        elif choice == "3":
            print("\n📱 SNSでメッセージ発信...")
            boost = random.uniform(1, 4)
            print(f"若年層の支持拡大！ +{boost:.1f}%")
        elif choice == "4":
            print("\n🤝 支持団体を訪問...")
            boost = random.uniform(2, 4)
            print(f"組織票の固めに成功！ +{boost:.1f}%")
        
        self.game.player_party.support_rate += boost
        time.sleep(1.5)
    
    def _get_all_parties(self) -> Dict[str, float]:
        """全政党の支持率を取得"""
        parties = {self.game.player_party.name: self.game.player_party.support_rate}
        
        # 野党支持率シミュレーション
        for party in self.game.domestic.parties:
            if party.name == self.game.player_party.name:
                continue
            parties[party.name] = party.support_rate
        
        # 支持率の正規化
        total = sum(parties.values())
        return {k: (v/total)*100 for k, v in parties.items()}
    
    def _calculate_small_district(self, parties: Dict[str, float]) -> Dict[str, int]:
        """小選挙区の議席配分"""
        seats = {party: 0 for party in parties.keys()}
        total_districts = 289
        
        for _ in range(total_districts):
            # 各選挙区で勝者を決定
            votes = {party: support + random.gauss(0, 5) 
                    for party, support in parties.items()}
            winner = max(votes.items(), key=lambda x: x[1])[0]
            seats[winner] += 1
        
        return seats
    
    def _calculate_proportional(self, parties: Dict[str, float]) -> Dict[str, int]:
        """比例代表の議席配分（ドント式）"""
        total_seats = 176
        seats = {party: 0 for party in parties.keys()}
        
        for _ in range(total_seats):
            quotients = {party: support / (seats[party] + 1) 
                        for party, support in parties.items()}
            winner = max(quotients.items(), key=lambda x: x[1])[0]
            seats[winner] += 1
        
        return seats
    
    def _update_party_seats(self, results: Dict[str, int]):
        """政党の議席数を更新"""
        player_seats = results.get(self.game.player_party.name, 0)
        self.game.player_party.lower_house_seats = player_seats
        self.game.player_party.total_seats = self.game.player_party.lower_house_seats + self.game.player_party.upper_house_seats

        for party in self.game.domestic.parties:
            seats = results.get(party.name, party.lower_house_seats)
            party.lower_house_seats = seats
            party.total_seats = party.lower_house_seats + party.upper_house_seats

        # 選挙後の経過ターンをリセット
        self.game.domestic.turns_since_election = 0
    
    def _analyze_election_result(self, results: Dict[str, int]):
        """選挙結果の分析"""
        player_seats = results.get(self.game.player_party.name, 0)
        total_seats = 465
        
        print("\n" + "=" * 80)
        print("【政局分析】")
        print("=" * 80)
        
        if player_seats >= 310:  # 3分の2
            print("\n� 圧倒的勝利！衆議院の3分の2を確保！")
            print("参議院の反対を押し切って法案を通せます！")
            self.game.is_prime_minister = True
            self.game.coalition_partners = []
            self._form_cabinet()
        elif player_seats >= 233:  # 過半数
            print("\n� 単独過半数獲得！政権奪取に成功しました！")
            self.game.is_prime_minister = True
            self.game.coalition_partners = []
            self._form_cabinet()
        elif player_seats + self._get_potential_coalition_seats() >= 233:
            print("\n🤝 連立政権の可能性があります")
            self._coalition_negotiation(results)
        else:
            print("\n😢 政権奪取には至りませんでした")
            print("野党として活動します")
            self.game.is_prime_minister = False
            self.game.coalition_partners = []
    
    def _get_potential_coalition_seats(self) -> int:
        """連立可能な政党の議席数"""
        coalition_seats = 0
        player_ideology = self.game.player_party.ideology.value
        
        for party in self.game.domestic.parties:
            if party.name == self.game.player_party.name:
                continue
            ideology_diff = abs(party.ideology.value - player_ideology)
            if ideology_diff <= 2:  # 近い思想の政党
                coalition_seats += party.lower_house_seats
        
        return coalition_seats
    
    def _coalition_negotiation(self, results: Dict[str, int]):
        """連立交渉"""
        print("\n" + "=" * 80)
        print("【連立交渉】")
        print("=" * 80)
        
        player_ideology = self.game.player_party.ideology.value
        potential_partners = []
        
        for party in self.game.domestic.parties:
            if party.name == self.game.player_party.name:
                continue
            ideology_diff = abs(party.ideology.value - player_ideology)
            if ideology_diff <= 2 and party.lower_house_seats > 0:
                potential_partners.append(party)
        
        if not potential_partners:
            print("\n連立可能な政党がありません")
            self.game.is_prime_minister = False
            return
        
        print("\n連立交渉可能な政党:")
        for i, party in enumerate(potential_partners, 1):
            print(f"{i}. {party.name} ({party.lower_house_seats}議席)")
        
        print("\n連立交渉を行いますか？ (y/n)")
        if input("> ").strip().lower() == 'y':
            # 最大の政党と交渉
            partner = max(potential_partners, key=lambda p: p.lower_house_seats)
            
            print(f"\n{partner.name}と連立交渉中...")
            time.sleep(2)
            
            # 交渉成功判定
            success_chance = 0.6 + (self.game.politicians[self.game.player_id].negotiation / 200)
            
            if random.random() < success_chance:
                print(f"\n✅ {partner.name}との連立合意に成功！")
                combined_seats = (self.game.player_party.lower_house_seats + 
                                partner.lower_house_seats)
                print(f"連立政権議席: {combined_seats}議席")
                
                if combined_seats >= 233:
                    print("\n🎉 連立政権を樹立しました！")
                    self.game.is_prime_minister = True
                    self.game.coalition_partners = [partner.name]
                    self._form_cabinet()
                else:
                    print("\n議席不足により政権奪取できませんでした")
                    self.game.is_prime_minister = False
                    self.game.coalition_partners = []
            else:
                print(f"\n❌ {partner.name}は連立を拒否しました")
                self.game.is_prime_minister = False
                self.game.coalition_partners = []
        else:
            self.game.is_prime_minister = False
            self.game.coalition_partners = []
    
    def _form_cabinet(self):
        """内閣組閣"""
        print("\n" + "=" * 80)
        print("【内閣組閣】")
        print("=" * 80)
        if self.game.is_prime_minister:
            print("\nあなたは内閣総理大臣に指名されました！")
            print("閣僚を任命します...")
            time.sleep(2)
            self.game.form_cabinet(self.game.coalition_partners)
        else:
            print("\n政権を獲得できなかったため組閣できません。")


# ========================
# 国会システム
# ========================

class DietSystem:
    """国会システム - 法案審議、委員会、採決"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
        self.current_session = "通常国会"
        self.session_days_remaining = 150
        
    def submit_bill(self, bill: Bill) -> bool:
        """法案を提出"""
        # 提出要件チェック
        if bill.sponsor_type == "議員":
            # 議員立法は20人以上の賛同が必要
            if bill.support_count < 20:
                print("\n❌ 賛同者が不足しています（20人以上必要）")
                return False
        
        # 法案をシステムに登録
        self.game.bills[bill.id] = bill
        bill.status = BillStatus.COMMITTEE
        bill.submitted_date = self.game.date
        
        # 委員会に付託
        committee = self._assign_to_committee(bill)
        print(f"\n✅ 法案を{committee.name}に付託しました")
        
        return True
    
    def _assign_to_committee(self, bill: Bill) -> Committee:
        """法案を適切な委員会に付託"""
        # 政策分野に応じた委員会
        committee_map = {
            PolicyArea.ECONOMY: "財務金融委員会",
            PolicyArea.EDUCATION: "文部科学委員会",
            PolicyArea.HEALTHCARE: "厚生労働委員会",
            PolicyArea.DEFENSE: "安全保障委員会",
            PolicyArea.ENVIRONMENT: "環境委員会",
        }
        
        committee_name = committee_map.get(bill.area, "内閣委員会")
        
        if committee_name not in self.game.committees:
            self.game.committees[committee_name] = Committee(
                name=committee_name,
                area=bill.area
            )
        
        committee = self.game.committees[committee_name]
        committee.current_bills.append(bill.id)
        bill.committee = committee_name
        
        return committee
    
    def debate_bill(self, bill_id: str) -> bool:
        """法案を審議"""
        if bill_id not in self.game.bills:
            return False
        
        bill = self.game.bills[bill_id]
        
        GameInitializer.clear_screen()
        print("=" * 80)
        print(f"【{bill.committee} - 法案審議】")
        print("=" * 80)
        print(f"\n法案: {bill.name}")
        print(f"内容: {bill.description}")
        print(f"予算: {bill.budget_required:.1f}兆円")
        print("\n" + "-" * 80)
        
        # 委員会審議
        print("\n【委員会審議】")
        print("野党から厳しい質問が予想されます")
        print("\n対応を選択:")
        print("1. 丁寧に答弁（時間かかるが支持率↑）")
        print("2. 簡潔に答弁（時間短縮）")
        print("3. 強行採決（支持率↓↓）")
        
        choice = input("\n選択: ").strip()
        
        if choice == "1":
            print("\n💬 丁寧な答弁を行っています...")
            time.sleep(2)
            bill.committee_votes_for += random.randint(15, 25)
            bill.committee_votes_against += random.randint(5, 15)
            self.game.player_party.support_rate += random.uniform(0.5, 1.5)
            
        elif choice == "2":
            print("\n⚡ 迅速に審議を進めています...")
            time.sleep(1)
            bill.committee_votes_for += random.randint(12, 20)
            bill.committee_votes_against += random.randint(8, 18)
            
        elif choice == "3":
            print("\n💥 強行採決！")
            print("野党が激しく反発しています！")
            time.sleep(1)
            bill.committee_votes_for += random.randint(10, 15)
            bill.committee_votes_against += random.randint(15, 25)
            self.game.player_party.support_rate -= random.uniform(2, 5)
        
        # 委員会採決
        if bill.committee_votes_for > bill.committee_votes_against:
            print(f"\n✅ 委員会可決 (賛成{bill.committee_votes_for} 反対{bill.committee_votes_against})")
            bill.status = BillStatus.LOWER_HOUSE
            return True
        else:
            print(f"\n❌ 委員会否決 (賛成{bill.committee_votes_for} 反対{bill.committee_votes_against})")
            bill.status = BillStatus.REJECTED
            return False
    
    def vote_in_diet(self, bill_id: str, house: str = "lower") -> bool:
        """本会議で採決"""
        if bill_id not in self.game.bills:
            return False
        
        bill = self.game.bills[bill_id]
        
        print("\n" + "=" * 80)
        print(f"【{'衆議院' if house == 'lower' else '参議院'}本会議 - 採決】")
        print("=" * 80)
        print(f"\n法案: {bill.name}")
        time.sleep(1)
        
        # 議席数に基づく投票
        if house == "lower":
            total_seats = 465
            ruling_seats = self.game.player_party.lower_house_seats
            
            # 連立政権の場合
            if hasattr(self.game, 'coalition_partners'):
                for partner_name in self.game.coalition_partners:
                    for party in self.game.domestic.parties:
                        if party.name == partner_name:
                            ruling_seats += party.lower_house_seats
            
            opposition_seats = total_seats - ruling_seats
            
            # 造反者シミュレーション
            rebellion_rate = 0.02 if bill.public_support > 60 else 0.08
            actual_votes_for = int(ruling_seats * (1 - rebellion_rate))
            
            # 野党の一部賛成もあり得る
            opposition_support_rate = max(0, (bill.public_support - 40) / 100)
            actual_votes_for += int(opposition_seats * opposition_support_rate)
            
            actual_votes_against = total_seats - actual_votes_for
            
            bill.lower_house_votes_for = actual_votes_for
            bill.lower_house_votes_against = actual_votes_against
            
        else:  # upper house
            total_seats = 248
            ruling_seats = self.game.player_party.upper_house_seats
            
            if hasattr(self.game, 'coalition_partners'):
                for partner_name in self.game.coalition_partners:
                    for party in self.game.domestic.parties:
                        if party.name == partner_name:
                            ruling_seats += party.upper_house_seats
            
            opposition_seats = total_seats - ruling_seats
            
            rebellion_rate = 0.03
            actual_votes_for = int(ruling_seats * (1 - rebellion_rate))
            opposition_support_rate = max(0, (bill.public_support - 45) / 100)
            actual_votes_for += int(opposition_seats * opposition_support_rate)
            
            actual_votes_against = total_seats - actual_votes_for
            
            bill.upper_house_votes_for = actual_votes_for
            bill.upper_house_votes_against = actual_votes_against
        
        # 結果発表
        votes_for = bill.lower_house_votes_for if house == "lower" else bill.upper_house_votes_for
        votes_against = bill.lower_house_votes_against if house == "lower" else bill.upper_house_votes_against
        
        print(f"\n投票結果:")
        print(f"  賛成: {votes_for}票")
        print(f"  反対: {votes_against}票")
        
        if votes_for > votes_against:
            print(f"\n✅ {'衆議院' if house == 'lower' else '参議院'}可決！")
            
            if house == "lower":
                bill.status = BillStatus.UPPER_HOUSE
            else:
                bill.status = BillStatus.PASSED
                bill.passed_date = self.game.date
                self._implement_bill(bill)
            
            return True
        else:
            print(f"\n❌ {'衆議院' if house == 'lower' else '参議院'}否決")
            
            if house == "lower":
                bill.status = BillStatus.REJECTED
            else:
                # 参議院否決 → 衆議院の3分の2で再可決可能
                if self.game.player_party.lower_house_seats >= 310:
                    print("\n⚡ 衆議院の3分の2で再可決が可能です")
                    print("再可決を行いますか？ (y/n)")
                    if input("> ").strip().lower() == 'y':
                        print("\n🔨 衆議院で再可決！")
                        bill.status = BillStatus.PASSED
                        self.game.player_party.support_rate -= 3  # 強行採決ペナルティ
                        self._implement_bill(bill)
                        return True
                
                bill.status = BillStatus.REJECTED
            
            return False
    
    def _implement_bill(self, bill: Bill):
        """法案を政策として実施"""
        print(f"\n🎊 法案「{bill.name}」が成立しました！")
        
        # 政策として登録
        policy = Policy(
            name=bill.name,
            area=bill.area,
            cost=bill.budget_required,
            effect_on_economy=bill.expected_effects.get('economy', 0),
            effect_on_happiness=bill.expected_effects.get('happiness', 0),
            effect_on_support=bill.expected_effects.get('support', 0),
            implementation_time=8
        )
        
        self.game.active_policies.append(policy)
        time.sleep(2)


# ========================
# 野党AIシステム
# ========================

class OppositionAI:
    """野党の行動をシミュレート"""
    
    def __init__(self, game: 'PoliticalSimulator'):
        self.game = game
    
    def simulate_opposition_activities(self):
        """野党の活動をシミュレート"""
        for party in self.game.domestic.parties:
            if party.name == self.game.player_party.name:
                continue
            
            # 支持率変動
            self._update_party_support(party)
            
            # 野党の戦略
            if random.random() < 0.3:
                self._opposition_action(party)
            
            # 政党の興亡
            if random.random() < 0.05:
                self._party_dynamics(party)
    
    def _update_party_support(self, party: PoliticalParty):
        """野党支持率の更新"""
        # 与党支持率との逆相関
        player_support_change = self.game.player_party.support_rate - party.support_rate
        
        # 野党は与党の失敗で支持率が上がる
        if self.game.player_party.support_rate < 40:
            party.support_rate += random.uniform(1, 3)
        elif self.game.player_party.support_rate > 60:
            party.support_rate -= random.uniform(0.5, 2)
        
        # 自然変動
        party.support_rate += random.gauss(0, 1)
        party.support_rate = max(5, min(50, party.support_rate))
    
    def _opposition_action(self, party: PoliticalParty):
        """野党の具体的行動"""
        actions = [
            "内閣不信任案の検討",
            "政策提言の発表",
            "スキャンダル追及",
            "連立交渉の模索",
            "党勢拡大キャンペーン"
        ]
        
        action = random.choice(actions)
        
        if action == "内閣不信任案の検討":
            if self.game.player_party.support_rate < 30:
                print(f"\n⚠️ {party.name}が内閣不信任案を提出する構え！")
                self.game.player_party.support_rate -= 1
                
        elif action == "政策提言の発表":
            print(f"\n📰 {party.name}が新政策を発表")
            party.support_rate += random.uniform(0.5, 2)
            
        elif action == "スキャンダル追及":
            if random.random() < 0.3:
                print(f"\n💥 {party.name}が政権のスキャンダルを追及！")
                self.game.player_party.support_rate -= random.uniform(1, 3)
                
        elif action == "党勢拡大キャンペーン":
            print(f"\n📣 {party.name}が支持拡大キャンペーン")
            party.support_rate += random.uniform(1, 2.5)
    
    def _party_dynamics(self, party: PoliticalParty):
        """政党の興亡"""
        if party.support_rate < 3 and party.lower_house_seats < 5:
            # 政党消滅
            print(f"\n💔 {party.name}が解党しました")
            self.game.domestic.parties.remove(party)
            
        elif party.support_rate > 15 and random.random() < 0.1:
            # 政党分裂
            print(f"\n⚡ {party.name}から新党が分離！")
            self._create_new_party(party)
    
    def _create_new_party(self, origin_party: PoliticalParty):
        """新党を作成"""
        new_party_names = ["未来の党", "希望の党", "国民の党", "維新の会", "民主の党"]
        new_name = random.choice(new_party_names)
        name_suffix = 1
        existing_names = {p.name for p in self.game.domestic.parties}
        existing_names.add(self.game.player_party.name)
        while new_name in existing_names:
            new_name = f"{random.choice(new_party_names)}{name_suffix}"
            name_suffix += 1
        
        new_party = PoliticalParty(
            name=new_name,
            short_name=new_name[:3],
            founded_year=self.game.date.year,
            ideology=origin_party.ideology,
            lower_house_seats=origin_party.lower_house_seats // 3,
            upper_house_seats=origin_party.upper_house_seats // 3,
            total_seats=0,
            support_rate=origin_party.support_rate / 2
        )
        new_party.total_seats = new_party.lower_house_seats + new_party.upper_house_seats
        
        # 元の政党の議席を削減
        origin_party.lower_house_seats = origin_party.lower_house_seats * 2 // 3
        origin_party.upper_house_seats = origin_party.upper_house_seats * 2 // 3
        origin_party.support_rate *= 0.7
        origin_party.total_seats = origin_party.lower_house_seats + origin_party.upper_house_seats
        
        self.game.domestic.parties.append(new_party)
        print(f"  {new_name}が結成されました（{new_party.lower_house_seats}議席）")


class PoliticalSimulator:
    """メインゲームクラス"""
    
    def __init__(self, player_name: str = "政治家", party_name: str = "新政党",
                 party_short_name: str = "新党", ideology: PoliticalIdeology = PoliticalIdeology.CENTER,
                 manifesto: List[str] = None, difficulty: str = "2"):
        
        # プレイヤー情報
        self.player_name = player_name
        self.player_id = "player_001"
        self.difficulty = difficulty
        
        # ゲーム状態
        self.turn = 0
        self.date = datetime(2025, 1, 1)
        self.game_over = False
        self.victory = False
        self.is_prime_minister = False
        self.tutorial_complete = False
        
        # システム初期化
        self.economy = EconomicSystem()
        self.diplomacy = DiplomacySystem()
        self.domestic = DomesticSystem()
        self.llm = LLMIntegration()
        
        # プレイヤー政党
        self.player_party = PoliticalParty(
            name=party_name,
            short_name=party_short_name,
            founded_year=2025,
            ideology=ideology,
            lower_house_seats=0,
            upper_house_seats=0,
            support_rate=30.0,
            party_leader_id=self.player_id,
            manifesto=manifesto or ["経済成長", "社会福祉", "外交強化"]
        )

        # 難易度に応じた初期支持率・議席
        difficulty_support = {
            "1": 28.0,
            "2": 22.0,
            "3": 18.0,
            "4": 15.0
        }
        base_support = difficulty_support.get(self.difficulty, 22.0)
        self.player_party.support_rate = base_support
        self.player_party.lower_house_seats = 35 if base_support >= 22 else 20
        self.player_party.upper_house_seats = 12 if base_support >= 22 else 6
        self.player_party.total_seats = self.player_party.lower_house_seats + self.player_party.upper_house_seats
        
        # 政治家データ
        self.politicians: Dict[str, Politician] = {}
        self.factions: Dict[str, Faction] = {}
        self.bills: Dict[str, Bill] = {}
        self.committees: Dict[str, Committee] = {}
        
        # プレイヤー政治家作成
        self._create_player_politician()

        # 内政初期化と諸システム
        self.coalition_partners: List[str] = []
        self.domestic.setup_initial_state(self.player_party)
        self.election_system = ElectionSystem(self)
        self.diet_system = DietSystem(self)
        self.opposition_ai = OppositionAI(self)
        self.public_activity = PublicActivitySystem(self)
        
        # 新しい戦略的システム
        self.event_manager = EventManager(self)
        self.public_opinion = PublicOpinionSimulator(self)
        self.game_state = GameState.PLAYING
        self.pending_actions: queue.Queue = queue.Queue()
        self.action_points = 100  # アクションポイント制
        self.strategic_resources = {
            "political_capital": 50,
            "media_influence": 30,
            "international_standing": 40,
            "economic_credibility": 45
        }

        # 活動中の政策
        self.active_policies: List[Policy] = []
        self.policy_history: List[Dict] = []
        
        # 50の政治ゲーム要素
        self.game_elements = [
            "GDP管理", "税制改革", "財政政策", "金融政策", "貿易政策",
            "外交関係", "軍事防衛", "同盟管理", "国際交渉", "領土問題",
            "支持率管理", "世論調査", "選挙制度", "政党政治", "連立政権",
            "内閣人事", "スキャンダル対応", "メディア対策", "演説システム", "政治資金",
            "教育政策", "医療制度", "年金改革", "社会保障", "福祉政策",
            "環境政策", "エネルギー政策", "気候変動対策", "災害対応", "インフラ整備",
            "科学技術振興", "イノベーション", "産業政策", "農業政策", "労働政策",
            "都道府県管理", "地方自治", "人口動態", "少子高齢化", "移民政策",
            "治安維持", "司法改革", "憲法改正", "国家安全保障", "情報戦略",
            "国際機関", "国連外交", "経済制裁", "人権問題", "文化外交"
        ]
        
    def _create_player_politician(self):
        """プレイヤー政治家を作成"""
        self.politicians[self.player_id] = Politician(
            id=self.player_id,
            name=self.player_name,
            age=45,
            party=self.player_party.name,
            faction="主流派",
            ideology=self.player_party.ideology,
            district="東京1区",
            charisma=random.uniform(70, 85),
            policy_skill=random.uniform(65, 80),
            negotiation=random.uniform(60, 75),
            speech=random.uniform(70, 85),
            management=random.uniform(65, 80),
            position="党首",
            terms_served=1
        )
        
    def show_status(self):
        os.system('clear' if os.name != 'nt' else 'cls')
        print("="*70)
        print(f"📅 {self.date.strftime('%Y年%m月')} (ターン {self.turn})")
        print("="*70)
        
        print(f"\n【国内状況】")
        print(f"  支持率: {self.domestic.national_support:.1f}% {'🎯' if self.domestic.national_support >= 80 else ''}")
        print(f"  国民幸福度: {self.domestic.national_happiness:.2f}/10 {'🎯' if self.domestic.national_happiness >= 8 else ''}")
        
        print(f"\n【経済指標】")
        print(f"  GDP: {self.economy.gdp:.1f}兆円 (成長率: {self.economy.growth_rate:.2f}%)")
        print(f"  失業率: {self.economy.unemployment_rate:.1f}%")
        print(f"  インフレ率: {self.economy.inflation_rate:.1f}%")
        print(f"  国家債務: {self.economy.national_debt:.0f}兆円 (GDP比: {self.economy.national_debt/self.economy.gdp*100:.0f}%)")
        print(f"  税収: {self.economy.tax_revenue:.1f}兆円")
        print(f"  株価: {self.economy.stock_index:.0f}円")
        print(f"  為替: {self.economy.yen_rate:.1f}円/ドル")
        
        print(f"\n【実行中の政策】 {len(self.active_policies)}件")
        for p in self.active_policies[:3]:
            print(f"  • {p.name} (残り{p.implementation_time}ターン)")
            
    def show_strategic_dashboard(self):
        """戦略ダッシュボード表示"""
        print("\n" + "="*80)
        print("【政治戦略ダッシュボード】")
        print("="*80)
        
        # 基本情報
        print(f"日時: {self.date.strftime('%Y年%m月%d日')} | ターン: {self.turn}")
        print(f"地位: {'首相' if self.is_prime_minister else '野党党首'} | 支持率: {self.player_party.support_rate:.1f}%")
        print(f"アクションポイント: {self.action_points}/100")
        
        # 戦略的リソース
        print(f"\n【戦略リソース】")
        print(f"政治的影響力: {self.strategic_resources['political_capital']}/100")
        print(f"メディア影響力: {self.strategic_resources['media_influence']}/100") 
        print(f"国際的地位: {self.strategic_resources['international_standing']}/100")
        print(f"経済的信頼: {self.strategic_resources['economic_credibility']}/100")
        
        # アクティブなイベント
        if self.event_manager.active_events:
            print(f"\n【緊急事案】 ({len(self.event_manager.active_events)}件)")
            for event in self.event_manager.active_events[:3]:  # 最大3件表示
                days_left = (event.expires_at - self.date).days
                urgency_mark = "!" * event.urgency.value
                print(f"  {urgency_mark} {event.title} (残り{days_left}日)")
        
        print("\n" + "-"*80)
        print("【行動選択】")
        print("1. 政策立案・実行")
        print("2. 公共活動 (街頭演説、SNS、記者会見など)")
        print("3. 政治交渉 (連立、法案調整など)")
        print("4. 危機対応 (緊急事案への対処)")
        print("5. 戦略分析 (AIによる情勢分析)")
        print("6. 情報収集 (世論、野党動向など)")
        print("7. 国際活動 (外交、国際会議など)")
        print("8. 自由行動 (独自の戦略実行)")
        print("S. セーブ")
        print("L. ロード")
        print("0. 時間経過 (イベント進行)")
        print("Q. ゲーム終了")
        
    def economic_policy_menu(self):
        print("\n【経済政策】")
        print("1. 財政出動 (10兆円)")
        print("2. 減税政策")
        print("3. 規制緩和")
        print("4. 金融緩和")
        print("5. インフラ投資")
        print("6. イノベーション支援")
        print("7. 中小企業支援")
        print("0. 戻る")
        
        choice = input("\n選択: ")
        
        policies_map = {
            "1": Policy("財政出動", PolicyArea.ECONOMY, 10, 2, 0.5, 1, 4),
            "2": Policy("減税政策", PolicyArea.ECONOMY, 5, 1.5, 1, 3, 4),
            "3": Policy("規制緩和", PolicyArea.ECONOMY, 1, 1, 0.2, -1, 6),
            "4": Policy("金融緩和", PolicyArea.ECONOMY, 0, 0.8, 0, 0.5, 2),
            "5": Policy("インフラ投資", PolicyArea.INFRASTRUCTURE, 15, 1.5, 0.8, 0, 8),
            "6": Policy("イノベーション支援", PolicyArea.TECHNOLOGY, 3, 1, 0.3, 0.5, 6),
            "7": Policy("中小企業支援", PolicyArea.ECONOMY, 2, 0.8, 0.5, 1, 4),
        }
        
        if choice in policies_map:
            policy = policies_map[choice]
            if self.economy.budget >= policy.cost:
                self.active_policies.append(policy)
                self.economy.budget -= policy.cost
                print(f"\n✅ {policy.name}を実施しました（コスト: {policy.cost}兆円）")
                time.sleep(1.5)
            else:
                print("\n❌ 予算不足です")
                time.sleep(1.5)
    
    def diplomacy_menu(self):
        print("\n【外交・防衛】")
        print("対象国を選択:")
        for i, (name, country) in enumerate(self.diplomacy.countries.items(), 1):
            status = "🤝" if country.relationship > 50 else "⚠️" if country.relationship > 0 else "💥"
            print(f"{i}. {name} {status} (関係: {country.relationship:.0f})")
        print("0. 戻る")
        
        choice = input("\n選択: ")
        if choice.isdigit() and 1 <= int(choice) <= len(self.diplomacy.countries):
            country_name = list(self.diplomacy.countries.keys())[int(choice)-1]
            
            print(f"\n{country_name}への外交行動:")
            print("1. 関係改善")
            print("2. 貿易協定")
            print("3. 軍事協力")
            print("4. 経済支援")
            
            action_choice = input("選択: ")
            actions = {"1": "improve_relations", "2": "trade_agreement", 
                      "3": "military_cooperation", "4": "economic_aid"}
            
            if action_choice in actions:
                result = self.diplomacy.conduct_diplomacy(country_name, actions[action_choice], 1.0)
                print(f"\n{result['message']}")
                time.sleep(2)
    
    def domestic_policy_menu(self):
        print("\n【内政・社会政策】")
        print("1. 教育改革")
        print("2. 医療制度改革")
        print("3. 年金制度改革")
        print("4. 子育て支援")
        print("5. 環境政策")
        print("6. 労働改革")
        print("0. 戻る")
        
        choice = input("\n選択: ")
        
        policies_map = {
            "1": Policy("教育改革", PolicyArea.EDUCATION, 5, 0.5, 2, 1, 8),
            "2": Policy("医療制度改革", PolicyArea.HEALTHCARE, 8, 0.3, 2.5, 2, 8),
            "3": Policy("年金制度改革", PolicyArea.WELFARE, 10, -0.5, 1, -5, 12),
            "4": Policy("子育て支援", PolicyArea.WELFARE, 3, 0.2, 1.5, 2, 4),
            "5": Policy("環境政策", PolicyArea.ENVIRONMENT, 4, 0.3, 1, 0, 6),
            "6": Policy("労働改革", PolicyArea.LABOR, 2, 1, 0.5, -2, 6),
        }
        
        if choice in policies_map:
            policy = policies_map[choice]
            if self.economy.budget >= policy.cost:
                self.active_policies.append(policy)
                self.economy.budget -= policy.cost
                print(f"\n✅ {policy.name}を実施しました")
                time.sleep(1.5)
            else:
                print("\n❌ 予算不足です")
                time.sleep(1.5)
    
    def speech_menu(self):
        print("\n【演説・広報活動】")
        print("1. 経済政策について演説")
        print("2. 外交政策について演説")
        print("3. 社会保障について演説")
        print("4. 国家ビジョンについて演説")
        print("5. カスタム演説（LLM使用）")
        print("0. 戻る")
        
        choice = input("\n選択: ")
        
        topics = {
            "1": "経済成長戦略",
            "2": "平和外交",
            "3": "全世代型社会保障",
            "4": "新しい日本のビジョン"
        }
        
        if choice in topics:
            context = {
                "support": self.domestic.national_support,
                "gdp_growth": self.economy.growth_rate,
                "unemployment": self.economy.unemployment_rate
            }
            print("\n📢 演説を行っています...\n")
            speech = self.llm.generate_speech(topics[choice], context)
            print(f"「{speech}」\n")
            
            # 演説効果
            effect = random.gauss(2, 1)
            self.domestic.national_support += effect
            print(f"支持率が{effect:.1f}%変動しました")
            time.sleep(3)
            
        elif choice == "5":
            topic = input("\n演説テーマを入力: ")
            context = {
                "support": self.domestic.national_support,
                "gdp_growth": self.economy.growth_rate,
                "unemployment": self.economy.unemployment_rate
            }
            print("\n📢 演説を作成しています...\n")
            speech = self.llm.generate_speech(topic, context)
            print(f"「{speech}」\n")
            effect = random.gauss(1.5, 1.5)
            self.domestic.national_support += effect
            print(f"支持率が{effect:.1f}%変動しました")
            time.sleep(3)
    
    def cabinet_menu(self):
        print("\n【内閣・人事管理】")
        for i, member in enumerate(self.domestic.cabinet, 1):
            loyalty_icon = "🟢" if member.loyalty > 70 else "🟡" if member.loyalty > 40 else "🔴"
            print(f"{i}. {member.name} {loyalty_icon}")
            print(f"   能力: {member.competence:.0f} | 忠誠: {member.loyalty:.0f} | スキャンダルリスク: {member.scandal_risk:.1f}%")
        
        print("\n1. 大臣を交代")
        print("2. 内閣改造")
        print("0. 戻る")
        
        choice = input("\n選択: ")
        
        if choice == "1":
            idx = input("交代する大臣の番号: ")
            if idx.isdigit() and 1 <= int(idx) <= len(self.domestic.cabinet):
                old_member = self.domestic.cabinet[int(idx)-1]
                new_member = CabinetMember(
                    f"新{old_member.ministry}大臣",
                    old_member.ministry,
                    random.gauss(70, 10),
                    random.gauss(80, 10),
                    random.gauss(3, 2)
                )
                self.domestic.cabinet[int(idx)-1] = new_member
                print(f"\n✅ {old_member.name}を{new_member.name}に交代しました")
                self.domestic.national_support += random.gauss(-2, 3)
                time.sleep(2)
                
        elif choice == "2":
            print("\n🔄 内閣改造を実施します...")
            for i in range(len(self.domestic.cabinet)):
                if random.random() < 0.4:
                    member = self.domestic.cabinet[i]
                    self.domestic.cabinet[i] = CabinetMember(
                        f"新{member.ministry}大臣",
                        member.ministry,
                        random.gauss(70, 10),
                        random.gauss(80, 10),
                        random.gauss(3, 2)
                    )
            self.domestic.national_support += random.gauss(0, 5)
            print("✅ 内閣改造が完了しました")
            time.sleep(2)
    
    def show_prefectures(self):
        print("\n【都道府県状況】")
        print("-"*70)
        for name, pref in list(self.domestic.prefectures.items())[:10]:
            print(f"{name:6s} | 支持率: {pref.support_rate:5.1f}% | 幸福度: {pref.happiness:.1f} | 失業率: {pref.unemployment_rate:.1f}%")
            print(f"        | 人口: {pref.population//10000:4d}万人 | GDP: {pref.gdp:.0f}兆円")
        print("-"*70)
        input("\nEnterで戻る...")
    
    def show_international(self):
        print("\n【国際情勢】")
        print("-"*70)
        for name, country in self.diplomacy.countries.items():
            relation_status = "同盟" if country.alliance_level >= 4 else "友好" if country.relationship > 50 else "中立" if country.relationship > 0 else "敵対"
            print(f"{name:15s} | 関係: {country.relationship:6.1f} ({relation_status})")
            print(f"                | 経済力: {country.economic_power:.0f} | 軍事力: {country.military_power:.0f}")
            print(f"                | 貿易: {country.trade_volume:.0f}億ドル | 同盟Lv: {country.alliance_level}")
            if country.territorial_disputes:
                print(f"                | ⚠️ 領土問題あり")
        print("-"*70)
        input("\nEnterで戻る...")
    
    def show_detailed_report(self):
        print("\n" + "="*70)
        print("【詳細レポート】")
        print("="*70)
        
        print("\n📊 政党支持率:")
        for party in self.domestic.parties:
            bar = "█" * int(party.support_rate / 2)
            print(f"  {party.name:12s} {bar} {party.support_rate:.1f}% ({party.seats}議席)")
        
        print("\n💰 財政状況:")
        print(f"  歳入: {self.economy.tax_revenue:.1f}兆円")
        print(f"  歳出: {self.economy.budget:.1f}兆円")
        print(f"  収支: {self.economy.tax_revenue - self.economy.budget:+.1f}兆円")
        print(f"  債務残高: {self.economy.national_debt:.0f}兆円")
        print(f"  債務対GDP比: {self.economy.national_debt/self.economy.gdp*100:.0f}%")
        
        print("\n📈 経済トレンド:")
        if len(self.policy_history) > 0:
            recent = self.policy_history[-5:]
            avg_growth = sum(p.get("gdp_growth", 0) for p in recent) / len(recent)
            print(f"  平均成長率: {avg_growth:.2f}%")
        
        print("\n🎯 目標達成状況:")
        support_progress = min(100, self.domestic.national_support / 80 * 100)
        happiness_progress = min(100, self.domestic.national_happiness / 8 * 100)
        print(f"  支持率: [{self._progress_bar(support_progress, 30)}] {support_progress:.0f}%")
        print(f"  幸福度: [{self._progress_bar(happiness_progress, 30)}] {happiness_progress:.0f}%")
        
        input("\nEnterで戻る...")
    
    def _progress_bar(self, percentage: float, width: int = 20) -> str:
        filled = int(width * percentage / 100)
        return "█" * filled + "░" * (width - filled)
    
    def llm_policy_analysis(self):
        print("\n【LLM政策分析】")
        
        if not self.llm.available:
            print("\n❌ LMstudioに接続できません")
            print("http://localhost:1234 でLMstudioを起動してください")
            input("\nEnterで戻る...")
            return
        
        print("\n自然言語で政策を入力してください")
        print("例: 消費税を8%に引き下げて、教育予算を倍増させる")
        policy_text = input("\n政策: ")
        
        if not policy_text.strip():
            return
        
        print("\n🤖 AIが政策を分析しています...\n")
        
        context = {
            "gdp_growth": self.economy.growth_rate,
            "unemployment": self.economy.unemployment_rate,
            "support": self.domestic.national_support,
            "debt": self.economy.national_debt
        }
        
        analysis = self.llm.analyze_policy_impact(policy_text, context)
        
        print("="*70)
        print("【分析結果】")
        print("="*70)
        print(f"\n政策: {policy_text}\n")
        print(f"経済への影響:     {analysis['economy']:+.1f}/10")
        print(f"幸福度への影響:   {analysis['happiness']:+.1f}/10")
        print(f"支持率への影響:   {analysis['support']:+.1f}/10")
        print(f"実施コスト:       {analysis['cost']:.1f}兆円")
        print(f"\n詳細分析:\n{analysis['analysis']}")
        
        print("\n\nこの政策を実施しますか？ (y/n)")
        if input().lower() == 'y':
            if self.economy.budget >= analysis['cost']:
                custom_policy = Policy(
                    policy_text[:30],
                    PolicyArea.ECONOMY,
                    analysis['cost'],
                    analysis['economy'],
                    analysis['happiness'],
                    analysis['support'],
                    random.randint(4, 8)
                )
                self.active_policies.append(custom_policy)
                self.economy.budget -= analysis['cost']
                print(f"\n✅ 政策を実施しました")
            else:
                print(f"\n❌ 予算不足です（必要: {analysis['cost']:.1f}兆円、利用可能: {self.economy.budget:.1f}兆円）")
        
        time.sleep(2)

    def parliament_menu(self):
        while True:
            print("\n" + "=" * 70)
            print("【国会・選挙管理】")
            print("=" * 70)
            print("1. 国会勢力図を確認")
            print("2. 法案を起草・提出")
            print("3. 委員会審議を進める")
            print("4. 本会議で採決する")
            print("5. 衆議院を解散して総選挙")
            print("0. 戻る")

            choice = input("\n選択: ").strip()

            if choice == "1":
                self._display_parliament_status()
            elif choice == "2":
                self._create_bill_menu()
            elif choice == "3":
                self._committee_menu()
            elif choice == "4":
                self._conduct_plenary_vote()
            elif choice == "5":
                if self.is_prime_minister:
                    self.force_general_election("内閣による解散総選挙")
                else:
                    print("\n❌ 与党でないため解散権がありません")
                    time.sleep(1.5)
            elif choice == "0":
                break
            else:
                print("\n❌ 無効な選択です")
                time.sleep(1)

    def _display_parliament_status(self):
        print("\n" + "-" * 70)
        print("【国会勢力図】")
        print("-" * 70)
        parties = {}
        for party in [self.player_party] + self.domestic.parties:
            parties[party.name] = party
        total_lower = sum(p.lower_house_seats for p in parties.values())
        total_upper = sum(p.upper_house_seats for p in parties.values())
        for name, party in parties.items():
            bar = "█" * max(1, int(party.lower_house_seats / 10))
            coalition_mark = "🤝" if name in self.coalition_partners or (name == self.player_party.name and self.is_prime_minister) else ""
            print(f"{name:12s} 下:{party.lower_house_seats:3d} 上:{party.upper_house_seats:3d} 支持率:{party.support_rate:4.1f}% {coalition_mark} {bar}")
        print("-" * 70)
        print(f"衆議院総議席: {total_lower} / 465 | 過半数: 233 | 3分の2: 310")
        print(f"参議院総議席: {total_upper} / 248 | 過半数: 125")
        time.sleep(2.5)

    def _create_bill_menu(self):
        print("\n" + "-" * 70)
        print("【法案起草】")
        print("-" * 70)
        print("1. 経済・財政パッケージ")
        print("2. 社会保障改革")
        print("3. 教育・子育て強化")
        print("4. 防衛・安全保障")
        print("5. 環境・エネルギー")
        print("6. カスタム法案を作成")
        print("0. 戻る")

        choice = input("\n選択: ").strip()
        if choice == "0":
            return

        template_map = {
            "1": {
                "name": "景気回復緊急対策法",
                "area": PolicyArea.ECONOMY,
                "budget": 15.0,
                "effects": {"economy": 3.5, "happiness": 1.0, "support": 2.5},
                "support": 58.0,
                "description": "公共投資と減税による総合的な景気対策を実施"},
            "2": {
                "name": "全世代型社会保障改革法",
                "area": PolicyArea.WELFARE,
                "budget": 12.0,
                "effects": {"economy": -0.5, "happiness": 3.2, "support": 2.0},
                "support": 62.0,
                "description": "年金・医療・介護の持続可能性を高める改革"},
            "3": {
                "name": "教育未来投資法",
                "area": PolicyArea.EDUCATION,
                "budget": 8.0,
                "effects": {"economy": 1.0, "happiness": 2.8, "support": 1.5},
                "support": 65.0,
                "description": "教育無償化とデジタル教育基盤を強化"},
            "4": {
                "name": "包括的安全保障強化法",
                "area": PolicyArea.DEFENSE,
                "budget": 10.0,
                "effects": {"economy": 0.5, "happiness": -0.5, "support": -1.5},
                "support": 48.0,
                "description": "防衛予算増額と同盟国との連携強化"},
            "5": {
                "name": "グリーンイノベーション推進法",
                "area": PolicyArea.ENVIRONMENT,
                "budget": 9.0,
                "effects": {"economy": 1.5, "happiness": 2.0, "support": 2.2},
                "support": 70.0,
                "description": "再生可能エネルギーと脱炭素社会の実現"}
        }

        if choice == "6":
            name = input("\n法案名: ").strip() or "特別政策法案"
            description = input("概要: ").strip() or "特別政策に関する法案"
            print("分野を選択:")
            for idx, area in enumerate(PolicyArea, 1):
                print(f"{idx}. {area.value}")
            area_choice = input("> ").strip()
            area_list = list(PolicyArea)
            area = area_list[int(area_choice) - 1] if area_choice.isdigit() and 1 <= int(area_choice) <= len(area_list) else PolicyArea.ECONOMY
            budget = self._prompt_float("予算規模(兆円): ", 5.0)
            public_support = self._prompt_float("世論の支持率(%): ", 50.0)
            effects = {
                "economy": self._prompt_float("経済効果(-10~10): ", 0.0),
                "happiness": self._prompt_float("幸福度効果(-10~10): ", 0.0),
                "support": self._prompt_float("支持率効果(-10~10): ", 0.0)
            }
            template = {
                "name": name,
                "area": area,
                "budget": budget,
                "effects": effects,
                "support": public_support,
                "description": description
            }
        else:
            template = template_map.get(choice)

        if not template:
            print("\n❌ 法案作成をキャンセルしました")
            time.sleep(1.5)
            return

        bill_id = f"bill_{len(self.bills) + 1}_{int(time.time())}"
        sponsor_type = "内閣" if self.is_prime_minister else "議員"
        bill = Bill(
            id=bill_id,
            name=template["name"],
            description=template["description"],
            area=template["area"],
            sponsor=self.player_id,
            sponsor_type=sponsor_type,
            budget_required=template["budget"],
            expected_effects=template["effects"],
            public_support=template["support"]
        )
        bill.support_count = 40 if sponsor_type == "内閣" else random.randint(10, 35)

        if self.diet_system.submit_bill(bill):
            print(f"\n✅ {bill.name}を提出しました")
        else:
            print("\n❌ 法案を提出できませんでした")
        time.sleep(1.5)

    def _committee_menu(self):
        pending = [b for b in self.bills.values() if b.status == BillStatus.COMMITTEE]
        if not pending:
            print("\n現在、委員会審議中の法案はありません")
            time.sleep(1.5)
            return

        print("\n審議中の法案一覧:")
        for idx, bill in enumerate(pending, 1):
            print(f"{idx}. {bill.name} ({bill.committee or '未割当'}) 賛成/反対: {bill.committee_votes_for}/{bill.committee_votes_against}")

        choice = input("\n審議する法案番号 (0で戻る): ").strip()
        if not choice.isdigit() or int(choice) == 0:
            return

        idx = int(choice) - 1
        if 0 <= idx < len(pending):
            self.diet_system.debate_bill(pending[idx].id)
            time.sleep(1.5)

    def _conduct_plenary_vote(self):
        lower_pending = [b for b in self.bills.values() if b.status == BillStatus.LOWER_HOUSE]
        upper_pending = [b for b in self.bills.values() if b.status == BillStatus.UPPER_HOUSE]

        if not lower_pending and not upper_pending:
            print("\n本会議に上程できる法案がありません")
            time.sleep(1.5)
            return

        print("\nどの院で採決しますか？")
        print("1. 衆議院")
        print("2. 参議院")
        chamber_choice = input("\n選択: ").strip()

        if chamber_choice == "1":
            target_list = lower_pending
            house = "lower"
        elif chamber_choice == "2":
            target_list = upper_pending
            house = "upper"
        else:
            print("\n❌ 無効な選択です")
            time.sleep(1.5)
            return

        if not target_list:
            print("\n採決できる法案がありません")
            time.sleep(1.5)
            return

        for idx, bill in enumerate(target_list, 1):
            print(f"{idx}. {bill.name} 世論支持:{bill.public_support:.1f}% 予算:{bill.budget_required:.1f}兆円")

        choice = input("\n採決する法案番号 (0で戻る): ").strip()
        if not choice.isdigit() or int(choice) == 0:
            return

        idx = int(choice) - 1
        if 0 <= idx < len(target_list):
            self.diet_system.vote_in_diet(target_list[idx].id, house)
            time.sleep(1.5)

    def _prompt_float(self, prompt: str, default: float) -> float:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            print(f"無効な入力のため既定値({default})を適用します")
            return default
    
    def public_activity_menu(self):
        """公共活動・メディア戦略メニュー"""
        while True:
            print("\n" + "=" * 70)
            print("【公共活動・メディア戦略】")
            print("=" * 70)
            print("1. 街頭演説を行う")
            print("2. SNS戦略を展開")
            print("3. 記者会見を開く")
            print("4. 政治討論会に参加")
            print("5. 活動履歴を確認")
            print("0. 戻る")
            
            choice = input("\n選択: ").strip()
            
            if choice == "1":
                self.public_activity.street_speech()
            elif choice == "2":
                self.public_activity.sns_campaign()
            elif choice == "3":
                self.public_activity.press_conference()
            elif choice == "4":
                self.public_activity.political_debate()
            elif choice == "5":
                self._show_activity_history()
            elif choice == "0":
                break
            else:
                print("\n❌ 無効な選択です")
                time.sleep(1)
    
    def _show_activity_history(self):
        """公共活動の履歴表示"""
        GameInitializer.clear_screen()
        print("=" * 80)
        print("【公共活動履歴】")
        print("=" * 80)
        
        # 街頭演説履歴
        if self.public_activity.speech_history:
            print("\n🎤 街頭演説履歴:")
            for i, speech in enumerate(self.public_activity.speech_history[-5:], 1):  # 最新5件
                date_str = speech['date'].strftime('%Y-%m-%d')
                print(f"  {i}. {date_str} {speech['venue']} - 支持率変動: {speech['analysis'].get('support_change', 0):+.1f}%")
        
        # SNS投稿履歴
        if self.public_activity.sns_posts:
            print("\n📱 SNS投稿履歴:")
            for i, post in enumerate(self.public_activity.sns_posts[-5:], 1):
                date_str = post['date'].strftime('%Y-%m-%d')
                viral = post['analysis'].get('viral_potential', 0)
                print(f"  {i}. {date_str} {post['platform']} - バイラル度: {viral}/100")
        
        # 記者会見履歴
        if self.public_activity.press_conferences:
            print("\n📰 記者会見履歴:")
            for i, conf in enumerate(self.public_activity.press_conferences[-5:], 1):
                date_str = conf['date'].strftime('%Y-%m-%d')
                print(f"  {i}. {date_str} {conf['type']} - 総合スコア: {conf['total_score']:.1f}/100")
        
        # 討論会履歴
        if self.public_activity.debates:
            print("\n🏛️ 討論会履歴:")
            for i, debate in enumerate(self.public_activity.debates[-5:], 1):
                date_str = debate['date'].strftime('%Y-%m-%d')
                result = "勝利" if debate['player_score'] > debate['opponent_score'] else "敗北"
                print(f"  {i}. {date_str} vs {debate['opponent']} ({debate['theme']}) - {result}")
        
        if not any([self.public_activity.speech_history, self.public_activity.sns_posts, 
                   self.public_activity.press_conferences, self.public_activity.debates]):
            print("\n📝 まだ公共活動の記録がありません")
        
        print("\n" + "=" * 80)
        input("Enterで戻る...")
        time.sleep(1)
    
    def strategic_policy_menu(self):
        """戦略的政策メニュー"""
        if self.action_points < 20:
            print("アクションポイントが不足しています (必要: 20)")
            return
        
        print("\n戦略的政策実行")
        print("具体的な政策内容と目標を入力してください:")
        print("例: '中小企業支援のため法人税を15%に引き下げ、雇用創出を図る'")
        
        policy_description = input("\n政策内容: ").strip()
        if not policy_description:
            print("政策が入力されませんでした")
            return
        
        # LLMで政策を分析
        context = {
            'support': self.player_party.support_rate,
            'gdp_growth': self.economy.growth_rate,
            'unemployment': self.economy.unemployment_rate,
            'debt': self.economy.national_debt
        }
        
        analysis = self.llm.analyze_policy_impact(policy_description, context)
        
        print(f"\n政策分析結果:")
        print(f"経済効果: {analysis.get('economy', 0):+.1f}")
        print(f"幸福度効果: {analysis.get('happiness', 0):+.1f}")
        print(f"支持率効果: {analysis.get('support', 0):+.1f}")
        print(f"実施コスト: {analysis.get('cost', 0):.1f}兆円")
        print(f"\n分析: {analysis.get('analysis', '分析不可')}")
        
        if input("\nこの政策を実行しますか？ (y/n): ").lower() == 'y':
            self.action_points -= 20
            
            # 効果を適用
            self.player_party.support_rate += analysis.get('support', 0)
            self.economy.growth_rate += analysis.get('economy', 0) * 0.1
            
            # 国民の反応をシミュレート
            reaction = self.public_opinion.simulate_public_reaction(policy_description, context)
            self.public_opinion.display_public_reaction(reaction, policy_description)
            
            print("\n政策を実行しました")
    
    def strategic_public_activity(self):
        """戦略的公共活動"""
        if self.action_points < 15:
            print("アクションポイントが不足しています (必要: 15)")
            return
        
        self.public_activity_menu()  # 既存の機能を活用
        self.action_points -= 15
    
    def political_negotiation_menu(self):
        """政治交渉メニュー"""
        if self.action_points < 25:
            print("アクションポイントが不足しています (必要: 25)")
            return
        
        print("\n政治交渉")
        print("交渉内容と目標を入力してください:")
        
        negotiation_content = input("交渉内容: ").strip()
        
        if negotiation_content:
            self.action_points -= 25
            
            # 交渉成功判定
            success_rate = 0.4 + (self.strategic_resources['political_capital'] / 200)
            
            if random.random() < success_rate:
                print("交渉に成功しました！")
                self.strategic_resources['political_capital'] += 15
                self.player_party.support_rate += random.uniform(1, 3)
            else:
                print("交渉は不調に終わりました...")
                self.strategic_resources['political_capital'] -= 5
    
    def crisis_response_menu(self):
        """危機対応メニュー"""
        active_events = [e for e in self.event_manager.active_events if not e.resolved]
        
        if not active_events:
            print("現在、対応が必要な危機はありません")
            return
        
        print("\n緊急事案対応")
        for i, event in enumerate(active_events, 1):
            print(f"{i}. {event.title} (緊急度: {event.urgency.name})")
        
        choice = input("対応する事案番号: ").strip()
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(active_events):
                event = active_events[idx]
                response = self.event_manager.present_event_to_player(event)
    
    def strategic_analysis_menu(self):
        """戦略分析メニュー"""
        if self.action_points < 10:
            print("アクションポイントが不足しています (必要: 10)")
            return
        
        print("\n戦略分析")
        print("分析したい内容を入力してください:")
        
        analysis_query = input("分析内容: ").strip()
        
        if analysis_query:
            self.action_points -= 10
            
            # LLMで戦略分析を実行
            context = self._build_game_context()
            analysis = self.llm.analyze_political_stance_impact(analysis_query, context)
            
            print(f"\nAI戦略分析結果:")
            print(f"総合効果度: {analysis.get('overall_effectiveness', 50)}/100")
            print(f"リスク評価: {analysis.get('risk_assessment', '不明')}")
            print(f"戦略アドバイス: {analysis.get('strategic_advice', 'データなし')}")
    
    def information_gathering_menu(self):
        """情報収集メニュー"""
        if self.action_points < 5:
            print("アクションポイントが不足しています (必要: 5)")
            return
        
        print("\n世論動向調査結果:")
        print(f"現在の支持率: {self.player_party.support_rate:.1f}%")
        
        # 各政党の支持率も表示
        for party in self.domestic.parties:
            print(f"{party.name}: {party.support_rate:.1f}%")
        
        self.action_points -= 5
    
    def international_activity_menu(self):
        """国際活動メニュー"""
        if self.action_points < 30:
            print("アクションポイントが不足しています (必要: 30)")
            return
        
        print("\n国際活動")
        print("国際的な活動内容を入力してください:")
        
        activity = input("活動内容: ").strip()
        
        if activity:
            self.action_points -= 30
            self.strategic_resources['international_standing'] += 10
            
            # 国民の反応をシミュレート
            reaction = self.public_opinion.simulate_public_reaction(activity)
            self.public_opinion.display_public_reaction(reaction, "国際活動")
            
            print("国際活動を実行しました")
    
    def free_action_mode(self):
        """自由行動モード - LLM完全統合"""
        print("\n" + "="*60)
        print("【自由行動モード】")
        print("="*60)
        print("任意の政治的行動を自然言語で入力してください:")
        print("AIが詳細に分析し、リアルタイムで国民の声を生成します")
        print("例: 「税制改革について記者会見を開く」")
        print("    「SNSで若者向けメッセージを発信」")
        print("    「野党との連立協議を開始」")
        
        action = input("\n行動内容: ").strip()
        
        if not action:
            print("行動が入力されませんでした")
            return
        
        # アクションポイント消費
        cost = max(5, min(50, len(action) // 10))
        
        if self.action_points < cost:
            print(f"アクションポイントが不足しています (必要: {cost})")
            return
        
        self.action_points -= cost
        
        # 国民の反応をシミュレート
        context = self._build_game_context()
        reaction = self.public_opinion.simulate_public_reaction(action, context)
        self.public_opinion.display_public_reaction(reaction, action)
        
        # 結果を適用
        support_change = self.public_opinion.calculate_support_change(reaction)
        self.player_party.support_rate += support_change
        self.player_party.support_rate = max(5.0, min(95.0, self.player_party.support_rate))
        
        print(f"\n支持率変化: {support_change:+.1f}% → {self.player_party.support_rate:.1f}%")
        
        print(f"\n【行動実行結果】")
        print(f"コスト: {cost}AP | 支持率変化: {support_change:+.1f}%")
        print(f"現在支持率: {self.player_party.support_rate:.1f}%")
        
        # 戦略リソースへの影響も表示
        if abs(support_change) > 2:
            if support_change > 0:
                self.strategic_resources['political_capital'] += random.uniform(1, 3)
                print("政治的影響力が向上しました")
            else:
                self.strategic_resources['political_capital'] -= random.uniform(1, 3)
                print("政治的影響力が低下しました")
        
        input("\nEnterで続行...")
    
    def advance_time(self):
        """時間経過"""
        print("\n時間が経過しています...")
        
        # アクションポイント回復
        self.action_points = min(100, self.action_points + 30)
        
        # 日付進行
        self.date += timedelta(days=7)
        self.turn += 1
        
        # 経済・政治情勢の変化
        self.economy.simulate_quarter([])
        self.opposition_ai.simulate_opposition_activities()
        
        # 戦略リソースの自然変動
        for resource in self.strategic_resources:
            self.strategic_resources[resource] += random.uniform(-2, 2)
            self.strategic_resources[resource] = max(0, min(100, self.strategic_resources[resource]))
        
        print(f"アクションポイント回復: {self.action_points}/100")
        
        # 勝利・敗北条件チェック
        if self.player_party.support_rate >= 70:
            print("\n圧倒的支持を獲得！政治的勝利です！")
            self.victory = True
            self.game_over = True
        elif self.player_party.support_rate <= 10:
            print("\n支持率が極端に低下...政治生命が危険です")
            self.game_over = True
    
    def _build_game_context(self) -> Dict:
        """ゲーム状況のコンテキストを構築"""
        return {
            'support': self.player_party.support_rate,
            'is_pm': self.is_prime_minister,
            'date': self.date,
            'turn': self.turn,
            'action_points': self.action_points,
            'resources': self.strategic_resources.copy(),
            'economy': {
                'growth': self.economy.growth_rate,
                'unemployment': self.economy.unemployment_rate
            }
        }

    def form_cabinet(self, coalition_partners: Optional[List[str]] = None) -> None:
        """内閣を構成"""
        coalition_partners = coalition_partners or []
        self.coalition_partners = coalition_partners
        cabinet_members: List[CabinetMember] = []
        ministries = [
            "内閣官房", "財務", "外務", "防衛", "厚生労働", "経済産業",
            "文部科学", "国土交通", "農林水産", "環境", "総務", "法務", "デジタル"
        ]

        partner_cycle = coalition_partners[:]
        for ministry in ministries:
            if partner_cycle:
                partner = partner_cycle.pop(0)
                partner_cycle.append(partner)
            else:
                partner = self.player_party.name

            name = f"{ministry}担当大臣"
            loyalty_base = 80 if partner == self.player_party.name else 65
            cabinet_members.append(
                CabinetMember(
                    name=f"{partner[:2]}系{name}",
                    ministry=ministry,
                    competence=random.gauss(72, 8),
                    loyalty=max(30.0, random.gauss(loyalty_base, 12)),
                    scandal_risk=max(1.0, random.gauss(4.5, 1.5)),
                    politician_id=f"cab_{ministry}_{int(time.time())}"
                )
            )

        self.domestic.cabinet = cabinet_members
        self.domestic.player_party_name = self.player_party.name
        print("\n✅ 新内閣を発足しました")
        time.sleep(2)

    def force_general_election(self, reason: str) -> None:
        """総選挙を実施する"""
        print("\n" + "=" * 70)
        print("【総選挙発動】")
        print("=" * 70)
        print(f"理由: {reason}")
        time.sleep(1.5)
        self.election_system.run_general_election()
    
    def end_turn(self):
        print("\n" + "="*70)
        print("⏰ ターンを進行しています...")
        print("="*70)
        
        # 経済シミュレーション
        print("\n📊 経済動向を計算中...")
        economic_data = self.economy.simulate_quarter(self.active_policies)
        time.sleep(0.5)
        
        # 外交イベント
        print("🌍 国際情勢をシミュレート中...")
        diplomatic_events = self.diplomacy.simulate_international_events()
        time.sleep(0.5)
        
        # 世論シミュレーション
        print("📢 世論動向を分析中...")
        self.domestic.simulate_public_opinion(
            self.player_party,
            self.domestic.parties,
            self.active_policies,
            economic_data,
            diplomatic_events
        )
        time.sleep(0.5)

        # 野党活動
        self.opposition_ai.simulate_opposition_activities()
        
        # 政策の進行
        completed_policies = []
        for policy in self.active_policies:
            policy.implementation_time -= 1
            if policy.implementation_time <= 0:
                completed_policies.append(policy)
        
        for policy in completed_policies:
            self.active_policies.remove(policy)
            print(f"\n✅ 政策「{policy.name}」が完了しました")
        
        # ランダムイベント
        if random.random() < 0.2:
            self._trigger_random_event()
        
        # 外交イベント表示
        if diplomatic_events:
            print("\n🌏 国際イベント:")
            for event in diplomatic_events:
                print(f"  • {event}")
        
        # 予算更新
        self.economy.budget = self.economy.tax_revenue * 1.8
        
        # ターン進行
        self.turn += 1
        self.date += timedelta(days=90)
        
        # 履歴記録
        self.policy_history.append({
            "turn": self.turn,
            "support": self.domestic.national_support,
            "happiness": self.domestic.national_happiness,
            "gdp_growth": self.economy.growth_rate,
            "debt": self.economy.national_debt
        })
        
        # 勝利条件チェック
        if self.domestic.national_support >= 80 and self.domestic.national_happiness >= 8.0:
            self.victory = True
            self.game_over = True
        
        # 敗北条件チェック
        if self.domestic.national_support < 15:
            print("\n💥 支持率が低すぎます！不信任案が可決されました")
            self.game_over = True
        elif self.economy.national_debt / self.economy.gdp > 3.0:
            print("\n💥 国家債務が制御不能になりました！")
            self.game_over = True
        elif self.turn >= 40:  # 10年
            print("\n⏰ 任期満了です")
            self.game_over = True
        
        print("\n" + "="*70)
        input("Enterでターン終了...")
    
    def _trigger_random_event(self):
        events = [
            ("🌪️ 大型台風が上陸", -1, -0.5, -2),
            ("📈 株価が急騰", 1, 0.3, 2),
            ("🏭 大企業が工場閉鎖を発表", -0.5, -0.3, -3),
            ("🎓 ノーベル賞受賞者が誕生", 0, 0.5, 3),
            ("⚡ エネルギー価格が高騰", -1, -0.5, -2),
            ("🏆 オリンピック誘致成功", 0.5, 1, 5),
            ("💼 失業率が改善", 0.5, 0.5, 2),
            ("🏥 医療費が増大", -0.5, -0.3, -1),
        ]
        
        event, economy_effect, happiness_effect, support_effect = random.choice(events)
        print(f"\n🎲 ランダムイベント: {event}")
        
        self.economy.growth_rate += economy_effect
        self.domestic.national_happiness += happiness_effect
        self.domestic.national_support += support_effect
        
        time.sleep(2)
    
    def show_game_over(self):
        os.system('clear' if os.name != 'nt' else 'cls')
        print("\n" + "="*70)
        
        if self.victory:
            print("🎉🎉🎉 ゲームクリア！！🎉🎉🎉")
            print("="*70)
            print("\nおめでとうございます！")
            print(f"支持率 {self.domestic.national_support:.1f}% と")
            print(f"国民幸福度 {self.domestic.national_happiness:.2f} を達成しました！")
            print("\nあなたは優れた政治家です！")
        else:
            print("💔 ゲームオーバー")
            print("="*70)
            print("\n残念ながら目標を達成できませんでした")
        
        print("\n" + "="*70)
        print("【最終成績】")
        print("="*70)
        print(f"在任期間: {self.turn}ターン ({self.turn/4:.1f}年)")
        print(f"最終支持率: {self.domestic.national_support:.1f}%")
        print(f"最終幸福度: {self.domestic.national_happiness:.2f}/10")
        print(f"最終GDP: {self.economy.gdp:.1f}兆円")
        print(f"平均成長率: {sum(p.get('gdp_growth', 0) for p in self.policy_history)/len(self.policy_history):.2f}%" if self.policy_history else "N/A")
        print(f"実施した政策数: {len(self.policy_history)}")
        
        # スコア計算
        score = (
            self.domestic.national_support * 10 +
            self.domestic.national_happiness * 100 +
            self.economy.growth_rate * 50 +
            (3000 - self.economy.national_debt) / 10
        )
        print(f"\n総合スコア: {score:.0f}点")
        
        if score > 2000:
            print("ランク: S (伝説の首相)")
        elif score > 1500:
            print("ランク: A (優秀な首相)")
        elif score > 1000:
            print("ランク: B (平均的な首相)")
        elif score > 500:
            print("ランク: C (課題の多い首相)")
        else:
            print("ランク: D (失敗した首相)")
        
        print("="*70)
    
    def run(self):
        """新しい戦略的メインゲームループ"""
        print("\n戦略的政治シミュレーション開始！")
        print("あなたは能動的な判断で政治情勢を動かしていきます")
        
        while not self.game_over:
            # イベントチェック
            new_event = self.event_manager.update_events()
            if new_event and not new_event.resolved:
                response = self.event_manager.present_event_to_player(new_event)
                # 国民の反応をシミュレート
                reaction = self.public_opinion.simulate_public_reaction(response)
                self.public_opinion.display_public_reaction(reaction, new_event.title)
                
                # 支持率に反映
                support_change = self.public_opinion.calculate_support_change(reaction)
                self.player_party.support_rate += support_change
                self.player_party.support_rate = max(5.0, min(95.0, self.player_party.support_rate))
            
            # ダッシュボード表示
            self.show_strategic_dashboard()
            
            # アクションポイントが不足していたら時間経過を促す
            if self.action_points < 10:
                print(f"\nアクションポイント不足 ({self.action_points}/100)")
                print("時間を経過させてポイントを回復するか、軽い行動を選択してください")
            
            choice = input("\n行動選択: ").strip()
            
            if choice == "1":
                self.strategic_policy_menu()
            elif choice == "2":
                self.strategic_public_activity()
            elif choice == "3":
                self.political_negotiation_menu()
            elif choice == "4":
                self.crisis_response_menu()
            elif choice == "5":
                self.strategic_analysis_menu()
            elif choice == "6":
                self.information_gathering_menu()
            elif choice == "7":
                self.international_activity_menu()
            elif choice == "8":
                self.free_action_mode()
            elif choice.lower() == "s":
                self.save_game_menu()
            elif choice.lower() == "l":
                self.load_game_menu()
            elif choice == "0":
                self.advance_time()
            elif choice.lower() == "q":
                if input("\n本当に終了しますか？ (y/n): ").lower() == 'y':
                    self.game_over = True
                    print("\nゲームを終了します")
                    break
            else:
                print("無効な選択です")
        
        if self.game_over:
            self.show_game_over()
    
    def save_game_menu(self):
        """セーブメニュー"""
        print("\n" + "="*50)
        print("【ゲームセーブ】")
        print("="*50)
        
        # 既存のセーブ一覧表示
        saves = SaveManager.list_saves()
        if saves:
            print("既存のセーブデータ:")
            for i, save in enumerate(saves[:5], 1):  # 最新5件表示
                date_str = save.get('saved_at', '').replace('T', ' ')[:19]
                print(f"  {i}. {save['slot_name']} ({date_str})")
        
        print("\nセーブ名を入力してください（空白で自動生成）:")
        slot_name = input("> ").strip()
        
        if not slot_name:
            slot_name = f"save_{self.date.strftime('%Y%m%d_%H%M')}_{self.player_party.short_name}"
        
        success, result = SaveManager.save_game(self, slot_name)
        if success:
            print(f"\n✅ セーブ完了: {slot_name}")
        else:
            print(f"\n❌ セーブ失敗: {result}")
        
        input("Enterで戻る...")
    
    def load_game_menu(self):
        """ロードメニュー"""
        saves = SaveManager.list_saves()
        if not saves:
            print("\n📁 セーブデータがありません")
            input("Enterで戻る...")
            return
        
        print("\n" + "="*50)
        print("【ゲームロード】")
        print("="*50)
        
        for i, save in enumerate(saves, 1):
            date_str = save.get('saved_at', '').replace('T', ' ')[:19]
            support = save.get('support_rate', 0)
            turn = save.get('turn', 0)
            print(f"{i}. {save['slot_name']} - {save['party_name']}")
            print(f"   └ {date_str} | ターン{turn} | 支持率{support:.1f}%")
        
        print("\n0. 戻る")
        choice = input("\nロードするデータ番号: ")
        
        if choice.isdigit() and 1 <= int(choice) <= len(saves):
            save_data = saves[int(choice) - 1]
            confirm = input(f"\n{save_data['slot_name']} をロードしますか？現在の進行は失われます (y/n): ")
            
            if confirm.lower() == 'y':
                loaded_game = SaveManager.load_game(save_data['slot_name'])
                if loaded_game:
                    # 現在のゲーム状態を置き換え
                    self.__dict__.update(loaded_game.__dict__)
                    print(f"\n✅ {save_data['slot_name']} をロードしました")
                    time.sleep(1)
                else:
                    print("\n❌ ロードに失敗しました")
                    input("Enterで戻る...")
        elif choice != "0":
            print("\n無効な選択です")
            input("Enterで戻る...")

if __name__ == "__main__":
    try:
        while True:
            choice = GameInitializer.show_main_menu()
            
            if choice == "1":
                # 新規ゲーム
                game = GameInitializer.create_new_game()
                if game:
                    # 総裁選チュートリアル
                    election = LeadershipElection(game)
                    if election.run_tutorial_election():
                        game.tutorial_complete = True
                        game.run()
                    else:
                        print("\n総裁選で敗北しました。")
                        input("Enterで戻る...")
                        
            elif choice == "2":
                # ロード
                saves = SaveManager.list_saves()
                if not saves:
                    print("\nセーブデータがありません")
                    input("Enterで戻る...")
                    continue
                
                GameInitializer.clear_screen()
                print("=" * 80)
                print("【セーブデータ一覧】")
                print("=" * 80)
                for i, save in enumerate(saves, 1):
                    print(f"{i}. {save['slot_name']}")
                    print(f"   {save['party_name']} | ターン{save['turn']}")
                    print(f"   支持率: {save['support_rate']:.1f}% | {save['saved_at']}")
                    print()
                
                print("0. 戻る")
                choice = input("\n読み込むデータ番号: ").strip()
                
                if choice.isdigit() and 1 <= int(choice) <= len(saves):
                    save_data = saves[int(choice) - 1]
                    game = SaveManager.load_game(save_data['slot_name'])
                    if game:
                        print(f"\n✅ {save_data['slot_name']} をロードしました")
                        time.sleep(1)
                        game.run()
                    else:
                        print("\n❌ ロードに失敗しました")
                        input("Enterで戻る...")
                        
            elif choice == "3":
                # セーブ管理
                saves = SaveManager.list_saves()
                if not saves:
                    print("\nセーブデータがありません")
                    input("Enterで戻る...")
                    continue
                
                GameInitializer.clear_screen()
                print("=" * 80)
                print("【セーブデータ管理】")
                print("=" * 80)
                for i, save in enumerate(saves, 1):
                    print(f"{i}. {save['slot_name']} - {save['party_name']}")
                
                print("\n削除するデータ番号（0で戻る）:")
                choice = input("> ").strip()
                
                if choice.isdigit() and 1 <= int(choice) <= len(saves):
                    save_data = saves[int(choice) - 1]
                    confirm = input(f"\n本当に削除しますか？ {save_data['slot_name']} (y/n): ")
                    if confirm.lower() == 'y':
                        if SaveManager.delete_save(save_data['slot_name']):
                            print("\n✅ 削除しました")
                        else:
                            print("\n❌ 削除に失敗しました")
                    time.sleep(1)
                    
            elif choice == "4":
                # ゲーム説明
                GameInitializer.show_tutorial()
                
            elif choice == "0":
                print("\nゲームを終了します")
                break
                
    except KeyboardInterrupt:
        print("\n\nゲームを中断しました")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()