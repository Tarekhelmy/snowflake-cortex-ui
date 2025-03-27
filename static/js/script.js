// Define API endpoints and DOM elements
const API_BASE_URL = window.location.origin; // Use the window location for relative paths
const chatContainer = document.getElementById('chat-container');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-btn');
const clearChatButton = document.getElementById('clear-chat');
const semanticModelSelect = document.getElementById('semantic-model-select');
const connectionStatus = document.getElementById('connection-status');

// State variables
let messages = [];
let currentConversationId = null;
let selectedSemanticModel = null;
let isWaitingForResponse = false;

// Initialize the chat
async function initChat() {
    try {
        // Fetch available semantic models
        const response = await fetch(`${API_BASE_URL}/semantic-models`);
        if (!response.ok) throw new Error('Failed to fetch semantic models');
        
        const data = await response.json();
        semanticModelSelect.innerHTML = '';
        
        data.models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.path;
            option.textContent = model.name;
            semanticModelSelect.appendChild(option);
        });
        
        if (data.models.length > 0) {
            selectedSemanticModel = data.models[0].path;
            semanticModelSelect.value = selectedSemanticModel;
        }
        
        connectionStatus.textContent = 'Status: Connected';
        connectionStatus.style.color = 'green';
        
        // Add initial system message
        addSystemMessage('Welcome to Cortex Analyst! Ask me anything about your data.');
        
        // Add a default first question
        setTimeout(() => {
            sendMessage('What questions can I ask?');
        }, 500);
        
    } catch (error) {
        console.error('Initialization error:', error);
        connectionStatus.textContent = 'Status: Connection Error';
        connectionStatus.style.color = 'red';
        addSystemMessage('Failed to connect to the server. Please check your connection and try again.');
    }
}

// Send a message to the API
async function sendMessage(text) {
    if (!text.trim() || isWaitingForResponse) return;
    
    isWaitingForResponse = true;
    addUserMessage(text);
    
    // Show loading indicator
    const loadingElement = document.createElement('div');
    loadingElement.className = 'message analyst-message loading';
    loadingElement.innerHTML = `
        <div class="loading-spinner"></div>
        <div>Thinking...</div>
    `;
    chatContainer.appendChild(loadingElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    try {
        // Prepare the message payload
        const newMessage = {
            role: 'user',
            content: [{ type: 'text', text: text }]
        };
        
        messages.push(newMessage);
        
        // Create the request payload exactly matching the expected format
        const requestPayload = {
            messages: messages,
            semantic_model_file: selectedSemanticModel ? `@${selectedSemanticModel}` : ""
        };
        
        console.log("Sending request with payload:", requestPayload);
        
        const response = await fetch(`${API_BASE_URL}/analyst/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestPayload)
        });
        
        // Remove loading indicator
        chatContainer.removeChild(loadingElement);
        
        if (!response.ok) {
            throw new Error(`Failed to get response from server: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        currentConversationId = data.request_id;
        
        // Add analyst message
        const analystMessage = {
            role: 'analyst',
            content: data.message.content,
            request_id: data.request_id
        };
        
        messages.push(analystMessage);
        addAnalystMessage(analystMessage);
        
        // Display warnings if any
        if (data.warnings && data.warnings.length > 0) {
            displayWarnings(data.warnings);
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        // Remove loading indicator if it's still there
        if (chatContainer.contains(loadingElement)) {
            chatContainer.removeChild(loadingElement);
        }
        addSystemMessage(`Error: Failed to get a response. ${error.message}`);
    } finally {
        isWaitingForResponse = false;
    }
}

// Add a user message to the chat
function addUserMessage(text) {
    const timestamp = new Date().toLocaleTimeString();
    const messageElement = document.createElement('div');
    messageElement.className = 'message user-message';
    messageElement.innerHTML = `
        <div class="message-content">${text}</div>
        <div class="message-time">${timestamp}</div>
    `;
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    userInput.value = '';
}

// Add a system message to the chat
function addSystemMessage(text) {
    const timestamp = new Date().toLocaleTimeString();
    const messageElement = document.createElement('div');
    messageElement.className = 'message analyst-message';
    messageElement.innerHTML = `
        <div class="message-content">${text}</div>
        <div class="message-time">${timestamp}</div>
    `;
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Add an analyst message to the chat
function addAnalystMessage(message) {
    const timestamp = new Date().toLocaleTimeString();
    const messageElement = document.createElement('div');
    messageElement.className = 'message analyst-message';
    messageElement.dataset.requestId = message.request_id;
    
    let contentHTML = '';
    
    message.content.forEach(item => {
        if (item.type === 'text') {
            // Convert markdown-like syntax to HTML
            let text = item.text
                .replace(/```([a-z]*)\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
            
            contentHTML += `<div>${text}</div>`;
        } else if (item.type === 'suggestions') {
            contentHTML += '<div class="suggestions">';
            item.suggestions.forEach(suggestion => {
                contentHTML += `<button class="suggestion-btn">${suggestion}</button>`;
            });
            contentHTML += '</div>';
        } else if (item.type === 'sql') {
            contentHTML += `
                <div class="sql-result">
                    <div class="sql-tabs">
                        <div class="sql-tab active" data-tab="query">SQL Query</div>
                        <div class="sql-tab" data-tab="data">Data</div>
                        <div class="sql-tab" data-tab="chart">Chart</div>
                    </div>
                    <div class="tab-content active" data-content="query">
                        <div class="sql-query">${item.statement}</div>
                    </div>
                    <div class="tab-content" data-content="data">
                        <div class="sql-data-container">Loading data...</div>
                    </div>
                    <div class="tab-content" data-content="chart">
                        <div class="chart-container">
                            <p>Select columns to visualize:</p>
                            <div class="chart-options">Loading options...</div>
                        </div>
                    </div>
                    <div class="feedback-section">
                        <p>Was this SQL query helpful?</p>
                        <div class="feedback-buttons">
                            <button class="btn btn-secondary feedback-btn" data-value="positive">👍 Yes</button>
                            <button class="btn btn-secondary feedback-btn" data-value="negative">👎 No</button>
                        </div>
                        <textarea class="feedback-text" placeholder="Optional feedback..."></textarea>
                        <button class="btn submit-feedback-btn">Submit Feedback</button>
                    </div>
                </div>
            `;
            
            // Execute the SQL query to get the data
            executeSQL(item.statement, messageElement);
        }
    });
    
    messageElement.innerHTML = `
        <div class="message-content">${contentHTML}</div>
        <div class="message-time">${timestamp}</div>
    `;
    
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    // Add event listeners for suggestion buttons
    messageElement.querySelectorAll('.suggestion-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            sendMessage(btn.textContent);
        });
    });
    
    // Add event listeners for SQL tabs
    messageElement.querySelectorAll('.sql-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            const tabContent = messageElement.querySelector(`[data-content="${tabName}"]`);
            
            // Remove active class from all tabs and contents
            messageElement.querySelectorAll('.sql-tab').forEach(t => t.classList.remove('active'));
            messageElement.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Add active class to clicked tab and its content
            tab.classList.add('active');
            tabContent.classList.add('active');
        });
    });
    
    // Add event listeners for feedback buttons
    messageElement.querySelectorAll('.feedback-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const feedback = btn.dataset.value;
            const feedbackSection = btn.closest('.feedback-section');
            feedbackSection.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    
    // Add event listener for feedback submission
    messageElement.querySelectorAll('.submit-feedback-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const feedbackSection = btn.closest('.feedback-section');
            const activeBtn = feedbackSection.querySelector('.feedback-btn.active');
            const feedbackText = feedbackSection.querySelector('.feedback-text').value;
            
            if (activeBtn) {
                const isPositive = activeBtn.dataset.value === 'positive';
                submitFeedback(message.request_id, isPositive, feedbackText);
            }
        });
    });
}

// Execute SQL query and display results
async function executeSQL(query, messageElement) {
    try {
        const response = await fetch(`${API_BASE_URL}/execute-sql`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query })
        });
        
        if (!response.ok) throw new Error('Failed to execute SQL query');
        
        const data = await response.json();
        
        if (data.success && data.data.length > 0) {
            // Create a table for the data
            let tableHTML = '<table class="data-table"><thead><tr>';
            
            // Add table headers
            data.columns.forEach(column => {
                tableHTML += `<th>${column}</th>`;
            });
            
            tableHTML += '</tr></thead><tbody>';
            
            // Add table rows
            data.data.forEach(row => {
                tableHTML += '<tr>';
                data.columns.forEach(column => {
                    tableHTML += `<td>${row[column] !== null ? row[column] : ''}</td>`;
                });
                tableHTML += '</tr>';
            });
            
            tableHTML += '</tbody></table>';
            
            // Update the data tab
            const dataContainer = messageElement.querySelector('.sql-data-container');
            dataContainer.innerHTML = tableHTML;
            
            // Update chart options
            const chartOptions = messageElement.querySelector('.chart-options');
            let chartHTML = '';
            
            if (data.columns.length >= 2) {
                chartHTML += `
                    <div class="chart-selects">
                        <select class="x-axis-select">
                            <option value="" disabled selected>Select X-Axis</option>
                            ${data.columns.map(col => `<option value="${col}">${col}</option>`).join('')}
                        </select>
                        <select class="y-axis-select">
                            <option value="" disabled selected>Select Y-Axis</option>
                            ${data.columns.map(col => `<option value="${col}">${col}</option>`).join('')}
                        </select>
                        <select class="chart-type-select">
                            <option value="line">Line Chart</option>
                            <option value="bar">Bar Chart</option>
                        </select>
                        <button class="btn generate-chart-btn">Generate Chart</button>
                    </div>
                    <div class="chart-display"></div>
                `;
                chartOptions.innerHTML = chartHTML;
                
                // Add event listener for chart generation
                const generateBtn = chartOptions.querySelector('.generate-chart-btn');
                generateBtn.addEventListener('click', () => {
                    const xAxis = chartOptions.querySelector('.x-axis-select').value;
                    const yAxis = chartOptions.querySelector('.y-axis-select').value;
                    const chartType = chartOptions.querySelector('.chart-type-select').value;
                    
                    if (xAxis && yAxis) {
                        // Here you would generate a chart with your preferred charting library
                        // For this example, we'll just display a placeholder
                        const chartDisplay = chartOptions.querySelector('.chart-display');
                        chartDisplay.innerHTML = `
                            <div style="background-color: #f0f0f0; padding: 20px; border-radius: 5px; text-align: center;">
                                <p>Chart would be displayed here</p>
                                <p>X-Axis: ${xAxis}, Y-Axis: ${yAxis}, Type: ${chartType}</p>
                                <p>In a production environment, integrate a charting library like Chart.js</p>
                            </div>
                        `;
                    }
                });
            } else {
                chartOptions.innerHTML = '<p>Not enough columns for visualization</p>';
            }
        } else {
            messageElement.querySelector('.sql-data-container').innerHTML = '<p>No data returned</p>';
            messageElement.querySelector('.chart-options').innerHTML = '<p>No data available for visualization</p>';
        }
        
    } catch (error) {
        console.error('Error executing SQL:', error);
        messageElement.querySelector('.sql-data-container').innerHTML = '<p>Error executing SQL query</p>';
        messageElement.querySelector('.chart-options').innerHTML = '<p>Error executing SQL query</p>';
    }
}

// Submit feedback for a query
async function submitFeedback(requestId, positive, feedbackMessage) {
    try {
        const response = await fetch(`${API_BASE_URL}/analyst/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                request_id: requestId,
                positive: positive,
                feedback_message: feedbackMessage
            })
        });
        
        if (!response.ok) throw new Error('Failed to submit feedback');
        
        // Show success message
        const messageElement = document.querySelector(`.message[data-request-id="${requestId}"]`);
        const feedbackSection = messageElement.querySelector('.feedback-section');
        feedbackSection.innerHTML = '<p>Thank you for your feedback!</p>';
        
    } catch (error) {
        console.error('Error submitting feedback:', error);
        alert('Failed to submit feedback. Please try again later.');
    }
}

// Display warnings
function displayWarnings(warnings) {
    const warningsContainer = document.createElement('div');
    warningsContainer.className = 'warnings';
    
    let warningsHTML = '<strong>⚠️ Warnings:</strong><ul>';
    warnings.forEach(warning => {
        warningsHTML += `<li>${warning.message}</li>`;
    });
    warningsHTML += '</ul>';
    
    warningsContainer.innerHTML = warningsHTML;
    chatContainer.appendChild(warningsContainer);
}

// Event listeners
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage(userInput.value);
    }
});

sendButton.addEventListener('click', () => {
    sendMessage(userInput.value);
});

clearChatButton.addEventListener('click', () => {
    messages = [];
    chatContainer.innerHTML = '';
    addSystemMessage('Chat history cleared. Ask me anything about your data.');
    
    // Delete conversation from the server if we have a conversation ID
    if (currentConversationId) {
        fetch(`${API_BASE_URL}/conversations/${currentConversationId}`, {
            method: 'DELETE'
        }).catch(error => {
            console.error('Error deleting conversation:', error);
        });
        currentConversationId = null;
    }
});

semanticModelSelect.addEventListener('change', (e) => {
    selectedSemanticModel = e.target.value;
    // When changing semantic model, clear chat
    messages = [];
    chatContainer.innerHTML = '';
    addSystemMessage(`Semantic model changed to ${selectedSemanticModel.split('/').pop()}`);
});

// Initialize the chat when the page loads
document.addEventListener('DOMContentLoaded', () => {
    initChat();
});