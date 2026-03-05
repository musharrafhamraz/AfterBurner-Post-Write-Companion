/**
 * AfterBurner VSCode Extension — Main entry point.
 *
 * Activates the TreeView sidebar, spawns the Python backend,
 * and registers all commands.
 */

import * as vscode from 'vscode';
import { BackendManager, PipelineState } from './backendManager';
import { PipelineTreeProvider } from './treeProvider';

let backend: BackendManager;
let pipelineTree: PipelineTreeProvider;
let outputChannel: vscode.OutputChannel;

export async function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('AfterBurner');
    outputChannel.appendLine('🔥 AfterBurner extension activating...');

    // ── TreeView Providers ──
    pipelineTree = new PipelineTreeProvider(context);

    vscode.window.registerTreeDataProvider('afterburner.pipeline', pipelineTree);

    // ── Backend Manager ──
    backend = new BackendManager(outputChannel);

    backend.setOnStateChange((state: PipelineState) => {
        pipelineTree.updateState(state);
        // Commands in the title bar will handle their own enabling/disabling via 'when' clause if needed later.
    });

    backend.setOnRunComplete((state: PipelineState) => {
        if (state.status === 'complete') {
            vscode.window.showInformationMessage('🔥 AfterBurner pipeline complete!');
        } else if (state.status === 'failed' || state.status === 'error') {
            const errorMsg = state.errors.length > 0
                ? state.errors[state.errors.length - 1]
                : 'Unknown error';
            vscode.window.showErrorMessage(`AfterBurner failed: ${errorMsg}`);
        }

        // Show the final summary in the output channel
        if (state.final_summary) {
            outputChannel.appendLine('\n' + '='.repeat(60));
            outputChannel.appendLine(state.final_summary);
            outputChannel.appendLine('='.repeat(60) + '\n');
        }
    });

    backend.setOnConfig((config: Record<string, any>) => {
        const lines = Object.entries(config)
            .map(([key, value]) => `  ${key}: ${value}`)
            .join('\n');
        vscode.window.showInformationMessage('AfterBurner Config', { modal: false });
        outputChannel.appendLine(`\n🔧 Configuration:\n${lines}\n`);
        outputChannel.show();
    });

    // Start the backend
    try {
        await backend.start();
    } catch (error) {
        outputChannel.appendLine(`Failed to start backend: ${error}`);
        vscode.window.showWarningMessage(
            'AfterBurner backend failed to start. Commands will attempt to reconnect.'
        );
    }

    // ── Register Commands ──

    context.subscriptions.push(
        vscode.commands.registerCommand('afterburner.run', () => {
            if (!backend.isConnected()) {
                vscode.window.showWarningMessage('AfterBurner backend not connected.');
                return;
            }
            const config = vscode.workspace.getConfiguration('afterburner');
            const skipDeploy = config.get<boolean>('skipDeploy', true);
            outputChannel.appendLine('🚀 Starting full pipeline...');
            outputChannel.show();
            backend.send('run', { skip_deploy: skipDeploy });
        }),

        vscode.commands.registerCommand('afterburner.security', () => {
            if (!backend.isConnected()) {
                vscode.window.showWarningMessage('AfterBurner backend not connected.');
                return;
            }
            outputChannel.appendLine('🛡️ Starting security scan...');
            outputChannel.show();
            backend.send('security');
        }),

        vscode.commands.registerCommand('afterburner.test', () => {
            if (!backend.isConnected()) {
                vscode.window.showWarningMessage('AfterBurner backend not connected.');
                return;
            }
            outputChannel.appendLine('🧪 Starting test run...');
            outputChannel.show();
            backend.send('test');
        }),

        vscode.commands.registerCommand('afterburner.commit', () => {
            if (!backend.isConnected()) {
                vscode.window.showWarningMessage('AfterBurner backend not connected.');
                return;
            }
            outputChannel.appendLine('📦 Starting git commit...');
            outputChannel.show();
            backend.send('commit');
        }),

        vscode.commands.registerCommand('afterburner.deploy', () => {
            if (!backend.isConnected()) {
                vscode.window.showWarningMessage('AfterBurner backend not connected.');
                return;
            }
            outputChannel.appendLine('🚀 Starting deployment...');
            outputChannel.show();
            backend.send('deploy');
        }),

        vscode.commands.registerCommand('afterburner.stop', () => {
            outputChannel.appendLine('⏹ Stopping pipeline...');
            vscode.window.showInformationMessage('AfterBurner: Stopping (process will finish current node).');
            pipelineTree.reset();
        }),

        vscode.commands.registerCommand('afterburner.showStatus', () => {
            if (!backend.isConnected()) {
                vscode.window.showWarningMessage('AfterBurner backend not connected.');
                return;
            }
            backend.send('status');
        }),

        vscode.commands.registerCommand('afterburner.showReport', () => {
            if (outputChannel) {
                outputChannel.show();
            }
        }),
    );

    // ── Disposables ──
    context.subscriptions.push(outputChannel);

    outputChannel.appendLine('✅ AfterBurner extension activated');
}

export async function deactivate() {
    if (backend) {
        await backend.stop();
    }
}
