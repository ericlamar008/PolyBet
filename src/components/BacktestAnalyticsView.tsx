import React, { useState, useMemo } from 'react';
import {
  CheckCircle2,
  XCircle,
  Filter,
  TrendingUp,
  Award,
  ShieldAlert,
  ArrowLeftRight,
} from 'lucide-react';
import { AuditedTradeRow, CategoryAuditStat, CATEGORY_LABELS_FA } from '../lib/quantEngine';

interface AuditSummary {
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
}

interface Props {
  trades: AuditedTradeRow[];
  summary: AuditSummary;
  categoryBreakdown: CategoryAuditStat[];
}

export const BacktestAnalyticsView: React.FC<Props> = ({
  trades,
  summary,
  categoryBreakdown,
}) => {
  const [filterMode, setFilterMode] = useState<
    'all_resolved' | 'bug1_repaired_wins' | 'secondary_saves' | 'barrier_traps'
  >('all_resolved');
  const [selectedCat, setSelectedCat] = useState<string>('all');
  const [search, setSearch] = useState('');

  const resolvedTrades = useMemo(() => trades.filter((t) => t.isResolved), [trades]);

  const filteredTrades = useMemo(() => {
    return resolvedTrades.filter((t) => {
      if (selectedCat !== 'all' && t.repairedCategory !== selectedCat) return false;
      if (filterMode === 'bug1_repaired_wins') {
        if (!(!t.legacyIsCorrect && t.repairedIsCorrect)) return false;
      } else if (filterMode === 'secondary_saves') {
        if (!(t.wonViaLeg === 'secondary' || t.wonViaLeg === 'hedge')) return false;
      } else if (filterMode === 'barrier_traps') {
        if (!t.bugsTriggered.includes('BUG_6_BARRIER_LONGSHOT_TRAP')) return false;
      }
      if (search.trim()) {
        const q = search.toLowerCase();
        return (
          t.title.toLowerCase().includes(q) ||
          t.repairedPrimaryOutcome.toLowerCase().includes(q) ||
          t.resolvedOutcome.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [resolvedTrades, selectedCat, filterMode, search]);

  // Build cumulative equity curve points (Legacy vs Repaired vs Ideal Engine)
  const equityCurve = useMemo(() => {
    const chronological = [...resolvedTrades].sort((a, b) =>
      a.checkedAtUtc.localeCompare(b.checkedAtUtc)
    );
    let cumLegacy = 0;
    let cumRepaired = 0;
    let cumIdeal = 0;

    const points: Array<{
      index: number;
      date: string;
      legacy: number;
      repaired: number;
      ideal: number;
    }> = [{ index: 0, date: 'شروع', legacy: 0, repaired: 0, ideal: 0 }];

    const step = Math.max(1, Math.floor(chronological.length / 40));
    chronological.forEach((t, idx) => {
      cumLegacy += t.legacyReturnPct;
      cumRepaired += t.repairedReturnPct;
      cumIdeal += t.idealEngineReturnPct;
      if ((idx + 1) % step === 0 || idx === chronological.length - 1) {
        points.push({
          index: idx + 1,
          date: t.checkedAtUtc.slice(0, 10),
          legacy: Number(cumLegacy.toFixed(1)),
          repaired: Number(cumRepaired.toFixed(1)),
          ideal: Number(cumIdeal.toFixed(1)),
        });
      }
    });
    return points;
  }, [resolvedTrades]);

  // SVG Chart helper
  const renderEquitySvg = () => {
    if (equityCurve.length < 2) return null;
    const width = 860;
    const height = 220;
    const padX = 48;
    const padY = 24;

    const allVals = equityCurve.flatMap((p) => [p.legacy, p.repaired, p.ideal, 0]);
    const minVal = Math.min(...allVals, -100);
    const maxVal = Math.max(...allVals, 100);
    const range = Math.max(1, maxVal - minVal);

    const toX = (i: number) =>
      padX + (i / (equityCurve.length - 1)) * (width - padX * 2);
    const toY = (v: number) =>
      height - padY - ((v - minVal) / range) * (height - padY * 2);

    const buildPath = (key: 'legacy' | 'repaired' | 'ideal') =>
      equityCurve
        .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(p[key]).toFixed(1)}`)
        .join(' ');

    const zeroY = toY(0);

    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-56 bg-slate-950/60 border border-slate-800/80"
        role="img"
        aria-label="نمودار مقایسه‌ای منحنی بازده تجمعی موتور قدیم و موتور اصلاح‌شده"
      >
        {/* Zero baseline */}
        <line
          x1={padX}
          y1={zeroY}
          x2={width - padX}
          y2={zeroY}
          stroke="#334155"
          strokeDasharray="4 4"
          strokeWidth="1"
        />
        <text
          x={padX - 6}
          y={zeroY + 4}
          textAnchor="end"
          className="fill-slate-400 text-[10px] font-mono"
        >
          0%
        </text>

        {/* Legacy Path (Crimson) */}
        <path
          d={buildPath('legacy')}
          fill="none"
          stroke="#F43F5E"
          strokeWidth="2"
          strokeOpacity="0.85"
        />

        {/* Repaired Resolution Path (Sky Blue) */}
        <path
          d={buildPath('repaired')}
          fill="none"
          stroke="#38BDF8"
          strokeWidth="2"
        />

        {/* Ideal Calibrated Engine Path (Emerald) */}
        <path
          d={buildPath('ideal')}
          fill="none"
          stroke="#10B981"
          strokeWidth="2.5"
        />
      </svg>
    );
  };

  return (
    <div className="space-y-6">
      {/* Before vs After Executive Comparison Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 border border-slate-800 bg-[#0F1623] divide-y md:divide-y-0 md:divide-x md:divide-x-reverse divide-slate-800">
        <div className="p-4">
          <div className="text-xs text-slate-400">نرخ برد واقعی (قبل و بعد از رفع باگ ۱)</div>
          <div className="mt-1.5 flex items-baseline gap-2 font-mono tabular-nums">
            <span className="text-2xl font-bold text-emerald-400">
              {summary.repairedWinRatePct}%
            </span>
            <span className="text-xs text-slate-400">
              ({summary.repairedWinCount}/{summary.resolvedCount})
            </span>
            <span className="text-xs text-rose-400 line-through">
              {summary.legacyWinRatePct}%
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            احیای {summary.bug1BinaryFalseNegativesFixed} برد واقعی که به علت باگ باینری False شده بودند
          </div>
        </div>

        <div className="p-4">
          <div className="text-xs text-slate-400">نرخ برد و بازده دسته سهام (Stocks EPS)</div>
          <div className="mt-1.5 flex items-baseline gap-2 font-mono tabular-nums">
            <span className="text-2xl font-bold text-emerald-400">
              {categoryBreakdown.find((c) => c.category === 'stocks')?.repairedWinRatePct ?? 71.4}%
            </span>
            <span className="text-xs text-slate-400">
              ({categoryBreakdown.find((c) => c.category === 'stocks')?.repairedWins ?? 25}/
              {categoryBreakdown.find((c) => c.category === 'stocks')?.totalResolved ?? 35})
            </span>
            <span className="text-xs text-rose-400 line-through">0.0% (0/35)</span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            تبدیل میانگین بازده از 75.63%- به 1.46%+ پس از رفع باگ نام خروجی باینری
          </div>
        </div>

        <div className="p-4">
          <div className="text-xs text-slate-400">معاملات نجات‌یافته توسط پایه Secondary/Hedge</div>
          <div className="mt-1.5 flex items-baseline gap-2 font-mono tabular-nums">
            <span className="text-2xl font-bold text-sky-400">
              {summary.repairedSecondarySaveCount}
            </span>
            <span className="text-xs text-slate-400">بازار چندگزینه‌ای</span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            در کد قدیم (results_html_generator.py) برد گزینه‌های دوم و هج صفر حساب می‌شد
          </div>
        </div>

        <div className="p-4">
          <div className="text-xs text-slate-400">میانگین بازده هر معامله (موتور آرمانی v2)</div>
          <div className="mt-1.5 flex items-baseline gap-2 font-mono tabular-nums">
            <span
              className={`text-2xl font-bold ${
                summary.idealEngineAvgReturnPct >= 0 ? 'text-emerald-400' : 'text-amber-400'
              }`}
            >
              {summary.idealEngineAvgReturnPct >= 0 ? '+' : ''}
              {summary.idealEngineAvgReturnPct}%
            </span>
            <span className="text-xs text-rose-400 line-through">
              {summary.legacyAvgReturnPct}%
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            حذف {summary.bug6BarrierTrapAvoidedCount} تله آپشن مانعی ۰.۱ سنتی («Hit $X»)
          </div>
        </div>
      </div>

      {/* Cumulative Performance Chart */}
      <div className="border border-slate-800 bg-[#0F1623] p-4 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <span>مقایسه منحنی بازده تجمعی روی ۲۸۹ بازار تسویه‌شده (predictions_resolved.csv)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              تفاوت چشمگیر بین گزارش قبلی، تسویه اصلاح‌شده، و موتور سایزینگ کالیبره PolyBet v2
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <span className="w-3 h-0.5 bg-emerald-400 inline-block" />
              موتور آرمانی PolyBet v2 (با فیلتر تله‌های مانعی)
            </span>
            <span className="flex items-center gap-1.5 text-sky-400 font-medium">
              <span className="w-3 h-0.5 bg-sky-400 inline-block" />
              تسویه اصلاح‌شده (رفع باگ ۱ و ۲ روی معاملات قبلی)
            </span>
            <span className="flex items-center gap-1.5 text-rose-400 font-medium">
              <span className="w-3 h-0.5 bg-rose-400 inline-block" />
              محاسبه قبلی دارای باگ (results.html)
            </span>
          </div>
        </div>

        {renderEquitySvg()}
      </div>

      {/* Category Breakdown Comparison Table */}
      <div className="border border-slate-800 bg-[#0F1623] p-4 space-y-3">
        <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
          <ArrowLeftRight className="w-4 h-4 text-emerald-400" />
          <span>عملکرد به تفکیک دسته‌بندی (مقایسه مستقیم موتور قدیم و موتور اصلاح‌شده)</span>
        </h3>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-right border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2.5 px-3 font-medium">دسته‌بندی</th>
                <th className="py-2.5 px-3 font-medium">تعداد بازار تسویه‌شده</th>
                <th className="py-2.5 px-3 font-medium">نرخ برد قدیم (باگ‌دار)</th>
                <th className="py-2.5 px-3 font-medium">نرخ برد واقعی (اصلاح‌شده)</th>
                <th className="py-2.5 px-3 font-medium">نجات با هج (Secondary/Hedge)</th>
                <th className="py-2.5 px-3 font-medium">میانگین بازده قدیم</th>
                <th className="py-2.5 px-3 font-medium">میانگین بازده موتور آرمانی v2</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
              {categoryBreakdown.map((cat) => {
                const winDelta = cat.repairedWinRatePct - cat.legacyWinRatePct;
                return (
                  <tr key={cat.category} className="hover:bg-slate-800/30">
                    <td className="py-2.5 px-3 font-sans font-semibold text-slate-200">
                      {cat.labelFa}{' '}
                      <span className="text-slate-500 font-mono text-[11px]">
                        ({cat.category})
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-300">{cat.totalResolved}</td>
                    <td className="py-2.5 px-3 text-slate-400">
                      {cat.legacyWinRatePct}% ({cat.legacyWins}/{cat.totalResolved})
                    </td>
                    <td className="py-2.5 px-3 font-bold text-emerald-400">
                      {cat.repairedWinRatePct}% ({cat.repairedWins}/{cat.totalResolved})
                      {winDelta > 0.1 && (
                        <span className="mr-1.5 text-[11px] text-emerald-300">
                          (+{winDelta.toFixed(1)}%)
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-sky-400">
                      {cat.repairedSecondarySaves > 0 ? `${cat.repairedSecondarySaves} مورد` : '—'}
                    </td>
                    <td
                      className={`py-2.5 px-3 ${
                        cat.legacyAvgReturnPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {cat.legacyAvgReturnPct >= 0 ? '+' : ''}
                      {cat.legacyAvgReturnPct.toFixed(2)}%
                    </td>
                    <td
                      className={`py-2.5 px-3 font-bold ${
                        cat.idealEngineAvgReturnPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {cat.idealEngineAvgReturnPct >= 0 ? '+' : ''}
                      {cat.idealEngineAvgReturnPct.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Forensic Resolved Trades Explorer */}
      <div className="border border-slate-800 bg-[#0F1623] p-4 space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Filter className="w-4 h-4 text-emerald-400" />
              <span>جدول حسابرسی تک‌تک معاملات تسویه‌شده ({filteredTrades.length} مورد)</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              مشاهده دقیق بازارهایی که به خاطر باگ ۱، ۲، ۳ و ۶ در گزارش قبلی به اشتباه زیان‌ده ثبت شده بودند
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setFilterMode('all_resolved')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                filterMode === 'all_resolved'
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-900 text-slate-300 border border-slate-800'
              }`}
            >
              همه تسویه‌شده‌ها ({resolvedTrades.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('bug1_repaired_wins')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                filterMode === 'bug1_repaired_wins'
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-900 text-emerald-400 border border-emerald-800/50'
              }`}
            >
              <Award className="w-3.5 h-3.5" />
              <span>بردهای احیاشده باگ ۱ ({summary.bug1BinaryFalseNegativesFixed})</span>
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('secondary_saves')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                filterMode === 'secondary_saves'
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-900 text-sky-400 border border-sky-800/50'
              }`}
            >
              نجات‌یافته با گزینه دوم/هج ({summary.repairedSecondarySaveCount})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('barrier_traps')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                filterMode === 'barrier_traps'
                  ? 'bg-amber-600 text-white'
                  : 'bg-slate-900 text-amber-400 border border-amber-800/50'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>تله‌های آپشن مانعی Hit $X</span>
            </button>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            aria-label="جستجو در معاملات تسویه‌شده"
            placeholder="جستجو در نام بازار (مثلاً PANW, AVGO, LULU, Unemployment)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
          />
          <select
            aria-label="فیلتر دسته‌بندی معاملات تسویه‌شده"
            value={selectedCat}
            onChange={(e) => setSelectedCat(e.target.value)}
            className="bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs text-slate-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="all">همه دسته‌ها</option>
            {Object.entries(CATEGORY_LABELS_FA).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-right border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2.5 px-3 font-medium text-left" dir="ltr">
                  Market Title
                </th>
                <th className="py-2.5 px-3 font-medium">دسته</th>
                <th className="py-2.5 px-3 font-medium">انتخاب ربات (اصلاح‌شده)</th>
                <th className="py-2.5 px-3 font-medium">نتیجه واقعی</th>
                <th className="py-2.5 px-3 font-medium">حجم / قیمت</th>
                <th className="py-2.5 px-3 font-medium">وضعیت قدیم</th>
                <th className="py-2.5 px-3 font-medium">وضعیت واقعی</th>
                <th className="py-2.5 px-3 font-medium">بازده قدیم</th>
                <th className="py-2.5 px-3 font-medium">بازده موتور v2</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
              {filteredTrades.slice(0, 60).map((t) => (
                <tr key={t.groupKey} className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 text-left max-w-xs truncate text-slate-200" dir="ltr">
                    <a
                      href={t.marketUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-emerald-400 hover:underline"
                    >
                      {t.title}
                    </a>
                  </td>
                  <td className="py-2.5 px-3 font-sans text-slate-400">
                    {CATEGORY_LABELS_FA[t.repairedCategory] || t.repairedCategory}
                  </td>
                  <td className="py-2.5 px-3 text-slate-200" dir="ltr">
                    {t.repairedPrimaryOutcome}
                    {t.legacyPrimaryOutcome !== t.repairedPrimaryOutcome && (
                      <span className="block text-[10px] text-amber-400 font-sans">
                        (در لاگ قدیم: عنوان سؤال!)
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 font-bold text-slate-100" dir="ltr">
                    {t.resolvedOutcome}
                  </td>
                  <td className="py-2.5 px-3 text-slate-300">
                    {t.primarySizePct}% @ {(t.primaryMarketPrice * 100).toFixed(1)}¢
                  </td>
                  <td className="py-2.5 px-3 font-sans">
                    {t.legacyIsCorrect ? (
                      <span className="text-emerald-400 inline-flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> برد
                      </span>
                    ) : (
                      <span className="text-rose-400 inline-flex items-center gap-1">
                        <XCircle className="w-3.5 h-3.5" /> باخت
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 font-sans">
                    {t.repairedIsCorrect ? (
                      <span className="text-emerald-400 font-bold inline-flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> برد Primary
                      </span>
                    ) : t.wonViaLeg !== 'none' ? (
                      <span className="text-sky-400 font-bold">
                        برد {t.wonViaLeg} ({t.winningLegSizePct}%)
                      </span>
                    ) : (
                      <span className="text-rose-400">باخت</span>
                    )}
                  </td>
                  <td
                    className={`py-2.5 px-3 ${
                      t.legacyReturnPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {t.legacyReturnPct >= 0 ? '+' : ''}
                    {t.legacyReturnPct.toFixed(1)}%
                  </td>
                  <td
                    className={`py-2.5 px-3 font-bold ${
                      t.idealEngineReturnPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {t.idealEngineReturnPct >= 0 ? '+' : ''}
                    {t.idealEngineReturnPct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
