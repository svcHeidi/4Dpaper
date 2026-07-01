/**
 * Chatbox logic for 4Dpapers AI Agent integration.
 *
 * On load:
 *   1. GET /api/providers  → populate provider <select>, mark unavailable ones
 *   2. GET /api/agents     → populate persona <select>
 *
 * No API keys are ever sent from the client — they live in server env vars.
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── DOM refs ────────────────────────────────────────────────────────── //
    const chatInput          = document.getElementById('chatInput');
    const chatSendBtn        = document.getElementById('chatSendBtn');
    const chatMessages       = document.getElementById('chatMessages');
    const providerSelect     = document.getElementById('aiProviderSelect');
    const modelInput         = document.getElementById('aiModelInput');
    const settingsToggle     = document.getElementById('aiSettingsToggle');
    const settingsPanel      = document.getElementById('aiSettingsPanel');
    const providerStatus     = document.getElementById('aiProviderStatus');

    let chatHistory = [];
    let isWaitingForResponse = false;

    // Persisted config (no API key — that's server-side now)
    let aiConfig = JSON.parse(localStorage.getItem('4dpaper_ai_config')) || {
        provider: 'ollama',
        model:    'llama3',
    };

    function saveConfig() {
        localStorage.setItem('4dpaper_ai_config', JSON.stringify(aiConfig));
    }

    // ── Settings panel toggle ────────────────────────────────────────────── //
    if (settingsToggle && settingsPanel) {
        settingsToggle.addEventListener('click', () => {
            settingsPanel.classList.toggle('hidden');
        });
    }

    // ── Provider select change ───────────────────────────────────────────── //
    if (providerSelect) {
        providerSelect.addEventListener('change', () => {
            aiConfig.provider = providerSelect.value;
            // Auto-fill model with the first known default for that provider
            const selected = providerSelect.options[providerSelect.selectedIndex];
            const defaultModel = selected?.dataset?.defaultModel || '';
            if (defaultModel) {
                aiConfig.model = defaultModel;
                if (modelInput) modelInput.value = defaultModel;
            }
            updateProviderStatus();
            saveConfig();
        });
    }

    if (modelInput) {
        modelInput.addEventListener('change', () => {
            aiConfig.model = modelInput.value.trim();
            saveConfig();
        });
    }

    // ── Load providers from server ───────────────────────────────────────── //
    async function loadProviders() {
        if (!providerSelect) return;

        try {
            const resp = await fetch('/api/providers');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            providerSelect.innerHTML = '';
            let selectedFound = false;

            for (const p of data.providers || []) {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.available ? p.name : `${p.name} (not configured)`;
                opt.disabled = !p.available;
                opt.dataset.defaultModel = p.default_model || (p.models?.[0] ?? '');
                if (p.id === aiConfig.provider && p.available) {
                    opt.selected = true;
                    selectedFound = true;
                }
                providerSelect.appendChild(opt);
            }

            // If saved provider is gone/disabled, fall back to first available
            if (!selectedFound) {
                const firstAvail = Array.from(providerSelect.options).find(o => !o.disabled);
                if (firstAvail) {
                    firstAvail.selected = true;
                    aiConfig.provider = firstAvail.value;
                    aiConfig.model    = firstAvail.dataset.defaultModel || aiConfig.model;
                    saveConfig();
                }
            }

            // Populate model input
            if (modelInput) modelInput.value = aiConfig.model;
            updateProviderStatus();

        } catch (err) {
            console.warn('Could not load providers:', err);
            // Leave the select as-is; it may already have a fallback option
            updateProviderStatus();
        }
    }

    function updateProviderStatus() {
        if (!providerStatus || !providerSelect) return;
        const selected = providerSelect.options[providerSelect.selectedIndex];
        const available = selected && !selected.disabled;
        providerStatus.title = available
            ? `${selected.textContent} is configured`
            : 'Provider not configured on this server';
        providerStatus.className = available
            ? 'w-2 h-2 rounded-full bg-green-400 flex-shrink-0'
            : 'w-2 h-2 rounded-full bg-red-400 flex-shrink-0';
    }


    // ── Message rendering ────────────────────────────────────────────────── //
    function appendMessage(role, content) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} w-full mb-4`;

        const bubble = document.createElement('div');
        bubble.className = `chat-markdown max-w-[85%] rounded-lg p-3 break-words ${
            role === 'user'
                ? 'bg-app-accent text-white rounded-br-none'
                : 'bg-app-tabBg text-app-textLight rounded-bl-none border border-app-border'
        }`;

        bubble.innerHTML = typeof marked !== 'undefined' ? marked.parse(content) : content.replace(/\n/g, '<br>');
        msgDiv.appendChild(bubble);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        return bubble;
    }

    // ── Send message ─────────────────────────────────────────────────────── //
    async function sendMessage() {
        if (isWaitingForResponse) return;

        const message = chatInput.value.trim();
        if (!message) return;

        chatInput.value = '';
        chatInput.style.height = 'auto';

        // Remove empty-state placeholder
        const emptyState = chatMessages.querySelector('.text-center.mt-4');
        if (emptyState) emptyState.remove();

        appendMessage('user', message);
        chatHistory.push({ role: 'user', content: message });

        isWaitingForResponse = true;
        chatSendBtn.innerHTML = '<i class="ph-fill ph-spinner animate-spin text-lg"></i>';

        const aiBubble = appendMessage('assistant', '<span class="animate-pulse">...</span>');

        try {
            const persona  = 'default';
            const provider = providerSelect?.value     || aiConfig.provider;
            const model    = modelInput?.value.trim()  || aiConfig.model;

            const response = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: chatHistory,
                    persona,
                    provider,
                    model,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch AI response');
            }

            const data = await response.json();
            const parsedHTML = typeof marked !== 'undefined' ? marked.parse(data.reply) : data.reply.replace(/\n/g, '<br>');
            aiBubble.innerHTML = parsedHTML;
            chatHistory.push({ role: 'assistant', content: data.reply });

        } catch (err) {
            console.error('Chat error:', err);
            aiBubble.innerHTML = `<span class="text-red-400">Error: ${err.message}</span>`;
            chatHistory.pop(); // Remove failed user message so they can retry
        } finally {
            isWaitingForResponse = false;
            chatSendBtn.innerHTML = '<i class="ph-fill ph-paper-plane-right text-lg"></i>';
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    chatSendBtn.addEventListener('click', sendMessage);

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = this.scrollHeight + 'px';
        this.style.overflowY =
            this.scrollHeight > parseInt(getComputedStyle(this).maxHeight)
                ? 'auto'
                : 'hidden';
    });

    // ── Boot ─────────────────────────────────────────────────────────────── //
    loadProviders();
});
