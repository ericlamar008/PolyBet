import React, { useState, useMemo } from 'react';
import {
  Search,
  Sparkles,
  ExternalLink,
  AlertTriangle,
  ArrowUpDown,
  ShieldCheck,
  TrendingUp,
  Layers,
  X,
  CheckCircle2,
  Calculator,
} from 'lucide-react';
import { PositionPlanV2, CATEGORY_LABELS_FA } from '../lib/quantEngine';

export interface ScannerOpportunity {
  id: string;
  groupKey: string;
  title: string;
  category: string;
  categoryLabelFa: string;
  categoryWasFixed: boolean;
  daysToResolve: number;
  marketUrl: string;
  numSources: number;
  legacyConsensusScore: number;
  calibratedConsensusScore: number;
  legacyPrimaryOutcome: string;
  legacyPrimarySizePct: number;
  legacyPrimaryPrice: number;
  planV2: PositionPlanV2;
  sourceNames: string[];
  loggedAtUtc: string;
}

interface AiAnalysisResult {
  verdictFa: string;
  fundamentalDriversFa: string[];
  hedgeCritiqueFa: string;
  tailRisksFa: string[];
  recommendedActionFa: string;
}

interface Props {
  opportunities: ScannerOpportunity[];
  bankroll: number;
  onBankrollChange: (val: number) => void;
  onLoadInSimulator: (opp: ScannerOpportunity) => void;
}

export const ScannerTerminalView: React.FC<Props> = ({
  opportunities,
  bankroll,
  onBankrollChange,
  onLoadInSimulator,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'confidence' | 'edge' | 'ev' | 'days'>('confidence');
  const [hideBarrierTraps, setHideBarrierTraps] = useState<boolean>(false);

  const [aiModalOpp, setAiModalOpp] = useState<ScannerOpportunity | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<{ source: string; analysis: AiAnalysisResult } | null>(null);

  const categories = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const o of opportunities) {
      counts[o.category] = (counts[o.category] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [opportunities]);

  const filteredOpportunities = useMemo(() => {
    return opportunities
      .filter((o) => {
        if (selectedCategory !== 'all' && o.category !== selectedCategory) return false;
        if (hideBarrierTraps && o.planV2.isLongshotBarrierTrap) return false;
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          return (
            o.title.toLowerCase().includes(q) ||
            o.planV2.primaryOutcome.toLowerCase().includes(q) ||
            o.categoryLabelFa.includes(q)
          );
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'confidence') {
          return b.planV2.effectiveConfidenceScore - a.planV2.effectiveConfidenceScore;
        }
        if (sortBy === 'edge') {
          return Math.abs(b.planV2.edge) - Math.abs(a.planV2.edge);
        }
        if (sortBy === 'ev') {
          return b.planV2.expectedValuePct - a.planV2.expectedValuePct;
        }
        return a.daysToResolve - b.daysToResolve;
      });
  }, [opportunities, selectedCategory, hideBarrierTraps, searchQuery, sortBy]);

  const triggerAiAnalysis = async (opp: ScannerOpportunity) => {
    setAiModalOpp(opp);
    setAiLoading(true);
    setAiResult(null);
    try {
      const resp = await fetch('/api/ai-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: opp.title,
          category: opp.categoryLabelFa,
          allocations: opp.planV2.allocations,
          edge: opp.planV2.edge,
          calibratedConsensus: opp.planV2.calibratedConsensusScore,
          warning: opp.planV2.warning,
        }),
      });
      const data = await resp.json();
      setAiResult(data);
    } catch {
      setAiResult({
        source: 'fallback',
        analysis: {
          verdictFa: 'خطا در برقراری ارتباط با سرور تحلیل هوش مصنوعی.',
          fundamentalDriversFa: [],
          hedgeCritiqueFa: '',
          tailRisksFa: [],
          recommendedActionFa: 'لطفاً دوباره تلاش کنید.',
        },
      });
    } finally {
      setAiLoading(false);
    }
  };

  const trapCount = useMemo(
    () => opportunities.filter((o) => o.planV2.isLongshotBarrierTrap).length,
    [opportunities]
  );
  const binaryRepairedCount = useMemo(
    () =>
      opportunities.filter(
        (o) => o.legacyPrimaryOutcome.toLowerCase() === o.title.toLowerCase()
      ).length,
    [opportunities]
  );

  return (
    <div className="space-y-6">
      {/* Top Quantitative Summary Strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 border border-slate-800 bg-[#0F1623] divide-y md:divide-y-0 md:divide-x md:divide-x-reverse divide-slate-800">
        <div className="p-4">
          <div className="text-xs text-slate-400">فرصت‌های فعال کالیبره‌شده</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono tabular-nums text-slate-100">
              {filteredOpportunities.length}
            </span>
            <span className="text-xs text-emerald-400 font-mono tabular-nums">
              از {opportunities.length} بازار کل
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            حذف خودکار بازارهای ورزشی و اصلاح دسته‌بندی BoE
          </div>
        </div>

        <div className="p-4">
          <div className="text-xs text-slate-400">اصلاح باگ خروجی باینری (Yes/No)</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono tabular-nums text-emerald-400">
              {binaryRepairedCount}
            </span>
            <span className="text-xs text-slate-400">بازار تک‌گزینه‌ای</span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            جلوگیری از ثبت عنوان سؤال به جای گزینه «Yes» یا «No»
          </div>
        </div>

        <div className="p-4">
          <div className="text-xs text-slate-400">تله‌های آپشن مانعی شناسایی‌شده</div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono tabular-nums text-amber-400">
              {trapCount}
            </span>
            <span className="text-xs text-amber-300/80 font-mono tabular-nums">
              سقف تخصیص ۵٪
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            محافظت از سرمایه در برابر شرط‌های ۰.۱ سنتی «Hit $X»
          </div>
        </div>

        <div className="p-4">
          <label
            htmlFor="scanner-bankroll-input"
            className="block text-xs text-slate-400"
          >
            سرمایه پایه هر موقعیت (Bankroll $)
          </label>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="text-sm font-mono text-slate-400">$</span>
            <input
              id="scanner-bankroll-input"
              type="number"
              min={50}
              max={1000000}
              step={50}
              value={bankroll}
              onChange={(e) => onBankrollChange(Math.max(10, Number(e.target.value) || 1000))}
              className="w-full bg-slate-900 border border-slate-700 px-2.5 py-1 text-sm font-mono tabular-nums text-slate-100 focus:border-emerald-500 focus:outline-none"
            />
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            محاسبه زنده دلاری و تعداد سهام (Shares) برای هر پایه
          </div>
        </div>
      </div>

      {/* Filter & Search Control Bar */}
      <div className="border border-slate-800 bg-[#0F1623] p-4 space-y-3">
        <div className="flex flex-col lg:flex-row gap-3 items-stretch lg:items-center justify-between">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              aria-label="جستجوی عنوان بازار یا خروجی"
              placeholder="جستجوی بازار، تیکر سهام (PANW, AVGO, SPY)، نرخ بهره یا کاندیدا..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900/90 border border-slate-700 pr-9 pl-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
              <label htmlFor="scanner-sort-select" className="text-xs text-slate-400">
                مرتب‌سازی:
              </label>
              <select
                id="scanner-sort-select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'confidence' | 'edge' | 'ev' | 'days')}
                className="bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value="confidence">امتیاز اطمینان کالیبره (Confidence)</option>
                <option value="edge">لبه آماری مدل (Quant Edge)</option>
                <option value="ev">امید ریاضی سود خالص (Expected Value)</option>
                <option value="days">نزدیک‌ترین زمان تسویه</option>
              </select>
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none border border-slate-700 bg-slate-900 px-3 py-1.5">
              <input
                type="checkbox"
                checked={hideBarrierTraps}
                onChange={(e) => setHideBarrierTraps(e.target.checked)}
                className="accent-emerald-500"
              />
              <span>حذف بازارهای تله مانعی (Hit $X)</span>
            </label>
          </div>
        </div>

        {/* Category Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 pt-1 border-t border-slate-800/80">
          <button
            type="button"
            onClick={() => setSelectedCategory('all')}
            className={`px-3 py-1 text-xs font-medium transition-colors whitespace-nowrap ${
              selectedCategory === 'all'
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
            }`}
          >
            همه دسته‌ها ({opportunities.length})
          </button>
          {categories.map(([cat, count]) => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 text-xs font-medium transition-colors whitespace-nowrap ${
                selectedCategory === cat
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              {CATEGORY_LABELS_FA[cat] || cat} ({count})
            </button>
          ))}
        </div>
      </div>

      {/* Opportunities List */}
      {filteredOpportunities.length === 0 ? (
        <div className="border border-slate-800 bg-[#0F1623] p-12 text-center">
          <p className="text-sm text-slate-400">
            هیچ بازاری با فیلترهای انتخابی مطابقت ندارد.
          </p>
          <button
            type="button"
            onClick={() => {
              setSelectedCategory('all');
              setSearchQuery('');
              setHideBarrierTraps(false);
            }}
            className="mt-4 px-4 py-2 bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-500"
          >
            پاک کردن فیلترها
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredOpportunities.slice(0, 30).map((opp) => {
            const p = opp.planV2;
            const primaryDollar = ((bankroll * p.primarySizePct) / 100).toFixed(0);
            const wasBinaryBugRepaired =
              opp.legacyPrimaryOutcome.trim().toLowerCase() === opp.title.trim().toLowerCase();

            return (
              <article
                key={opp.id}
                className="border border-slate-800 bg-[#0F1623] hover:border-slate-700 transition-colors"
              >
                {/* Card Header */}
                <div className="p-4 border-b border-slate-800/80 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <span className="font-semibold text-emerald-400">
                        {opp.categoryLabelFa}
                      </span>
                      <span>·</span>
                      <span className="font-mono tabular-nums">
                        تسویه: {opp.daysToResolve.toFixed(1)} روز
                      </span>
                      <span>·</span>
                      <span>منابع: {opp.sourceNames.join('، ')}</span>
                      {opp.categoryWasFixed && (
                        <>
                          <span>·</span>
                          <span className="text-amber-400 font-medium">
                            اصلاح دسته‌بندی از BoE (باگ ۳)
                          </span>
                        </>
                      )}
                      {wasBinaryBugRepaired && (
                        <>
                          <span>·</span>
                          <span className="text-emerald-400 font-medium">
                            اصلاح خروجی باینری به «{p.primaryOutcome}» (باگ ۱)
                          </span>
                        </>
                      )}
                    </div>

                    <h3 className="text-base font-bold text-slate-100 leading-snug" dir="ltr">
                      {opp.title}
                    </h3>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => triggerAiAnalysis(opp)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 text-xs font-medium transition-colors"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>تحلیل هوش مصنوعی</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => onLoadInSimulator(opp)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium transition-colors"
                    >
                      <Calculator className="w-3.5 h-3.5" />
                      <span>شبیه‌ساز کِلی</span>
                    </button>

                    <a
                      href={opp.marketUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`مشاهده ${opp.title} در Polymarket`}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 text-xs transition-colors"
                    >
                      <span className="font-mono">Polymarket</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>

                {/* Quantitative Metrics Strip */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 bg-slate-900/50 border-b border-slate-800/80 divide-y sm:divide-y-0 sm:divide-x sm:divide-x-reverse divide-slate-800 text-xs">
                  <div className="p-3">
                    <div className="text-slate-400">گزینه اصلی (Primary)</div>
                    <div className="mt-1 font-bold text-emerald-400 font-mono truncate" dir="ltr">
                      {p.primaryOutcome}
                    </div>
                  </div>

                  <div className="p-3">
                    <div className="text-slate-400">سایز بهینه (v2 vs قدیم)</div>
                    <div className="mt-1 font-mono tabular-nums flex items-baseline gap-1.5">
                      <span className="font-bold text-slate-100">{p.primarySizePct}%</span>
                      <span className="text-[11px] text-slate-400">(${primaryDollar})</span>
                      {Math.abs(p.primarySizePct - opp.legacyPrimarySizePct) > 1 && (
                        <span className="text-[11px] text-amber-400 line-through">
                          {opp.legacyPrimarySizePct}%
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="p-3">
                    <div className="text-slate-400">قیمت بازار / احتمال مدل</div>
                    <div className="mt-1 font-mono tabular-nums text-slate-200">
                      {(p.primaryMarketPrice * 100).toFixed(1)}¢{' '}
                      <span className="text-slate-500">→</span>{' '}
                      <span className="text-emerald-400 font-semibold">
                        {(p.primaryModelProb * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>

                  <div className="p-3">
                    <div className="text-slate-400">اجماع بیزی (کالیبره)</div>
                    <div className="mt-1 font-mono tabular-nums flex items-baseline gap-1.5">
                      <span className="font-semibold text-slate-100">
                        {p.calibratedConsensusScore}%
                      </span>
                      {opp.legacyConsensusScore === 100 && opp.numSources <= 1 && (
                        <span className="text-[11px] text-amber-400" title="در کد قدیم به دلیل باگ ۱۰، تک‌منبع ۱۰۰٪ می‌گرفت">
                          (قدیم: 100%)
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="p-3">
                    <div className="text-slate-400">سود خالص اگر Primary ببرد</div>
                    <div
                      className={`mt-1 font-mono tabular-nums font-bold ${
                        p.netProfitIfPrimaryWinsPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {p.netProfitIfPrimaryWinsPct >= 0 ? '+' : ''}
                      {p.netProfitIfPrimaryWinsPct.toFixed(2)}%
                    </div>
                  </div>

                  <div className="p-3">
                    <div className="text-slate-400">حد ضرر / حد سود پیشنهادی</div>
                    <div className="mt-1 font-mono tabular-nums text-slate-300">
                      SL: {(p.stopLossPrice * 100).toFixed(1)}¢ · TP:{' '}
                      {(p.takeProfitPrice * 100).toFixed(1)}¢
                    </div>
                  </div>
                </div>

                {/* Warning Banner if Barrier Trap */}
                {p.warning && (
                  <div className="px-4 py-2.5 bg-amber-950/30 border-b border-amber-800/40 flex items-center gap-2 text-xs text-amber-300">
                    <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                    <span>{p.warning}</span>
                  </div>
                )}

                {/* Multi-Leg Allocation & Scenario Payoff Table */}
                <div className="p-4 overflow-x-auto">
                  <table className="w-full text-xs text-right border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-2 px-3 font-medium">نقش پایه (Role)</th>
                        <th className="py-2 px-3 font-medium text-left" dir="ltr">
                          Outcome
                        </th>
                        <th className="py-2 px-3 font-medium">سهم از بودجه</th>
                        <th className="py-2 px-3 font-medium">مبلغ دلاری ($)</th>
                        <th className="py-2 px-3 font-medium">قیمت فعلی</th>
                        <th className="py-2 px-3 font-medium">تعداد سهام (Shares)</th>
                        <th className="py-2 px-3 font-medium">دریافتی ناخالص</th>
                        <th className="py-2 px-3 font-medium">
                          سود/زیان خالص کل سبد در صورت برد این گزینه
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
                      {p.allocations.map((leg, idx) => {
                        const dollarVal = ((bankroll * leg.sizePct) / 100).toFixed(2);
                        const sharesVal = (Number(dollarVal) / leg.marketPrice).toFixed(1);
                        return (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="py-2 px-3 font-sans">
                              {leg.role === 'primary' ? (
                                <span className="text-emerald-400 font-semibold">
                                  گزینه اصلی (Primary)
                                </span>
                              ) : leg.role === 'secondary' ? (
                                <span className="text-sky-400">گزینه دوم (Secondary)</span>
                              ) : (
                                <span className="text-amber-400">پوشش هج (Hedge)</span>
                              )}
                            </td>
                            <td
                              className="py-2 px-3 text-left font-semibold text-slate-200"
                              dir="ltr"
                            >
                              {leg.outcome}
                            </td>
                            <td className="py-2 px-3 text-slate-100">{leg.sizePct.toFixed(2)}%</td>
                            <td className="py-2 px-3 text-slate-300">${dollarVal}</td>
                            <td className="py-2 px-3 text-slate-300">
                              {(leg.marketPrice * 100).toFixed(2)}¢
                            </td>
                            <td className="py-2 px-3 text-slate-300">{sharesVal}</td>
                            <td className="py-2 px-3 text-slate-200">
                              {leg.grossPayoutPct.toFixed(1)}%
                            </td>
                            <td
                              className={`py-2 px-3 font-bold ${
                                leg.netRoiIfWinsPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                              }`}
                            >
                              {leg.netRoiIfWinsPct >= 0 ? '+' : ''}
                              {leg.netRoiIfWinsPct.toFixed(2)}%
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* AI Deep Research Modal */}
      {aiModalOpp && (
        <div
          className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ai-modal-title"
        >
          <div className="bg-[#0F1623] border border-slate-700 max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-4">
            <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <div className="text-xs text-emerald-400 font-medium flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>گزارش تحلیل کوانت و بنیادی هوش مصنوعی (رفع باگ شماره ۸)</span>
                </div>
                <h2
                  id="ai-modal-title"
                  className="mt-1 text-base font-bold text-slate-100"
                  dir="ltr"
                >
                  {aiModalOpp.title}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setAiModalOpp(null)}
                aria-label="بستن پنجره تحلیل"
                className="p-1.5 text-slate-400 hover:text-slate-100 border border-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {aiLoading ? (
              <div className="py-12 text-center space-y-3">
                <div className="inline-block w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-xs text-slate-400">
                  در حال تحلیل تمام گزینه‌های کاندیدا، قیمت‌های CLOB و ساختار هجینگ...
                </p>
              </div>
            ) : aiResult ? (
              <div className="space-y-4 text-xs leading-relaxed">
                <div className="p-3.5 bg-emerald-950/20 border border-emerald-800/40 space-y-1">
                  <div className="font-bold text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>جمع‌بندی اجرایی (Executive Verdict)</span>
                  </div>
                  <p className="text-slate-200">{aiResult.analysis.verdictFa}</p>
                </div>

                <div className="p-3.5 bg-slate-900/70 border border-slate-800 space-y-2">
                  <div className="font-bold text-slate-200 flex items-center gap-1.5">
                    <TrendingUp className="w-4 h-4 text-sky-400" />
                    <span>محرک‌های بنیادی و آماری</span>
                  </div>
                  <ul className="list-disc list-inside space-y-1.5 text-slate-300">
                    {aiResult.analysis.fundamentalDriversFa.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                </div>

                <div className="p-3.5 bg-slate-900/70 border border-slate-800 space-y-1.5">
                  <div className="font-bold text-slate-200 flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-amber-400" />
                    <span>ارزیابی مهندسی هجینگ و تخصیص سرمایه</span>
                  </div>
                  <p className="text-slate-300">{aiResult.analysis.hedgeCritiqueFa}</p>
                </div>

                <div className="p-3.5 bg-slate-900/70 border border-slate-800 space-y-2">
                  <div className="font-bold text-slate-200 flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 text-rose-400" />
                    <span>ریسک‌های دنباله (Tail Risks & Resolution Rules)</span>
                  </div>
                  <ul className="list-disc list-inside space-y-1 text-slate-300">
                    {aiResult.analysis.tailRisksFa.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>

                <div className="p-3.5 bg-sky-950/20 border border-sky-800/40 space-y-1">
                  <div className="font-bold text-sky-400 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4" />
                    <span>توصیه عملیاتی نهایی</span>
                  </div>
                  <p className="text-slate-200">{aiResult.analysis.recommendedActionFa}</p>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
};
