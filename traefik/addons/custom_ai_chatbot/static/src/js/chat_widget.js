/**
 * Platform AI Chatbot Widget — vanilla JS, no external dependencies.
 * Communicates with /chatbot/* JSON endpoints.
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'plt_chat_token';
    const SESSION_KEY = 'plt_chat_session';

    let visitorToken = null;
    let sessionId = null;
    let config = null;

    try { visitorToken = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    try { sessionId = sessionStorage.getItem(SESSION_KEY); } catch (e) {}

    async function init() {
        try {
            const resp = await jsonRpc('/chatbot/config', {});
            if (!resp || !resp.enabled) return;
            config = resp;
            injectWidget();
        } catch (e) { /* chatbot unavailable */ }
    }

    function injectWidget() {
        if (document.getElementById('plt-chat-widget')) return;
        const color = config.primary_color || '#1E40AF';
        const widget = document.createElement('div');
        widget.id = 'plt-chat-widget';
        widget.innerHTML = `
            <button id="plt-chat-btn" title="Chat" style="background:${color}">💬</button>
            <div id="plt-chat-box" style="display:none">
                <div id="plt-chat-hdr" style="background:${color}">
                    <span>Chat with us</span>
                    <button id="plt-chat-close">✕</button>
                </div>
                <div id="plt-chat-msgs"></div>
                <div id="plt-chat-row">
                    <input id="plt-chat-in" placeholder="Type a message…" disabled />
                    <button id="plt-chat-send" disabled>➤</button>
                </div>
            </div>`;
        document.body.appendChild(widget);
        document.getElementById('plt-chat-btn').onclick = openChat;
        document.getElementById('plt-chat-close').onclick = () => {
            document.getElementById('plt-chat-box').style.display = 'none';
        };
        document.getElementById('plt-chat-send').onclick = sendMsg;
        document.getElementById('plt-chat-in').onkeydown = (e) => { if (e.key === 'Enter') sendMsg(); };
    }

    async function openChat() {
        document.getElementById('plt-chat-box').style.display = 'flex';
        if (sessionId) return;
        try {
            const r = await jsonRpc('/chatbot/start', {visitor_token: visitorToken, language: navigator.language || 'en'});
            visitorToken = r.visitor_token;
            sessionId = String(r.session_id);
            try { localStorage.setItem(STORAGE_KEY, visitorToken); } catch (e) {}
            try { sessionStorage.setItem(SESSION_KEY, sessionId); } catch (e) {}
            enableInput();
            addMsg('bot', config.greeting || 'Hi! How can I help you?');
        } catch (e) { addMsg('sys', 'Chat unavailable.'); }
    }

    async function sendMsg() {
        const inp = document.getElementById('plt-chat-in');
        const msg = inp.value.trim();
        if (!msg || !sessionId) return;
        inp.value = '';
        addMsg('usr', msg);
        setEnabled(false);
        try {
            const r = await jsonRpc('/chatbot/message', {session_id: sessionId, message: msg});
            addMsg('bot', r.reply || '…');
            if (r.escalated) { addMsg('sys', '🔁 Connecting you with a team member…'); setEnabled(false); return; }
        } catch (e) { addMsg('sys', 'Error — please try again.'); }
        setEnabled(true);
    }

    function addMsg(role, text) {
        const c = document.getElementById('plt-chat-msgs');
        const d = document.createElement('div');
        d.className = 'plt-msg plt-msg-' + role;
        d.textContent = text;
        c.appendChild(d);
        c.scrollTop = c.scrollHeight;
    }

    function setEnabled(on) {
        document.getElementById('plt-chat-in').disabled = !on;
        document.getElementById('plt-chat-send').disabled = !on;
    }

    function enableInput() { setEnabled(true); }

    async function jsonRpc(url, params) {
        const r = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params}),
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error.message);
        return d.result;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else { init(); }
})();
