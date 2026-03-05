"use strict";
/**
 * TreeView providers for the AfterBurner sidebar.
 *
 *
 * Two views:
 * 1. PipelineTreeProvider — shows pipeline stages with live status
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.PipelineItem = exports.PipelineTreeProvider = void 0;
const vscode = __importStar(require("vscode"));
// ──────────────────────────── Pipeline Tree ────────────────────────────
const STAGE_CONFIG = [
    { key: 'detect_changes', label: '1. Change Detection', desc: 'Analyzes your git diff to figure out what changed' },
    { key: 'security_review', label: '2. Security Sentinel', desc: 'Runs static analysis (Semgrep/Bandit) and LLM triage' },
    { key: 'test_run', label: '3. Test Pilot', desc: 'Runs tests and auto-debugs any failures' },
    { key: 'git_commit', label: '4. Git Guardian', desc: 'Generates commit message, commits, and opens a PR' },
    { key: 'deploy', label: '5. Launch Controller', desc: 'Deploys code and configures monitoring' },
    { key: 'summarize', label: '6. Output Generation', desc: 'Compiles the final pipeline summary' },
];
class PipelineTreeProvider {
    context;
    _onDidChangeTreeData = new vscode.EventEmitter();
    onDidChangeTreeData = this._onDidChangeTreeData.event;
    state = null;
    constructor(context) {
        this.context = context;
    }
    updateState(state) {
        this.state = state;
        this._onDidChangeTreeData.fire();
    }
    reset() {
        this.state = null;
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren(element) {
        if (element) {
            return element.children || [];
        }
        const items = [];
        const isIdle = !this.state || this.state.status === 'idle';
        // Progress Bar Calculation
        let completedStages = 0;
        let runningStage = -1;
        if (!isIdle) {
            for (let i = 0; i < STAGE_CONFIG.length; i++) {
                const s = this.state.stages[STAGE_CONFIG[i].key];
                if (s?.status === 'complete')
                    completedStages++;
                if (s?.status === 'running')
                    runningStage = i;
            }
        }
        const total = STAGE_CONFIG.length;
        const width = 12;
        const progressChunks = isIdle ? 0 : Math.round((completedStages / total) * width);
        let progressStr = '';
        for (let i = 0; i < width; i++) {
            if (i < progressChunks)
                progressStr += '█';
            else if (i === Math.max(0, runningStage) && !isIdle && this.state.status === 'running')
                progressStr += '▒'; // blinking/active piece
            else
                progressStr += '░';
        }
        const pct = isIdle ? 0 : Math.round((completedStages / total) * 100);
        // App Header / Status
        const statusLabel = isIdle ? 'Ready to launch' : this.getStatusLabel(this.state.status);
        const statusItem = new PipelineItem('AfterBurner Pipeline', vscode.TreeItemCollapsibleState.Expanded);
        statusItem.description = `[${progressStr}] ${pct}% — ${statusLabel}`;
        if (isIdle) {
            statusItem.iconPath = new vscode.ThemeIcon('rocket', new vscode.ThemeColor('symbolIcon.booleanForeground'));
        }
        else if (this.state.status === 'running') {
            statusItem.iconPath = new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.blue'));
        }
        else if (this.state.status === 'complete') {
            statusItem.iconPath = new vscode.ThemeIcon('pass-filled', new vscode.ThemeColor('testing.iconPassed'));
        }
        else {
            statusItem.iconPath = new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
        }
        // We nest the stages under the pipeline header for a very clean "Dashboard Object" look
        const stageItems = [];
        for (const stage of STAGE_CONFIG) {
            const stageInfo = this.state?.stages[stage.key];
            const item = this.createStageItem(stage, stageInfo);
            stageItems.push(item);
        }
        statusItem.children = stageItems;
        items.push(statusItem);
        // Errors section
        if (this.state?.errors && this.state.errors.length > 0) {
            items.push(new PipelineItem('', vscode.TreeItemCollapsibleState.None)); // spacer
            const errorItem = new PipelineItem(`Critical Errors (${this.state.errors.length})`, vscode.TreeItemCollapsibleState.Expanded);
            errorItem.iconPath = new vscode.ThemeIcon('warning', new vscode.ThemeColor('errorForeground'));
            errorItem.children = this.state.errors.map((err, idx) => {
                const child = new PipelineItem(`Issue ${idx + 1}`, vscode.TreeItemCollapsibleState.None);
                child.description = err.substring(0, 40) + '...';
                const tooltip = new vscode.MarkdownString(`**Error Detail**\n\n\`\`\`text\n${err}\n\`\`\``);
                child.tooltip = tooltip;
                child.iconPath = new vscode.ThemeIcon('circle-small');
                return child;
            });
            items.push(errorItem);
        }
        // Summary
        if (this.state?.final_summary) {
            items.push(new PipelineItem('', vscode.TreeItemCollapsibleState.None)); // spacer
            const summaryItem = new PipelineItem('View Full Output Report', vscode.TreeItemCollapsibleState.None);
            summaryItem.iconPath = new vscode.ThemeIcon('book', new vscode.ThemeColor('textLink.foreground'));
            summaryItem.command = { command: 'afterburner.showReport', title: 'Show Report' };
            items.push(summaryItem);
        }
        return items;
    }
    getStatusLabel(status) {
        switch (status) {
            case 'running': return 'Active';
            case 'complete': return 'Success';
            case 'failed': return 'Failed';
            case 'error': return 'System Error';
            default: return 'Ready';
        }
    }
    createStageItem(stage, info) {
        const status = info?.status || 'pending';
        const hasDetail = info?.detail && info.detail.length > 0;
        const item = new PipelineItem(stage.label, vscode.TreeItemCollapsibleState.None);
        // Rich Hover Tooltip
        const tooltip = new vscode.MarkdownString(`**${stage.label}**\n\n${stage.desc}`);
        if (hasDetail)
            tooltip.appendMarkdown(`\n\n---\n*Result:* ${info.detail}`);
        tooltip.isTrusted = true;
        item.tooltip = tooltip;
        if (status === 'pending') {
            item.iconPath = new vscode.ThemeIcon('circle-outline', new vscode.ThemeColor('disabledForeground'));
            item.description = 'queued';
        }
        else if (status === 'running') {
            item.iconPath = new vscode.ThemeIcon('loading~spin', new vscode.ThemeColor('charts.blue'));
            item.description = 'analyzing...';
        }
        else if (status === 'complete') {
            item.iconPath = new vscode.ThemeIcon('pass-filled', new vscode.ThemeColor('testing.iconPassed'));
            item.description = hasDetail ? info.detail : 'done';
        }
        else {
            item.iconPath = new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
            item.description = 'failed';
        }
        return item;
    }
}
exports.PipelineTreeProvider = PipelineTreeProvider;
// ──────────────────────────── Tree Item ────────────────────────────
class PipelineItem extends vscode.TreeItem {
    label;
    collapsibleState;
    children;
    constructor(label, collapsibleState) {
        super(label, collapsibleState);
        this.label = label;
        this.collapsibleState = collapsibleState;
    }
}
exports.PipelineItem = PipelineItem;
//# sourceMappingURL=treeProvider.js.map