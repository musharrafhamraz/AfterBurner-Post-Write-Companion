/**
 * TreeView providers for the AfterBurner sidebar.
 *
 *
 * Two views:
 * 1. PipelineTreeProvider — shows pipeline stages with live status
 */
import * as vscode from 'vscode';
import { PipelineState } from './backendManager';
export declare class PipelineTreeProvider implements vscode.TreeDataProvider<PipelineItem> {
    private context;
    private _onDidChangeTreeData;
    readonly onDidChangeTreeData: vscode.Event<void | PipelineItem | undefined>;
    private state;
    constructor(context: vscode.ExtensionContext);
    updateState(state: PipelineState): void;
    reset(): void;
    getTreeItem(element: PipelineItem): vscode.TreeItem;
    getChildren(element?: PipelineItem): PipelineItem[];
    private getStatusLabel;
    private createStageItem;
}
export declare class PipelineItem extends vscode.TreeItem {
    readonly label: string;
    readonly collapsibleState: vscode.TreeItemCollapsibleState;
    children: PipelineItem[] | undefined;
    constructor(label: string, collapsibleState: vscode.TreeItemCollapsibleState);
}
