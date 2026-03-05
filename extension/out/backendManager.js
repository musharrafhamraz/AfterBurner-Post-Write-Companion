"use strict";
/**
 * BackendManager — Spawns the Python API server and manages WebSocket communication.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.BackendManager = void 0;
const vscode = __importStar(require("vscode"));
const cp = __importStar(require("child_process"));
const ws_1 = __importDefault(require("ws"));
class BackendManager {
    process = null;
    ws = null;
    outputChannel;
    port;
    pythonPath;
    projectRoot;
    reconnectTimer = null;
    isShuttingDown = false;
    onStateChange = null;
    onRunComplete = null;
    onConfig = null;
    constructor(outputChannel) {
        this.outputChannel = outputChannel;
        const config = vscode.workspace.getConfiguration('afterburner');
        this.port = config.get('backendPort', 7777);
        this.pythonPath = config.get('pythonPath', 'python');
        this.projectRoot = this.getProjectRoot();
    }
    getProjectRoot() {
        const folders = vscode.workspace.workspaceFolders;
        if (folders && folders.length > 0) {
            return folders[0].uri.fsPath;
        }
        return process.cwd();
    }
    /** Register a callback for state updates. */
    setOnStateChange(handler) {
        this.onStateChange = handler;
    }
    /** Register a callback for run completion. */
    setOnRunComplete(handler) {
        this.onRunComplete = handler;
    }
    /** Register a callback for config responses. */
    setOnConfig(handler) {
        this.onConfig = handler;
    }
    /** Start the Python backend process and connect WebSocket. */
    async start() {
        this.isShuttingDown = false;
        this.outputChannel.appendLine('🔥 Starting AfterBurner backend...');
        // Spawn the Python process
        const env = {
            ...process.env,
            AFTERBURNER_PORT: String(this.port),
        };
        this.process = cp.spawn(this.pythonPath, ['-m', 'integrations.api_server'], {
            cwd: this.projectRoot,
            env,
            stdio: ['ignore', 'pipe', 'pipe'],
        });
        // Pipe stdout/stderr to Output Channel
        this.process.stdout?.on('data', (data) => {
            this.outputChannel.appendLine(data.toString().trim());
        });
        this.process.stderr?.on('data', (data) => {
            const text = data.toString().trim();
            if (text) {
                this.outputChannel.appendLine(text);
            }
        });
        this.process.on('exit', (code) => {
            this.outputChannel.appendLine(`Backend process exited with code ${code}`);
            if (!this.isShuttingDown) {
                this.outputChannel.appendLine('Backend crashed — attempting restart in 3s...');
                setTimeout(() => this.start(), 3000);
            }
        });
        // Wait for the server to start, then connect WebSocket
        await this.waitForServer();
        this.connectWebSocket();
    }
    /** Wait for the HTTP server to become available. */
    async waitForServer(maxAttempts = 20) {
        for (let i = 0; i < maxAttempts; i++) {
            try {
                const response = await fetch(`http://127.0.0.1:${this.port}/health`);
                if (response.ok) {
                    this.outputChannel.appendLine(`✅ Backend ready on port ${this.port}`);
                    return;
                }
            }
            catch {
                // Server not ready yet
            }
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        this.outputChannel.appendLine('⚠️ Backend did not start within 10s — continuing anyway');
    }
    /** Connect to the WebSocket endpoint. */
    connectWebSocket() {
        if (this.isShuttingDown) {
            return;
        }
        const url = `ws://127.0.0.1:${this.port}/ws`;
        this.outputChannel.appendLine(`Connecting to WebSocket: ${url}`);
        this.ws = new ws_1.default(url);
        this.ws.on('open', () => {
            this.outputChannel.appendLine('✅ WebSocket connected');
        });
        this.ws.on('message', (data) => {
            try {
                const message = JSON.parse(data.toString());
                this.handleMessage(message);
            }
            catch (e) {
                this.outputChannel.appendLine(`WS parse error: ${e}`);
            }
        });
        this.ws.on('close', () => {
            this.outputChannel.appendLine('WebSocket disconnected');
            if (!this.isShuttingDown) {
                this.scheduleReconnect();
            }
        });
        this.ws.on('error', (err) => {
            this.outputChannel.appendLine(`WebSocket error: ${err.message}`);
        });
    }
    /** Handle incoming WebSocket messages. */
    handleMessage(message) {
        switch (message.type) {
            case 'state_update':
                this.onStateChange?.(message.data);
                break;
            case 'run_complete':
                this.onRunComplete?.(message.data);
                break;
            case 'config':
                this.onConfig?.(message.data);
                break;
            case 'error':
                this.outputChannel.appendLine(`⚠️ Backend error: ${message.data}`);
                vscode.window.showErrorMessage(`AfterBurner: ${message.data}`);
                break;
        }
    }
    /** Schedule a WebSocket reconnection attempt. */
    scheduleReconnect() {
        if (this.reconnectTimer) {
            return;
        }
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connectWebSocket();
        }, 2000);
    }
    /** Send a command to the backend via WebSocket. */
    send(command, data = {}) {
        if (!this.ws || this.ws.readyState !== ws_1.default.OPEN) {
            vscode.window.showWarningMessage('AfterBurner backend is not connected. Try restarting.');
            return;
        }
        this.ws.send(JSON.stringify({
            command,
            repo_path: this.projectRoot,
            ...data,
        }));
    }
    /** Check if the backend is connected. */
    isConnected() {
        return this.ws !== null && this.ws.readyState === ws_1.default.OPEN;
    }
    /** Stop the backend and clean up. */
    async stop() {
        this.isShuttingDown = true;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        if (this.process) {
            this.process.kill();
            this.process = null;
        }
        this.outputChannel.appendLine('Backend stopped');
    }
}
exports.BackendManager = BackendManager;
//# sourceMappingURL=backendManager.js.map