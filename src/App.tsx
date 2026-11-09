import React, { useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bug,
  Calculator,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import { ScannerTerminalView, ScannerOpportunity } from './components/ScannerTerminalView';
import { BacktestAnalyticsView } from './components/BacktestAnalyticsView';
import { AuditAndCodeView } from './components/AuditAndCodeView';
import { PositionSimulatorView } from './components/PositionSimulatorView';
import { AuditedTradeRow, CategoryAuditStat } from './lib/quantEngine';
import { BugReportItem, FixedPythonFile } from './lib/fixedPythonTemplates';

type ActiveTab = 'scanner' | 'backtest' | 'audit' | 'simulator';

interface DatasetPayload {
  auditResult: {
    trades: AuditedTradeRow[];
    summary: {
      totalMarkets: number;
      resolvedCount: number;
      pendingCount: number;
      legacyWinCount: number;
      legacyWinRatePct: number;
      legacyTotalReturnPct: number;
      legacyAvgReturnPct: number;
      repairedWinCount: number;
      repairedWinRatePct: number;
      repairedSecondarySaveCount: number;
      repairedTotalReturnPct: number;
      repairedAvgReturnPct: number;
      idealEngineTotalReturnPct: number;
      idealEngineAvgReturnPct: number;
      bug1BinaryFalseNegativesFixed: number;
      bug2MultiLegPnlCorrectedCount: number;
      bug3CategoryMisclassificationsFixed: number;
      bug6BarrierTrapAvoidedCount: number;
    };
    categoryBreakdown: CategoryAuditStat[];
  };
  opportunities: ScannerOpportunity[];
  bugs: BugReportItem[];
  fixedPythonFiles: FixedPythonFile[];
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('scanner');
  const [data, setData] = useState<DatasetPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanningLive, setScanningLive] = useState<boolean>(false);
  const [scanStatusText, setScanStatusText] = useState<string>('');
  const [bankroll, setBankroll] = useState<number>(1000);
  const [simulatorTargetOpp, setSimulatorTargetOpp] = useState<ScannerOpportunity | null>(null);

  useEffect(() => {
    fetch('/api/dataset')
      .then((r) => r.json())
      .then((payload: DatasetPayload) => {
        setData(payload);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  const handleLiveScan = async () => {
    setScanningLive(true);
    setScanStatusText('در حال دریافت داده‌های زنده از Gamma API...');
    try {
      const resp = await fetch('/api/live-scan');
      const result = await resp.json();
      if (result.opportunities && data) {
        setData({
          ...data,
          opportunities: result.opportunities,
        });
        setScanStatusText(
          result.source === 'polymarket_gamma_live'
            ? `بروزرسانی شد (${result.liveFetchedCount} بازار زنده جدید)`
            : 'کالیبراسیون مجدد از آخرین اسنپ‌شات انجام شد'
        );
      }
    } catch {
      setScanStatusText('اسنپ‌شات محلی کالیبره فعال است');
    } finally {
      setScanningLive(false);
      setTimeout(() => setScanStatusText(''), 4000);
    }
  };

  const handleOpenInSimulator = (opp: ScannerOpportunity) => {
    setSimulatorTargetOpp(opp);
    setActiveTab('simulator');
  };

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-100 flex flex-col">
      {/* Top Bar Contract: 3 Distinct Zones (Brand — 4 Nav Links — 1 Primary Action CTA) */}
      <header className="sticky top-0 z-40 bg-[#0B0F17]/95 backdrop-blur border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          {/* Zone 1: Brand Identity */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-9 h-9 bg-emerald-600/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm sm:text-base tracking-tight text-slate-100 font-mono">
                  POLYBET QUANT v2.0
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                ترمینال کوانت، سایزینگ کِلی و حسابرسی بازارهای پیش‌بینی
              </p>
            </div>
          </div>

          {/* Zone 2: 4 Primary Navigation Tabs */}
          <nav aria-label="ناوبری اصلی" className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setActiveTab('scanner')}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                activeTab === 'scanner'
                  ? 'bg-slate-800 text-emerald-400 border-b-2 border-emerald-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>ترمینال سیگنال و اسکنر</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('backtest')}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                activeTab === 'backtest'
                  ? 'bg-slate-800 text-emerald-400 border-b-2 border-emerald-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span>بک‌تست و عملکرد (67.8% vs 58.5%)</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('audit')}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                activeTab === 'audit'
                  ? 'bg-slate-800 text-emerald-400 border-b-2 border-emerald-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Bug className="w-3.5 h-3.5" />
              <span>کالبدشکافی ۱۰ باگ + کد پایتون</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('simulator')}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                activeTab === 'simulator'
                  ? 'bg-slate-800 text-emerald-400 border-b-2 border-emerald-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Calculator className="w-3.5 h-3.5" />
              <span>شبیه‌ساز کِلی و هجینگ</span>
            </button>
          </nav>

          {/* Zone 3: Single Primary Action CTA */}
          <div className="flex items-center gap-2 shrink-0">
            {scanStatusText && (
              <span className="text-[11px] text-emerald-400 hidden xl:inline">
                {scanStatusText}
              </span>
            )}
            <button
              type="button"
              onClick={handleLiveScan}
              disabled={scanningLive}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-60 text-white text-xs font-medium transition-colors whitespace-nowrap shrink-0"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${scanningLive ? 'animate-spin' : ''}`} />
              <span>بروزرسانی اسکن زنده</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {loading || !data ? (
          <div className="space-y-4">
            <div className="h-24 bg-[#0F1623] border border-slate-800 animate-pulse" />
            <div className="h-96 bg-[#0F1623] border border-slate-800 animate-pulse" />
          </div>
        ) : (
          <>
            {activeTab === 'scanner' && (
              <ScannerTerminalView
                opportunities={data.opportunities}
                bankroll={bankroll}
                onBankrollChange={setBankroll}
                onLoadInSimulator={handleOpenInSimulator}
              />
            )}

            {activeTab === 'backtest' && (
              <BacktestAnalyticsView
                trades={data.auditResult.trades}
                summary={data.auditResult.summary}
                categoryBreakdown={data.auditResult.categoryBreakdown}
              />
            )}

            {activeTab === 'audit' && (
              <AuditAndCodeView
                bugs={data.bugs}
                fixedFiles={data.fixedPythonFiles}
              />
            )}

            {activeTab === 'simulator' && (
              <PositionSimulatorView
                initialOpportunity={simulatorTargetOpp}
                defaultBankroll={bankroll}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}
