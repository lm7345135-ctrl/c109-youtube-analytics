document.getElementById('extractBtn').addEventListener('click', async () => {
  // 現在開いているタブ（Xの画面）を探して、抽出開始の合図を送る
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: "extract" });
});