import React, { useState } from 'react';
import {
  Bug,
  FileCode2,
  Copy,
  Check,
  Download,
  AlertOctagon,
  Wrench,
  Database,
} from 'lucide-react';
import { BugReportItem, FixedPythonFile } from '../lib/fixedPythonTemplates';

interface Props {
  bugs: BugReportItem[];
  fixedFiles: FixedPythonFile[];
}

export const AuditAndCodeView: React.FC<Props> = ({ bugs, fixedFiles }) => {
  const [subTab, setSubTab] = useState<'bugs' | 'python_code'>('bugs');
  const [selectedBugId, setSelectedBugId] = useState<string>(bugs[0]?.id || '');
  const [selectedFileIndex, setSelectedFileIndex] = useState<number>(0);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const activeBug = bugs.find((b) => b.id === selectedBugId) || bugs[0];
  const activeFile = fixedFiles[selectedFileIndex] || fixedFiles[0];

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleDownloadFile = (file: FixedPythonFile) => {
    const blob = new Blob([file.code], { type: 'text/x-python;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = file.filename.replace(/\s+/g, '_');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Sub-navigation Header */}
      <div className="border border-slate-800 bg-[#0F1623] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-100">
            مرکز کالبدشکافی فنی کدهای پایتون و مخزن نسخه‌های اصلاح‌شده (PolyBet v2.0)
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            ۱۰ باگ منطقی، آماری و معماری کشف‌شده در فایل‌های پیوست‌شده به همراه شواهد واقعی از لاگ‌های CSV و کدهای اصلاح‌شده آماده جایگزینی در گیت‌هاب
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setSubTab('bugs')}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium transition-colors ${
              subTab === 'bugs'
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-900 text-slate-300 border border-slate-800 hover:text-white'
            }`}
          >
            <Bug className="w-3.5 h-3.5" />
            <span>کالبدشکافی ۱۱ باگ بحرانی (شامل ورک‌فلوها)</span>
          </button>

          <button
            type="button"
            onClick={() => setSubTab('python_code')}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium transition-colors ${
              subTab === 'python_code'
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-900 text-slate-300 border border-slate-800 hover:text-white'
            }`}
          >
            <FileCode2 className="w-3.5 h-3.5" />
            <span>فولدر .github/workflows و کدهای اصلاح‌شده ({fixedFiles.length} فایل)</span>
          </button>
        </div>
      </div>

      {subTab === 'bugs' ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left / Right Sidebar of 10 Bugs */}
          <div className="lg:col-span-4 border border-slate-800 bg-[#0F1623] divide-y divide-slate-800">
            {bugs.map((bug) => {
              const isSelected = bug.id === activeBug?.id;
              return (
                <button
                  key={bug.id}
                  type="button"
                  onClick={() => setSelectedBugId(bug.id)}
                  className={`w-full text-right p-3.5 transition-colors flex items-start gap-3 ${
                    isSelected ? 'bg-slate-800/80' : 'hover:bg-slate-900/60'
                  }`}
                >
                  <span
                    className={`font-mono tabular-nums text-xs font-bold px-2 py-0.5 border shrink-0 ${
                      bug.severity === 'CRITICAL'
                        ? 'text-rose-400 border-rose-800/60 bg-rose-950/30'
                        : 'text-amber-400 border-amber-800/60 bg-amber-950/30'
                    }`}
                  >
                    #{bug.number}
                  </span>
                  <div className="space-y-1 min-w-0">
                    <div className="text-xs font-bold text-slate-100 leading-snug">
                      {bug.titleFa}
                    </div>
                    <div className="text-[11px] font-mono text-slate-400 truncate" dir="ltr">
                      {bug.fileAffected}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Detailed Bug Forensic Panel */}
          {activeBug && (
            <div className="lg:col-span-8 border border-slate-800 bg-[#0F1623] p-6 space-y-5">
              <div className="border-b border-slate-800 pb-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="font-mono text-emerald-400" dir="ltr">
                    File: {activeBug.fileAffected}
                  </span>
                  <span
                    className={`font-mono font-bold ${
                      activeBug.severity === 'CRITICAL' ? 'text-rose-400' : 'text-amber-400'
                    }`}
                  >
                    شدت خطا: {activeBug.severity}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-slate-100">{activeBug.titleFa}</h3>
                <div className="text-xs font-mono text-slate-400" dir="ltr">
                  {activeBug.titleEn}
                </div>
              </div>

              {/* Impact Banner */}
              <div className="p-3.5 bg-rose-950/20 border border-rose-800/40 flex items-start gap-3">
                <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <span className="font-bold text-rose-300">تأثیر مستقیم روی عملکرد ربات: </span>
                  <span className="text-slate-200">{activeBug.impactMetric}</span>
                </div>
              </div>

              {/* Technical Explanation */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-slate-200">کالبدشکافی دقیق علت رخداد باگ:</h4>
                <p className="text-xs text-slate-300 leading-relaxed">
                  {activeBug.problemExplanationFa}
                </p>
              </div>

              {/* Real CSV Evidence */}
              <div className="p-3.5 bg-slate-900/90 border border-slate-800 space-y-1.5">
                <div className="text-xs font-bold text-sky-400 flex items-center gap-1.5">
                  <Database className="w-3.5 h-3.5" />
                  <span>سند و شواهد واقعی در فایل‌های CSV پیوست‌شده شما:</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">{activeBug.csvEvidence}</p>
              </div>

              {/* Side-by-Side Code Comparison */}
              <div className="grid grid-cols-1 gap-4">
                <div className="space-y-1.5">
                  <div className="text-xs font-bold text-rose-400">
                    کد قبلی (دارای باگ در پروژه فعلی):
                  </div>
                  <pre
                    dir="ltr"
                    className="p-3.5 bg-slate-950 border border-rose-900/40 text-xs font-mono text-rose-200 overflow-x-auto leading-relaxed"
                  >
                    <code>{activeBug.buggyCodeSnippet}</code>
                  </pre>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-emerald-400">
                      کد اصلاح‌شده و استاندارد (PolyBet v2.0):
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCopy(activeBug.fixedCodeSnippet, activeBug.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 border border-slate-700"
                    >
                      {copiedKey === activeBug.id ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span>کپی شد</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>کپی قطعه کد</span>
                        </>
                      )}
                    </button>
                  </div>
                  <pre
                    dir="ltr"
                    className="p-3.5 bg-slate-950 border border-emerald-900/40 text-xs font-mono text-emerald-200 overflow-x-auto leading-relaxed"
                  >
                    <code>{activeBug.fixedCodeSnippet}</code>
                  </pre>
                </div>
              </div>

              {/* Architectural Upgrade Note */}
              <div className="p-3.5 bg-emerald-950/20 border border-emerald-800/40 flex items-start gap-3">
                <Wrench className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <span className="font-bold text-emerald-300">ارتقای معماری اعمال‌شده: </span>
                  <span className="text-slate-200">{activeBug.architecturalUpgradeFa}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Fixed Python Modules Viewer & Downloader */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-4 border border-slate-800 bg-[#0F1623] divide-y divide-slate-800">
            {fixedFiles.map((file, idx) => (
              <button
                key={file.pathInRepo}
                type="button"
                onClick={() => setSelectedFileIndex(idx)}
                className={`w-full text-right p-4 transition-colors space-y-1 ${
                  selectedFileIndex === idx ? 'bg-slate-800/80' : 'hover:bg-slate-900/60'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-emerald-400 truncate" dir="ltr">
                    {file.pathInRepo}
                  </span>
                  <span className="text-[11px] font-mono text-slate-400 shrink-0">
                    {file.bugsFixedCount} اصلاح
                  </span>
                </div>
                <p className="text-xs text-slate-300 leading-snug">{file.descriptionFa}</p>
              </button>
            ))}
          </div>

          {activeFile && (
            <div className="lg:col-span-8 border border-slate-800 bg-[#0F1623] p-5 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-bold font-mono text-emerald-400" dir="ltr">
                    {activeFile.pathInRepo}
                  </h3>
                  <p className="text-xs text-slate-300 mt-0.5">{activeFile.descriptionFa}</p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => handleCopy(activeFile.code, activeFile.filename)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 border border-slate-700"
                  >
                    {copiedKey === activeFile.filename ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span>کپی شد</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>کپی کل فایل</span>
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => handleDownloadFile(activeFile)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-xs text-white font-medium"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>دانلود فایل .py</span>
                  </button>
                </div>
              </div>

              <pre
                dir="ltr"
                className="p-4 bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed max-h-[600px]"
              >
                <code>{activeFile.code}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
