/**
 * Chatbox logic for 4Dpapers AI Agent integration.
 */

document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatMessages = document.getElementById('chatMessages');
    const agentPersonaSelect = document.getElementById('agentPersonaSelect');
    
    let chatHistory = [];
    let isWaitingForResponse = false;

    // Default configuration (saved in localStorage)
    let aiConfig = JSON.parse(localStorage.getItem('4dpaper_ai_config')) || {
        provider: 'ollama', // 'ollama' or 'openai'
        model: 'llama3',    // Default ollama model
        apiKey: ''          // Empty by default
    };

    function saveConfig() {
        localStorage.setItem('4dpaper_ai_config', JSON.stringify(aiConfig));
    }

    // Modal settings integration
    window.openChatSettings = function() {
        const provider = prompt("Select Provider (ollama or openai):", aiConfig.provider);
        if (provider) {
            aiConfig.provider = provider.toLowerCase();
            const model = prompt("Enter model name (e.g. llama3, gpt-4o):", aiConfig.model);
            if (model) {
                aiConfig.model = model;
            }
            if (aiConfig.provider === 'openai') {
                const key = prompt("Enter your OpenAI API Key:");
                if (key) {
                    aiConfig.apiKey = key;
                }
            }
            saveConfig();
            alert("AI settings saved!");
        }
    };

    function appendMessage(role, content) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} w-full mb-4`;

        const bubble = document.createElement('div');
        bubble.className = `max-w-[85%] rounded-lg p-3 ${
            role === 'user' 
                ? 'bg-app-accent text-white rounded-br-none' 
                : 'bg-app-tabBg text-app-textLight rounded-bl-none border border-app-border'
        }`;
        
        // Simple line breaks for now. Can use marked.js later if imported.
        bubble.innerHTML = content.replace(/\n/g, '<br>');
        
        msgDiv.appendChild(bubble);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return bubble;
    }

    async function sendMessage() {
        if (isWaitingForResponse) return;
        
        const message = chatInput.value.trim();
        if (!message) return;
        
        // Add user message
        chatInput.value = '';
        chatInput.style.height = 'auto'; // Reset textarea height
        
        // Remove empty state text
        const emptyState = chatMessages.querySelector('.text-center.mt-4');
        if (emptyState) emptyState.remove();

        appendMessage('user', message);
        chatHistory.push({ role: 'user', content: message });
        
        isWaitingForResponse = true;
        chatSendBtn.innerHTML = '<i class="ph-fill ph-spinner animate-spin text-lg"></i>';
        
        const aiBubble = appendMessage('assistant', '<span class="animate-pulse">...</span>');
        
        try {
            const persona = agentPersonaSelect.value;
            
            const response = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    messages: chatHistory,
                    persona: persona,
                    config: aiConfig
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch AI response');
            }
            
            const data = await response.json();
            aiBubble.innerHTML = data.reply.replace(/\n/g, '<br>');
            chatHistory.push({ role: 'assistant', content: data.reply });
            
        } catch (err) {
            console.error('Chat error:', err);
            aiBubble.innerHTML = `<span class="text-red-400">Error: ${err.message}</span>`;
            // Remove the failed user message from history so they can try again
            chatHistory.pop();
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
    chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.scrollHeight > parseInt(getComputedStyle(this).maxHeight)) {
            this.style.overflowY = 'auto';
        } else {
            this.style.overflowY = 'hidden';
        }
    });
});
