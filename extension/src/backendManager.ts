/**
 * BackendManager — Spawns the Python API server and manages WebSocket communication.
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';
import WebSocket from 'ws';

export interface StageInfo {
    status: 'pending' | 'running' | 'complete' | 'failed';
    detail: string;
}

export interface PipelineState {
    status: 'idle' | 'running' | 'complete' | 'failed' | 'error';
    current_stage: string;
    stages: Record<string, StageInfo>;
    errors: string[];
    final_summary: string | null;
    result: Record<string, any> | null;
}

export type StateChangeHandler = (state: PipelineState) => void;
export type RunCompleteHandler = (state: PipelineState) => void;
export type ConfigHandler = (config: Record<string, any>) => void;

export class BackendManager {
    private process: cp.ChildProcess | null = null;
    private ws: WebSocket | null = null;
    private outputChannel: vscode.OutputChannel;
    private port: number;
    private pythonPath: string;
    private projectRoot: string;
    private reconnectTimer: NodeJS.Timeout | null = null;
    private isShuttingDown = false;

    private onStateChange: StateChangeHandler | null = null;
    private onRunComplete: RunCompleteHandler | null = null;
    private onConfig: ConfigHandler | null = null;

    constructor(outputChannel: vscode.OutputChannel) {
        this.outputChannel = outputChannel;

        const config = vscode.workspace.getConfiguration('afterburner');
        this.port = config.get<number>('backendPort', 7777);
        this.pythonPath = config.get<string>('pythonPath', 'python');
        this.projectRoot = this.getProjectRoot();
    }

    private getProjectRoot(): string {
        const folders = vscode.workspace.workspaceFolders;
        if (folders && folders.length > 0) {
            return folders[0].uri.fsPath;
        }
        return process.cwd();
    }

    /** Register a callback for state updates. */
    setOnStateChange(handler: StateChangeHandler): void {
        this.onStateChange = handler;
    }

    /** Register a callback for run completion. */
    setOnRunComplete(handler: RunCompleteHandler): void {
        this.onRunComplete = handler;
    }

    /** Register a callback for config responses. */
    setOnConfig(handler: ConfigHandler): void {
        this.onConfig = handler;
    }

    /** Start the Python backend process and connect WebSocket. */
    async start(): Promise<void> {
        this.isShuttingDown = false;
        this.outputChannel.appendLine('🔥 Starting AfterBurner backend...');

        // Spawn the Python process
        const env = {
            ...process.env,
            AFTERBURNER_PORT: String(this.port),
        };

        this.process = cp.spawn(
            this.pythonPath,
            ['-m', 'integrations.api_server'],
            {
                cwd: this.projectRoot,
                env,
                stdio: ['ignore', 'pipe', 'pipe'],
            }
        );

        // Pipe stdout/stderr to Output Channel
        this.process.stdout?.on('data', (data: Buffer) => {
            this.outputChannel.appendLine(data.toString().trim());
        });

        this.process.stderr?.on('data', (data: Buffer) => {
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
    private async waitForServer(maxAttempts = 20): Promise<void> {
        for (let i = 0; i < maxAttempts; i++) {
            try {
                const response = await fetch(`http://127.0.0.1:${this.port}/health`);
                if (response.ok) {
                    this.outputChannel.appendLine(`✅ Backend ready on port ${this.port}`);
                    return;
                }
            } catch {
                // Server not ready yet
            }
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        this.outputChannel.appendLine('⚠️ Backend did not start within 10s — continuing anyway');
    }

    /** Connect to the WebSocket endpoint. */
    private connectWebSocket(): void {
        if (this.isShuttingDown) { return; }

        const url = `ws://127.0.0.1:${this.port}/ws`;
        this.outputChannel.appendLine(`Connecting to WebSocket: ${url}`);

        this.ws = new WebSocket(url);

        this.ws.on('open', () => {
            this.outputChannel.appendLine('✅ WebSocket connected');
        });

        this.ws.on('message', (data: WebSocket.Data) => {
            try {
                const message = JSON.parse(data.toString());
                this.handleMessage(message);
            } catch (e) {
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
    private handleMessage(message: { type: string; data: any }): void {
        switch (message.type) {
            case 'state_update':
                this.onStateChange?.(message.data as PipelineState);
                break;
            case 'run_complete':
                this.onRunComplete?.(message.data as PipelineState);
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
    private scheduleReconnect(): void {
        if (this.reconnectTimer) { return; }
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connectWebSocket();
        }, 2000);
    }

    /** Send a command to the backend via WebSocket. */
    send(command: string, data: Record<string, any> = {}): void {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
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
    isConnected(): boolean {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    /** Stop the backend and clean up. */
    async stop(): Promise<void> {
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
