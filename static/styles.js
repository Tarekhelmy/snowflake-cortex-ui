x   // Config - API base URL (change this to your FastAPI backend address)
const API_BASE_URL = '/api';

// DOM Elements
const sidebar = document.getElementById('sidebar');
const menuBtn = document.getElementById('menuBtn');
const newChatBtn = document.getElementById('newChatBtn');
const conversationsList = document.getElementById('conversationsList');
const messagesContainer = document.getElementById('messagesContainer');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');

// State
let conversations = [];
let currentConversationId = null;
let messages = [{
    role: 'assistant',
    content: "Hello! I'm your Snowflake Cortex assistant. How can I help you with your data today?",
    id: 'welcome'
}];
let isLoading = false;

// Auto-resize textarea based on content
messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = (messageInput.scrollHeight < 200) ? 
        messageInput.scrollHeight + 'px' : '200px';
});

// Toggle sidebar
menuBtn.addEventListener('click', () => {
    sidebar.classList.toggle('closed');
});

// Send message on enter (unless shift+enter)
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Send message on button click
sendBtn.addEventListener('click', sendMessage);

// Send message to API
async function sendMessage() {
    const content = messageInput.value.trim();
    if (!content || isLoading) return;
    
    // Clear input and reset height
    messageInput.value = '';
    messageInput.style.height = 'auto';
    
    // Add user message to UI
    const userMessageId = 'msg-' + Date.now();
    messages.push({
        role: 'user',
        content: content,
        id: userMessageId
    });
    renderMessages();
    
    // Show loading indicator
    isLoading = true;
    const loadingMessage = document.createElement('div');
    loadingMessage.className = 'message assistant';
    loadingMessage.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content loading-indicator">
            <svg class="loading-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2V6M12 18V22M6 12H2M22 12H18M19.07 4.93L16.24 7.76M7.76 16.24L4.93 19.07M19.07 19.07L16.24 16.24M7.76 7.76L4.93 4.93" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Thinking...
        </div>
    `;
    messagesContainer.appendChild(loadingMessage);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    try {
        const response = await fetch(`${API_BASE_URL}/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: content,
                conversation_id: currentConversationId
            })
        });
        
        // Remove loading message
        messagesContainer.removeChild(loadingMessage);
        
        if (response.ok) {
            const assistantMessage = await response.json();
            messages.push(assistantMessage);
            
            // If this was a new conversation, update conversation ID and fetch conversations list
            if (!currentConversationId && assistantMessage.conversation_id) {
                currentConversationId = assistantMessage.conversation_id;
                await fetchConversations();
                renderConversations();
            }
        } else {
            // Handle error
            const error = await response.json();
            messages.push({
                role: 'assistant',
                content: `Error: ${error.detail || 'Failed to get response from server'}`,
                id: 'error-' + Date.now()
            });
        }
    } catch (error) {
        // Remove loading message
        messagesContainer.removeChild(loadingMessage);
        
        console.error('Error sending message:', error);
        messages.push({
            role: 'assistant',
            content: 'Sorry, there was a network error. Please try again later.',
            id: 'error-' + Date.now()
        });
    } finally {
        isLoading = false;
        renderMessages();
    }
}

// Start new conversation
newChatBtn.addEventListener('click', startNewConversation);

// Initialize app
init();

// Initialize app
async function init() {
    try {
        await fetchConversations();
        renderConversations();
        renderMessages();
    } catch (error) {
        console.error('Error initializing app:', error);
    }
}

// Fetch conversations from API
async function fetchConversations() {
    try {
        const response = await fetch(`${API_BASE_URL}/conversations`);
        if (response.ok) {
            conversations = await response.json();
        }
    } catch (error) {
        console.error('Error fetching conversations:', error);
    }
}

// Load conversation messages
async function loadConversation(id) {
    try {
        const response = await fetch(`${API_BASE_URL}/conversations/${id}`);
        if (response.ok) {
            const conversation = await response.json();
            currentConversationId = conversation.id;
            messages = conversation.messages;
            renderMessages();
            renderConversations(); // Re-render to update active state
        }
    } catch (error) {
        console.error('Error loading conversation:', error);
    }
}

// Delete conversation
async function deleteConversation(id) {
    try {
        const response = await fetch(`${API_BASE_URL}/conversations/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // Remove from conversations array
            conversations = conversations.filter(conv => conv.id !== id);
            
            // If current conversation was deleted, start a new one
            if (currentConversationId === id) {
                startNewConversation();
            }
            
            renderConversations();
        }
    } catch (error) {
        console.error('Error deleting conversation:', error);
    }
}

// Start a new conversation
function startNewConversation() {
    currentConversationId = null;
    messages = [{
        role: 'assistant',
        content: "Hello! I'm your Snowflake Cortex assistant. How can I help you with your data today?",
        id: 'welcome'
    }];
    renderMessages();
}

// Function to render conversations
function renderConversations() {
    conversationsList.innerHTML = '';
    conversations.forEach(conv => {
        const convDiv = document.createElement('div');
        convDiv.className = `conversation-item ${currentConversationId === conv.id ? 'active' : ''}`;
        convDiv.dataset.id = conv.id;
        
        const titleSpan = document.createElement('span');
        titleSpan.className = 'conversation-title';
        titleSpan.textContent = conv.title;
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-button';
        deleteBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 6H5H21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M8 6V4C8 3.46957 8.21071 2.96086 8.58579 2.58579C8.96086 2.21071 9.46957 2 10 2H14C14.5304 2 15.0391 2.21071 15.4142 2.58579C15.7893 2.96086 16 3.46957 16 4V6M19 6V20C19 20.5304 18.7893 21.0391 18.4142 21.4142C18.0391 21.7893 17.5304 22 17 22H7C6.46957 22 5.96086 21.7893 5.58579 21.4142C5.21071 21.0391 5 20.5304 5 20V6H19Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;
        
        convDiv.appendChild(titleSpan);
        convDiv.appendChild(deleteBtn);
        conversationsList.appendChild(convDiv);
        
        // Add event listeners
        convDiv.addEventListener('click', () => loadConversation(conv.id));
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteConversation(conv.id);
        });
    });
}

// Function to render messages
function renderMessages() {
    messagesContainer.innerHTML = '';
    messages.forEach(message => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${message.role}`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.textContent = message.role === 'assistant' ? 'AI' : 'You';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // Process markdown-like code syntax
        let content = message.content;
        // Process code blocks (```code```)
        content = content.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        // Process inline code (`code`)
        content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        contentDiv.innerHTML = content;
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        messagesContainer.appendChild(messageDiv);
    });
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}