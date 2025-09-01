// APIサーバーのURL - CORSプロキシ経由に変更
const API_ENDPOINT = '.php';

console.log('History Logger: Enhanced content.js (v3) loaded.');

let lastVideoId = null; // 最後に保存した動画ID
let saveTimeout = null;   // 保存処理の重複実行を防ぐタイマー
let lastCheckedUrl = '';  // 最後にチェックしたURL
let isProcessing = false; // 処理中フラグ

/**
 * 履歴をサーバーに送信する非同期関数
 * @param {string} videoId - YouTubeの動画ID
 * @param {string} title - 動画のタイトル
 */
async function sendHistory(videoId, title) {
    if (!videoId || !title) {
        console.warn('History Logger: videoIdまたはtitleが空のため送信をスキップします。');
        return;
    }

    // 同じ動画IDが連続で保存されるのを防ぐ
    if (videoId === lastVideoId) {
        console.log('History Logger: 直前と同じ動画IDのため送信をスキップします。');
        return;
    }

    try {
        console.log(`History Logger: 送信開始 - VideoID: ${videoId}, Title: ${title}`);
        
        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ video_id: videoId, title: title }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log('History Logger: API Response:', result);
        
        if (result.status === 'success') {
            lastVideoId = videoId; // 成功した場合のみlastVideoIdを更新
            console.log('History Logger: 履歴保存成功！');
        } else {
            console.warn('History Logger: API応答はあったが成功ステータスではありません:', result);
        }
    } catch (error) {
        console.error('History Logger: APIへの送信に失敗しました。', error);
    }
}

/**
 * 動画タイトルを取得する関数（複数のセレクタを試行）
 */
function getVideoTitle() {
    const selectors = [
        '#title h1.yt-formatted-string',
        'h1.ytd-watch-metadata',
        'h1.ytd-video-primary-info-renderer',
        '#container h1',
        '.ytd-video-primary-info-renderer h1',
        'h1[class*="title"]'
    ];
    
    for (const selector of selectors) {
        const element = document.querySelector(selector);
        if (element && element.textContent.trim()) {
            return element.textContent.trim();
        }
    }
    return null;
}

/**
 * 現在のページの動画情報を取得し、保存処理を呼び出す関数
 */
function processCurrentVideo() {
    // 重複実行を防ぐ
    if (isProcessing) {
        console.log('History Logger: 既に処理中のため、重複実行をスキップします。');
        return;
    }
    
    // 実行が集中しないように、タイマーで少し待ってから実行（デバウンス）
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
        isProcessing = true;
        
        try {
            // 動画再生ページ（/watch）であることを確認
            if (window.location.hostname === 'www.youtube.com' && window.location.pathname === '/watch') {
                const videoId = new URLSearchParams(window.location.search).get('v');
                if (!videoId) {
                    console.log('History Logger: URLからvideoIdを取得できませんでした。');
                    return;
                }

                console.log(`History Logger: 動画ページを検出 - VideoID: ${videoId}`);

                // タイトル要素が描画されるまで最大10秒間試行
                let attempts = 0;
                const maxAttempts = 20; // 試行回数 (500ms * 20 = 10秒)
                
                const checkTitleAndSend = () => {
                    attempts++;
                    const title = getVideoTitle();

                    if (videoId && title) {
                        console.log(`History Logger: 動画情報取得完了 (ID: ${videoId}, Title: ${title})`);
                        sendHistory(videoId, title);
                    } else if (attempts < maxAttempts) {
                        // まだタイトルが取得できない場合、少し待って再試行
                        console.log(`History Logger: タイトル取得試行中... (${attempts}/${maxAttempts})`);
                        setTimeout(checkTitleAndSend, 500);
                    } else {
                        console.error('History Logger: 最大試行回数に達しましたが、動画タイトルを取得できませんでした。');
                    }
                };
                checkTitleAndSend();

            } else {
                console.log('History Logger: 動画再生ページではないため処理をスキップします。');
                lastVideoId = null; // 動画ページ以外ではリセット
            }
        } finally {
            // 2秒後に処理フラグをリセット
            setTimeout(() => {
                isProcessing = false;
            }, 2000);
        }
    }, 800); // デバウンス時間を短縮
}

/**
 * YouTube固有のナビゲーションイベントをリッスン
 */
function setupYouTubeNavigation() {
    // YouTube固有のナビゲーションイベント
    window.addEventListener('yt-navigate-start', () => {
        console.log('History Logger: yt-navigate-start イベントを検知');
        processCurrentVideo();
    });
    
    window.addEventListener('yt-navigate-finish', () => {
        console.log('History Logger: yt-navigate-finish イベントを検知');
        processCurrentVideo();
    });
    
    // popstateイベント（ブラウザの戻る/進むボタン）
    window.addEventListener('popstate', () => {
        console.log('History Logger: popstate イベントを検知');
        setTimeout(processCurrentVideo, 500);
    });
    
    // pushstate/replacestate の監視
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;
    
    history.pushState = function(...args) {
        originalPushState.apply(history, args);
        console.log('History Logger: pushState を検知');
        setTimeout(processCurrentVideo, 300);
    };
    
    history.replaceState = function(...args) {
        originalReplaceState.apply(history, args);
        console.log('History Logger: replaceState を検知');
        setTimeout(processCurrentVideo, 300);
    };
}

/**
 * より積極的なDOM監視を設定
 */
function setupDOMObserver() {
    // メインのナビゲーション検知
    const navigationObserver = new MutationObserver((mutations) => {
        let shouldCheck = false;
        
        // URLの変更チェック
        if (window.location.href !== lastCheckedUrl) {
            console.log('History Logger: URLの変更を検知しました。', window.location.href);
            lastCheckedUrl = window.location.href;
            shouldCheck = true;
        }
        
        // 特定の要素の変更もチェック
        mutations.forEach(mutation => {
            if (mutation.type === 'childList') {
                // YouTube のメインコンテンツエリアの変更を検知
                const targetSelectors = [
                    '#primary',
                    '#content',
                    '#player',
                    '.ytd-watch-flexy'
                ];
                
                targetSelectors.forEach(selector => {
                    if (mutation.target.matches && mutation.target.matches(selector)) {
                        console.log('History Logger: 重要なDOM要素の変更を検知:', selector);
                        shouldCheck = true;
                    }
                });
            }
        });
        
        if (shouldCheck) {
            processCurrentVideo();
        }
    });

    // より包括的な監視設定
    navigationObserver.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: false, // 属性変更は監視しない（パフォーマンス向上）
        characterData: false // テキスト変更は監視しない
    });
    
    console.log('History Logger: DOM監視を開始しました。');
}

/**
 * 定期的なチェック機能
 */
function setupPeriodicCheck() {
    setInterval(() => {
        if (window.location.href !== lastCheckedUrl) {
            console.log('History Logger: 定期チェックでURL変更を検知');
            lastCheckedUrl = window.location.href;
            processCurrentVideo();
        }
    }, 3000); // 3秒ごとにチェック
}

// --- 初期化処理 ---
function initialize() {
    console.log('History Logger: 初期化開始');
    
    // 現在のURLを記録
    lastCheckedUrl = window.location.href;
    
    // 各種監視機能を設定
    setupYouTubeNavigation();
    setupDOMObserver();
    setupPeriodicCheck();
    
    // 初回実行
    setTimeout(() => {
        console.log('History Logger: 初回チェック実行');
        processCurrentVideo();
    }, 1000);
    
    console.log('History Logger: 初期化完了 - 全ての監視機能が有効になりました');
}

// DOM読み込み完了後に初期化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
} else {
    initialize();
}
