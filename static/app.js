// Web UI JavaScript - 处理用户交互和 API 通信

const API_BASE = '/api';
let ws = null;
let autoScroll = true;

// DOM 元素
const elements = {
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText'),
    startBtn: document.getElementById('startBtn'),
    stopBtn: document.getElementById('stopBtn'),
    restartBtn: document.getElementById('restartBtn'),
    forwardedCount: document.getElementById('forwardedCount'),
    filteredCount: document.getElementById('filteredCount'),
    totalCount: document.getElementById('totalCount'),
    configForm: document.getElementById('configForm'),
    logContainer: document.getElementById('logContainer'),
    clearLogsBtn: document.getElementById('clearLogsBtn'),
    autoScrollCheckbox: document.getElementById('autoScroll')
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    updateStatus();
    connectWebSocket();
    setupEventListeners();

    // 定期更新状态
    setInterval(updateStatus, 3000);
});

// 设置事件监听器
function setupEventListeners() {
    elements.startBtn.addEventListener('click', startBot);
    elements.stopBtn.addEventListener('click', stopBot);
    elements.restartBtn.addEventListener('click', restartBot);
    elements.configForm.addEventListener('submit', saveConfig);
    elements.clearLogsBtn.addEventListener('click', clearLogs);
    elements.autoScrollCheckbox.addEventListener('change', (e) => {
        autoScroll = e.target.checked;
    });
}

// API 请求函数
async function apiRequest(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(`${API_BASE}${endpoint}`, options);
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || '请求失败');
        }

        return result;
    } catch (error) {
        console.error('API 请求错误:', error);
        showNotification('错误: ' + error.message, 'error');
        throw error;
    }
}

// 加载配置
async function loadConfig() {
    try {
        const config = await apiRequest('/config');

        // 填充表单
        document.getElementById('sourceChats').value =
            config.config.source_chats.join('\n');
        document.getElementById('targetChats').value =
            (config.config.target_chats || []).join('\n');
        document.getElementById('regexPatterns').value =
            config.config.filters.regex_patterns.join('\n');
        document.getElementById('keywords').value =
            config.config.filters.keywords.join('\n');
        document.getElementById('filterMode').value =
            config.config.filters.mode;
        document.getElementById('preserveFormat').checked =
            config.config.forwarding.preserve_format;
        document.getElementById('addSourceInfo').checked =
            config.config.forwarding.add_source_info;
        document.getElementById('forwardDelay').value =
            config.config.forwarding.delay;

        console.log('配置已加载');
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

// 保存配置
async function saveConfig(e) {
    e.preventDefault();

    try {
        // 解析输入
        const sourceChats = document.getElementById('sourceChats').value
            .split('\n')
            .map(s => s.trim())
            .filter(s => s)
            .map(s => isNaN(s) ? s : parseInt(s));

        const targetChats = document.getElementById('targetChats').value
            .split('\n')
            .map(s => s.trim())
            .filter(s => s)
            .map(s => isNaN(s) ? s : parseInt(s));

        const regexPatterns = document.getElementById('regexPatterns').value
            .split('\n')
            .map(s => s.trim())
            .filter(s => s);

        const keywords = document.getElementById('keywords').value
            .split('\n')
            .map(s => s.trim())
            .filter(s => s);

        const configData = {
            source_chats: sourceChats,
            target_chats: targetChats,
            filters: {
                regex_patterns: regexPatterns,
                keywords: keywords,
                mode: document.getElementById('filterMode').value
            },
            forwarding: {
                preserve_format: document.getElementById('preserveFormat').checked,
                add_source_info: document.getElementById('addSourceInfo').checked,
                delay: parseFloat(document.getElementById('forwardDelay').value)
            }
        };

        await apiRequest('/config', 'PUT', configData);
        showNotification('配置已保存！', 'success');
    } catch (error) {
        console.error('保存配置失败:', error);
    }
}

// 更新状态
async function updateStatus() {
    try {
        const status = await apiRequest('/bot/status');

        // 更新状态指示器
        if (status.is_running) {
            elements.statusDot.className = 'status-dot running';
            elements.statusText.textContent = status.is_connected ? '运行中' : '连接中...';
            elements.startBtn.disabled = true;
            elements.stopBtn.disabled = false;
        } else {
            elements.statusDot.className = 'status-dot stopped';
            elements.statusText.textContent = '已停止';
            elements.startBtn.disabled = false;
            elements.stopBtn.disabled = true;
        }

        // 更新统计
        if (status.stats) {
            elements.forwardedCount.textContent = status.stats.forwarded || 0;
            elements.filteredCount.textContent = status.stats.filtered || 0;
            elements.totalCount.textContent = status.stats.total || 0;
        }
    } catch (error) {
        console.error('更新状态失败:', error);
    }
}

// Bot 控制
async function startBot() {
    try {
        const result = await apiRequest('/bot/start', 'POST');
        if (result.success) {
            showNotification('Bot 已启动！', 'success');
            updateStatus();
        } else {
            showNotification(result.message, 'warning');
        }
    } catch (error) {
        console.error('启动 Bot 失败:', error);
    }
}

async function stopBot() {
    try {
        const result = await apiRequest('/bot/stop', 'POST');
        if (result.success) {
            showNotification('Bot 已停止！', 'info');
            updateStatus();
        } else {
            showNotification(result.message, 'warning');
        }
    } catch (error) {
        console.error('停止 Bot 失败:', error);
    }
}

async function restartBot() {
    try {
        const result = await apiRequest('/bot/restart', 'POST');
        if (result.success) {
            showNotification('Bot 已重启！', 'success');
            updateStatus();
        } else {
            showNotification(result.message, 'warning');
        }
    } catch (error) {
        console.error('重启 Bot 失败:', error);
    }
}

// WebSocket 连接
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/logs`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket 已连接');
        addLog('系统', '实时日志已连接');
    };

    ws.onmessage = (event) => {
        const logMessage = event.data;
        addLog('log', logMessage);
    };

    ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
    };

    ws.onclose = () => {
        console.log('WebSocket 已断开，3秒后重连...');
        setTimeout(connectWebSocket, 3000);
    };
}

// 添加日志
function addLog(type, message) {
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${type}`;
    logEntry.textContent = message;

    elements.logContainer.appendChild(logEntry);

    // 限制日志条数（最多1000条）
    while (elements.logContainer.children.length > 1000) {
        elements.logContainer.removeChild(elements.logContainer.firstChild);
    }

    // 自动滚动到底部
    if (autoScroll) {
        elements.logContainer.scrollTop = elements.logContainer.scrollHeight;
    }
}

// 清空日志
function clearLogs() {
    elements.logContainer.innerHTML = '';
    addLog('系统', '日志已清空');
}

// 显示通知
function showNotification(message, type = 'info') {
    addLog(type, `[通知] ${message}`);
}
