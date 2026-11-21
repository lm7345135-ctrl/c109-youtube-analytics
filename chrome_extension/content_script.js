chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "extract") {
    try {
      const url = window.location.hostname;
      if (url.includes("tiktok.com")) {
        extractTikTokData();
      } else if (url.includes("x.com") || url.includes("twitter.com")) {
        extractXData();
      } else {
        alert("このページはX(Twitter)またはTikTokではありません。");
      }
    } catch (error) {
      alert("エラーが発生しました: " + error.message);
    }
  }
});

function parseNumber(str) {
  if (!str) return 0;
  let numStr = str.toString().replace(/,/g, '');
  let multi = 1;
  if (numStr.includes('万')) {
    multi = 10000;
    numStr = numStr.replace('万', '');
  } else if (numStr.match(/[Kk]/)) {
    multi = 1000;
    numStr = numStr.replace(/[Kk]/g, '');
  } else if (numStr.match(/[Mm]/)) {
    multi = 1000000;
    numStr = numStr.replace(/[Mm]/g, '');
  }
  let val = parseFloat(numStr.match(/[\d\.]+/));
  return isNaN(val) ? 0 : Math.floor(val * multi);
}

// ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
// 【1】TikTok用 抽出ロジック（野間さん考案：視覚構造ベース解析）
// ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
function extractTikTokData() {
  let parentLikes = 0, parentComments = 0, parentShares = 0;

  const likeEl = document.querySelector('[data-e2e="like-count"], [data-e2e="browse-like-count"], [data-e2e="search-like-count"]');
  if (likeEl) parentLikes = parseNumber(likeEl.innerText);

  const commentEl = document.querySelector('[data-e2e="comment-count"], [data-e2e="browse-comment-count"], [data-e2e="search-comment-count"]');
  if (commentEl) parentComments = parseNumber(commentEl.innerText);

  const shareEl = document.querySelector('[data-e2e="share-count"], [data-e2e="browse-share-count"], [data-e2e="search-share-count"]');
  if (shareEl) parentShares = parseNumber(shareEl.innerText);

  let result = {
    platform: "TikTok",
    parent_post: { likes: parentLikes, comments: parentComments, shares: parentShares },
    child_comments: { top_by_likes: [] }
  };

  let comments = [];

  // 1. 画面上の「返信」という文字を持つ最小単位の要素を探す
  const allElements = document.querySelectorAll('span, p, div');
  const replyElements = Array.from(allElements).filter(el =>
      el.innerText && el.innerText.trim() === '返信' && el.children.length === 0
  );

  if (replyElements.length === 0) {
    alert("コメントが見つかりません。リロード（F5）して再度お試しください。");
    return;
  }

  // 2. 「返信」ボタンを起点に、各コメントのブロック（親枠）を特定する
  replyElements.forEach(replyEl => {
      let container = replyEl.parentElement;
      let prevContainer = container;

      // 枠を上に遡り、1つのコメント全体を囲む最適な枠を見つける
      while (container && container.parentElement) {
          // もし枠内に「返信」という文字が2つ以上あったら、それはリスト全体まで遡ってしまった証拠なので1つ下に戻る
          const matchCount = (container.innerText.match(/返信/g) || []).length;
          if (matchCount > 1) {
              container = prevContainer;
              break;
          }
          // コメントブロックの特徴であるアバター画像が見つかればそこがベストな枠
          if (container.querySelector('img')) break;
          
          prevContainer = container;
          container = container.parentElement;
      }

      // 3. 枠内のテキストを改行で分割し、見た目通りの配列（ブロック）にする
      // 理想の形: ["ユーザー名", "本文", "日付", "返信", "いいね数"]
      let lines = container.innerText.split('\n').map(l => l.trim()).filter(l => l !== '');
      let replyIdx = lines.indexOf('返信');
      if (replyIdx === -1) return;

      // 4. 配列の位置関係から「いいね数」を取得（返信より後ろにある数字）
      let likes = 0;
      for (let i = replyIdx + 1; i < lines.length; i++) {
          let token = lines[i];
          if (/^[\d\.,]+[KkMm万]?$/.test(token)) {
              likes = parseNumber(token);
              break;
          }
      }

      // 5. 配列の位置関係から「本文」を取得（ユーザー名と日付の間にあるテキスト）
      let text = "";
      if (replyIdx >= 2) {
          // ユーザー名(index 0)を飛ばし、日付(replyIdx - 1)の直前までを結合
          text = lines.slice(1, replyIdx - 1).join('\n').trim();
      }

      if (text) {
          // 同じコメントの重複取得を防ぐ
          if (!comments.some(c => c.text === text)) {
              comments.push({ text, likes });
          }
      }
  });

  // いいね順にソートして上位5件を抽出
  let topLikes = [...comments].sort((a, b) => b.likes - a.likes).slice(0, 5);
  result.child_comments.top_by_likes = topLikes.map((item, index) => {
    return { rank: index + 1, text: item.text, likes: item.likes };
  });

  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `TikTok_extracted_${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
// 【2】X(Twitter)用 抽出ロジック（そのまま維持）
// ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
function extractXData() {
  const articles = document.querySelectorAll('article[data-testid="tweet"]');
  if (articles.length < 2) {
    alert("コメントが見つかりません。下へスクロールして表示させてください。");
    return;
  }

  let parentArticle = articles[0];
  let parentTextDiv = parentArticle.querySelector('[data-testid="tweetText"]');
  let parentText = parentTextDiv ? parentTextDiv.innerText : "";
  
  let parentLikes = 0;
  let parentImpressions = 0;

  const parentLikeBtn = parentArticle.querySelector('[data-testid="like"]');
  if (parentLikeBtn && parentLikeBtn.getAttribute('aria-label')) {
      const match = parentLikeBtn.getAttribute('aria-label').match(/(\d+(?:,\d+)*(?:\.\d+)?万?)\s*件のいいね/);
      if(match) parentLikes = parseNumber(match[1]);
  }
  if (parentLikes === 0) {
      const likeMatch = parentArticle.innerText.match(/([\d,]+(?:\.\d+)?万?)\s*件のいいね/);
      if (likeMatch) parentLikes = parseNumber(likeMatch[1]);
  }

  const parentImpBtn = parentArticle.querySelector('a[href*="/analytics"]');
  if (parentImpBtn && parentImpBtn.getAttribute('aria-label')) {
      const match = parentImpBtn.getAttribute('aria-label').match(/(\d+(?:,\d+)*(?:\.\d+)?万?)\s*件の表示/);
      if(match) parentImpressions = parseNumber(match[1]);
  }
  if (parentImpressions === 0) {
      const impMatch = parentArticle.innerText.match(/([\d,]+(?:\.\d+)?万?)\s*件の表示/);
      if (impMatch) parentImpressions = parseNumber(impMatch[1]);
  }

  let result = {
    platform: "X",
    parent_post: { text: parentText, impressions: parentImpressions, likes: parentLikes },
    child_comments: { top_by_impressions: [], top_by_likes: [] }
  };

  let comments = [];

  for (let i = 1; i < articles.length; i++) {
    const rawText = articles[i].textContent.replace(/\s+/g, '');
    const hasAdKeyword = rawText.includes('プロモーション') || rawText.includes('広告') || rawText.includes('PR]') || rawText.includes('ＰＲ]');
    const hasTime = articles[i].querySelector('time');
    
    if (hasAdKeyword || !hasTime) {
      continue;
    }

    let textDiv = articles[i].querySelector('[data-testid="tweetText"]');
    let text = textDiv ? textDiv.innerText : "";
    
    let likes = 0;
    let impressions = 0;
    
    const likeBtn = articles[i].querySelector('[data-testid="like"]');
    if (likeBtn && likeBtn.getAttribute('aria-label')) {
        const match = likeBtn.getAttribute('aria-label').match(/(\d+(?:,\d+)*(?:\.\d+)?万?)\s*件のいいね/);
        if(match) likes = parseNumber(match[1]);
    }
    if (likes === 0) {
         const likeMatch = articles[i].innerText.match(/([\d,]+(?:\.\d+)?万?)\s*件のいいね/);
         if(likeMatch) likes = parseNumber(likeMatch[1]);
    }

    const impBtn = articles[i].querySelector('a[href*="/analytics"]');
    if (impBtn && impBtn.getAttribute('aria-label')) {
         const match = impBtn.getAttribute('aria-label').match(/(\d+(?:,\d+)*(?:\.\d+)?万?)\s*件の表示/);
         if(match) impressions = parseNumber(match[1]);
    }
    if (impressions === 0) {
         const impMatch = articles[i].innerText.match(/([\d,]+(?:\.\d+)?万?)\s*件の表示/);
         if(impMatch) impressions = parseNumber(impMatch[1]);
    }

    if (text) {
      comments.push({ text, impressions, likes });
    }
  }

  let sortedByImp = [...comments].sort((a, b) => b.impressions - a.impressions).slice(0, 5);
  result.child_comments.top_by_impressions = sortedByImp.map((item, index) => {
      return { rank: index + 1, text: item.text, impressions: item.impressions, likes: item.likes };
  });

  let sortedByLikes = [...comments].sort((a, b) => b.likes - a.likes).slice(0, 5);
  result.child_comments.top_by_likes = sortedByLikes.map((item, index) => {
      return { rank: index + 1, text: item.text, impressions: item.impressions, likes: item.likes };
  });

  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `X_extracted_${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}