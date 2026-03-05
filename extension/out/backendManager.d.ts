/**
 * BackendManager — Spawns the Python API server and manages WebSocket communication.
 */
import * as vscode from 'vscode';
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
export declare class BackendManager {
    private process;
    private ws;
    private outputChannel;
    private port;
    private pythonPath;
    private projectRoot;
    private reconnectTimer;
    private isShuttingDown;
    private onStateChange;
    private onRunComplete;
    private onConfig;
    constructor(outputChannel: vscode.OutputChannel);
    private getProjectRoot;
    /** Register a callback for state updates. */
    setOnStateChange(handler: StateChangeHandler): void;
    /** Register a callback for run completion. */
    setOnRunComplete(handler: RunCompleteHandler): void;
    /** Register a callback for config responses. */
    setOnConfig(handler: ConfigHandler): void;
    /** Start the Python backend process and connect WebSocket. */
    start(): Promise<void>;
    /** Wait for the HTTP server to become available. */
    private waitForServer;
    /** Connect to the WebSocket endpoint. */
    private connectWebSocket;
    /** Handle incoming WebSocket messages. */
    private handleMessage;
    /** Schedule a WebSocket reconnection attempt. */
    private scheduleReconnect;
    /** Send a command to the backend via WebSocket. */
    send(command: string, data?: Record<string, any>): void;
    /** Check if the backend is connected. */
    isConnected(): boolean;
    /** Stop the backend and clean up. */
    stop(): Promise<void>;
}
