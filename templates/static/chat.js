// static/chat.js
// @ts-ignore
let ws = null;
// @ts-ignore
let room = null;
// @ts-ignore
let username = null;

const chatEl = document.getElementById('chat');
const joinBtn = document.getElementById('joinBtn');
const sendBtn = document.getElementById('sendBtn');

// @ts-ignore
function appendMessage(obj) {
  const div = document.createElement('div');
  div.className = 'msg';
  if (obj.type === 'system') {
    div.innerHTML = `<div class="system">${obj.text} <span class="meta">[${new Date(obj.ts).toLocaleString()}]</span></div>`;
  } else {
    div.innerHTML = `<strong>${obj.username}</strong>: ${obj.text} <div class="meta">${new Date(obj.ts).toLocaleString()}</div>`;
  }
  // @ts-ignore
  chatEl.appendChild(div);
  // @ts-ignore
  chatEl.scrollTop = chatEl.scrollHeight;
}

// @ts-ignore
async function loadHistory(room) {
  try {
    const res = await fetch(`/history/${encodeURIComponent(room)}?limit=100`);
    const data = await res.json();
    // @ts-ignore
    chatEl.innerHTML = '';
    data.forEach(appendMessage);
  } catch (e) {
    console.error("History load error", e);
  }
}

// @ts-ignore
joinBtn.onclick = async () => {
  // @ts-ignore
  room = document.getElementById('room').value || 'general';
  // @ts-ignore
  username = document.getElementById('username').value || 'guest';
  // @ts-ignore
  if (ws) {
    ws.close();
    ws = null;
  }
  await loadHistory(room);

  const proto = (location.protocol === 'https:') ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws/${encodeURIComponent(room)}?username=${encodeURIComponent(username)}`;
  ws = new WebSocket(url);

  ws.onopen = () => {
    // @ts-ignore
    appendMessage({type:'system', text: `Connected to room "${room}" as ${username}`, username:'system', ts: new Date().toISOString()});
  };
  ws.onmessage = evt => {
    try {
      const obj = JSON.parse(evt.data);
      appendMessage(obj);
    } catch (e) {
      console.warn('Invalid message', evt.data);
    }
  };
  ws.onclose = () => {
    appendMessage({type:'system', text:'Disconnected', username:'system', ts: new Date().toISOString()});
  };
};

// @ts-ignore
sendBtn.onclick = () => {
  const input = document.getElementById('message');
  // @ts-ignore
  const text = input.value.trim();
  if (!text) return;
  // @ts-ignore
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    alert('Not connected. Click Join first.');
    return;
  }
  ws.send(text);
  // @ts-ignore
  input.value = '';
};
