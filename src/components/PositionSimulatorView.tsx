import React, { useState, useMemo } from 'react';
import {
  Calculator,
  Plus,
  Trash2,
  ShieldCheck,
  AlertTriangle,
  Sparkles,
} from 'lucide-react';
import {
  buildOptimalPositionPlan,
  OutcomeCandidate,
  computeBucketProbabilities,
} from '../lib/quantEngine';
import { ScannerOpportunity } from './ScannerTerminalView';

interface Props {
  initialOpportunity?: ScannerOpportunity | null;
  defaultBankroll: number;
}

export const PositionSimulatorView: React.FC<Props> = ({
  initialOpportunity,
  defaultBankroll,
}) => {
  const [title, setTitle] = useState<string>(
    initialOpportunity?.title || 'Brazil GDP Growth in Q2 2026 (QoQ)?'
  );
  const [bankroll, setBankroll] = useState<number>(defaultBankroll || 1000);
  const [kellyFraction, setKellyFraction] = useState<number>(0.25);
  const [guaranteedMargin, setGuaranteedMargin] = useState<number>(0.05);
  const [numSources, setNumSources] = useState<number>(
    initialOpportunity?.numSources ?? 3
  );
  const [rawConsensus, setRawConsensus] = useState<number>(
    initialOpportunity?.legacyConsensusScore || 90
  );

  const [candidates, setCandidates] = useState<OutcomeCandidate[]>(() => {
    if (initialOpportunity && initialOpportunity.planV2.allocations.length >= 2) {
      return initialOpportunity.planV2.allocations.map((a) => ({
        name: a.outcome,
        marketPrice: a.marketPrice,
        modelProb: a.modelProb,
      }));
    }
    return [
      { name: '0.3%–0.5%', marketPrice: 0.76, modelProb: 0.82 },
      { name: '0.6%–0.8%', marketPrice: 0.12, modelProb: 0.11 },
      { name: '0.0%–0.2%', marketPrice: 0.08, modelProb: 0.05 },
      { name: '<0.0%', marketPrice: 0.04, modelProb: 0.02 },
    ];
  });

  // Macro Range Bucket Gaussian CDF Generator state (Bug #4 Fix Live Demo)
  const [macroMean, setMacroMean] = useState<number>(0.41);
  const [macroStd, setMacroStd] = useState<number>(0.16);

  const applyPreset = (preset: 'gdp_buckets' | 'panw_binary' | 'unemployment' | 'gold_trap') => {
    if (preset === 'gdp_buckets') {
      setTitle('Brazil GDP Growth in Q2 2026 (QoQ)?');
      setNumSources(3);
      setRawConsensus(92);
      setCandidates([
        { name: '0.3%–0.5%', marketPrice: 0.76, modelProb: 0.82 },
        { name: '0.6%–0.8%', marketPrice: 0.12, modelProb: 0.11 },
        { name: '0.0%–0.2%', marketPrice: 0.08, modelProb: 0.05 },
        { name: '<0.0%', marketPrice: 0.04, modelProb: 0.02 },
      ]);
    } else if (preset === 'panw_binary') {
      setTitle('Will Palo Alto Networks (PANW) beat quarterly earnings?');
      setNumSources(3);
      setRawConsensus(95);
      setCandidates([
        { name: 'Yes', marketPrice: 0.944, modelProb: 0.975 },
        { name: 'No', marketPrice: 0.056, modelProb: 0.025 },
      ]);
    } else if (preset === 'unemployment') {
      setTitle('August Unemployment Rate');
      setNumSources(3);
      setRawConsensus(88);
      setCandidates([
        { name: '4.1%', marketPrice: 0.34, modelProb: 0.44 },
        { name: '4.2%', marketPrice: 0.24, modelProb: 0.25 },
        { name: '4.0%', marketPrice: 0.18, modelProb: 0.16 },
        { name: '4.3%', marketPrice: 0.14, modelProb: 0.10 },
        { name: '≤3.9%', marketPrice: 0.10, modelProb: 0.05 },
      ]);
    } else if (preset === 'gold_trap') {
      setTitle('What will Gold (XAUUSD) hit in August 2026?');
      setNumSources(1);
      setRawConsensus(100);
      setCandidates([
        { name: '↑ $4,700', marketPrice: 0.002, modelProb: 0.005 },
        { name: '↓ $4,000', marketPrice: 0.117, modelProb: 0.12 },
        { name: '↓ $3,900', marketPrice: 0.078, modelProb: 0.08 },
      ]);
    }
  };

  const applyGaussianBucketCdf = () => {
    const labels = candidates.map((c) => c.name);
    const dist = computeBucketProbabilities(labels, macroMean, macroStd);
    setCandidates((prev) =>
      prev.map((c) => ({
        ...c,
        modelProb: dist[c.name] && dist[c.name] > 0 ? dist[c.name] : c.modelProb,
      }))
    );
  };

  const plan = useMemo(() => {
    const validCandidates = candidates.filter((c) => c.name.trim().length > 0 && c.marketPrice > 0);
    if (validCandidates.length === 0) return null;
    return buildOptimalPositionPlan({
      title,
      candidates: validCandidates,
      bankrollDollars: bankroll,
      kellyFraction,
      targetGuaranteedMargin: guaranteedMargin,
      numSources,
      rawConsensusScore: rawConsensus,
    });
  }, [title, candidates, bankroll, kellyFraction, guaranteedMargin, numSources, rawConsensus]);

  const updateCandidate = (
    idx: number,
    field: 'name' | 'marketPrice' | 'modelProb',
    value: string
  ) => {
    setCandidates((prev) =>
      prev.map((item, i) => {
        if (i !== idx) return item;
        if (field === 'name') return { ...item, name: value };
        const num = Math.min(0.999, Math.max(0.001, parseFloat(value) || 0.01));
        return { ...item, [field]: num };
      })
    );
  };

  const addCandidate = () => {
    setCandidates((prev) => [
      ...prev,
      { name: `Option ${prev.length + 1}`, marketPrice: 0.1, modelProb: 0.1 },
    ]);
  };

  const removeCandidate = (idx: number) => {
    if (candidates.length <= 2) return;
    setCandidates((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-6">
      {/* Presets Header */}
      <div className="border border-slate-800 bg-[#0F1623] p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Calculator className="w-4 h-4 text-emerald-400" />
            <span>آزمایشگاه شبیه‌ساز سایزینگ کِلی، هجینگ چندگزینه‌ای و انتگرال باکت‌های کلان</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            تست زنده فرمول‌های اصلاح‌شده position_logic.py و range_bucket.py با محاسبه دقیق بازده خالص هر سناریو
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-400">سناریوهای آماده:</span>
          <button
            type="button"
            onClick={() => applyPreset('gdp_buckets')}
            className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700"
          >
            رشد GDP برزیل (باکت‌های بازه‌ای)
          </button>
          <button
            type="button"
            onClick={() => applyPreset('panw_binary')}
            className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700"
          >
            گزارش درآمدی PANW (باینری)
          </button>
          <button
            type="button"
            onClick={() => applyPreset('unemployment')}
            className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700"
          >
            نرخ بیکاری آمریکا (۵ باکتی)
          </button>
          <button
            type="button"
            onClick={() => applyPreset('gold_trap')}
            className="px-2.5 py-1.5 bg-amber-950/40 hover:bg-amber-900/40 text-amber-300 border border-amber-700/50"
          >
            تله آپشن مانعی طلا (↑ $4,700)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Input Parameters Panel */}
        <div className="lg:col-span-5 border border-slate-800 bg-[#0F1623] p-5 space-y-5">
          <div className="space-y-3">
            <label className="block text-xs text-slate-300">
              عنوان بازار (Market Question)
              <input
                type="text"
                dir="ltr"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 w-full bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs text-slate-100 font-mono"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs text-slate-300">
                سرمایه کل (Bankroll $)
                <input
                  type="number"
                  min={50}
                  step={50}
                  value={bankroll}
                  onChange={(e) => setBankroll(Math.max(10, Number(e.target.value) || 1000))}
                  className="mt-1 w-full bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs font-mono tabular-nums text-slate-100"
                />
              </label>

              <label className="block text-xs text-slate-300">
                حاشیه سود تضمینی پایه (Margin)
                <select
                  value={guaranteedMargin}
                  onChange={(e) => setGuaranteedMargin(Number(e.target.value))}
                  className="mt-1 w-full bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs font-mono text-slate-100"
                >
                  <option value={0.03}>+3.0%</option>
                  <option value={0.05}>+5.0% (پیش‌فرض)</option>
                  <option value={0.08}>+8.0%</option>
                  <option value={0.12}>+12.0%</option>
                </select>
              </label>

              <label className="block text-xs text-slate-300">
                تعداد منابع مستقل (Sources)
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={numSources}
                  onChange={(e) => setNumSources(Math.max(0, Number(e.target.value) || 0))}
                  className="mt-1 w-full bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs font-mono tabular-nums text-slate-100"
                />
              </label>

              <label className="block text-xs text-slate-300">
                اجماع خام اولیه (Raw Consensus %)
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={rawConsensus}
                  onChange={(e) =>
                    setRawConsensus(Math.min(100, Math.max(0, Number(e.target.value) || 0)))
                  }
                  className="mt-1 w-full bg-slate-900 border border-slate-700 px-3 py-1.5 text-xs font-mono tabular-nums text-slate-100"
                />
              </label>
            </div>

            <label className="block text-xs text-slate-300">
              ضریب کِلی کسری (Fractional Kelly: {(kellyFraction * 100).toFixed(0)}%)
              <input
                type="range"
                min={0.1}
                max={1.0}
                step={0.05}
                value={kellyFraction}
                onChange={(e) => setKellyFraction(Number(e.target.value))}
                className="mt-1.5 w-full accent-emerald-500"
              />
            </label>
          </div>

          {/* Gaussian CDF Bucket Integrator (Bug #4 Fix Live Tool) */}
          <div className="p-3.5 bg-slate-900/90 border border-slate-800 space-y-3">
            <div className="text-xs font-bold text-sky-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              <span>تولیدکننده احتمال باکت‌های بازه‌ای با توزیع نرمال (رفع باگ ۴: range_bucket.py)</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-[11px] text-slate-400">
                میانگین پیش‌بینی کلان (Mean %):
                <input
                  type="number"
                  step={0.05}
                  value={macroMean}
                  onChange={(e) => setMacroMean(parseFloat(e.target.value) || 0)}
                  className="mt-1 w-full bg-slate-950 border border-slate-700 px-2 py-1 text-xs font-mono text-slate-100"
                />
              </label>
              <label className="text-[11px] text-slate-400">
                انحراف معیار تاریخی (StdDev %):
                <input
                  type="number"
                  step={0.02}
                  min={0.05}
                  value={macroStd}
                  onChange={(e) => setMacroStd(Math.max(0.05, parseFloat(e.target.value) || 0.1))}
                  className="mt-1 w-full bg-slate-950 border border-slate-700 px-2 py-1 text-xs font-mono text-slate-100"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={applyGaussianBucketCdf}
              className="w-full py-1.5 bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/40 text-xs font-medium"
            >
              محاسبه انتگرال گاوسی (CDF) و اعمال روی احتمالات مدل
            </button>
          </div>

          {/* Candidate Outcomes Editor */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-200">
                گزینه‌های بازار ( قیمت بازار در برابر احتمال مدل )
              </span>
              <button
                type="button"
                onClick={addCandidate}
                className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-emerald-400 border border-slate-700"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>افزودن گزینه</span>
              </button>
            </div>

            <div className="space-y-2">
              {candidates.map((cand, idx) => (
                <div
                  key={idx}
                  className="grid grid-cols-12 gap-2 items-center bg-slate-900/70 p-2 border border-slate-800 text-xs"
                >
                  <div className="col-span-5">
                    <input
                      type="text"
                      dir="ltr"
                      aria-label={`نام گزینه ${idx + 1}`}
                      value={cand.name}
                      onChange={(e) => updateCandidate(idx, 'name', e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 px-2 py-1 font-mono text-slate-100"
                    />
                  </div>
                  <div className="col-span-3">
                    <input
                      type="number"
                      step={0.01}
                      min={0.001}
                      max={0.99}
                      aria-label={`قیمت بازار گزینه ${idx + 1}`}
                      value={cand.marketPrice}
                      onChange={(e) => updateCandidate(idx, 'marketPrice', e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 px-2 py-1 font-mono tabular-nums text-slate-200"
                      title="قیمت بازار (0 تا 1)"
                    />
                  </div>
                  <div className="col-span-3">
                    <input
                      type="number"
                      step={0.01}
                      min={0.001}
                      max={0.99}
                      aria-label={`احتمال مدل گزینه ${idx + 1}`}
                      value={cand.modelProb ?? cand.marketPrice}
                      onChange={(e) => updateCandidate(idx, 'modelProb', e.target.value)}
                      className="w-full bg-slate-950 border border-emerald-800/60 px-2 py-1 font-mono tabular-nums text-emerald-300"
                      title="احتمال مدل (0 تا 1)"
                    />
                  </div>
                  <div className="col-span-1 flex justify-center">
                    <button
                      type="button"
                      onClick={() => removeCandidate(idx)}
                      disabled={candidates.length <= 2}
                      aria-label={`حذف گزینه ${cand.name}`}
                      className="text-slate-500 hover:text-rose-400 disabled:opacity-30"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Simulation Output Panel */}
        <div className="lg:col-span-7 border border-slate-800 bg-[#0F1623] p-5 space-y-5">
          {plan ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border-b border-slate-800 pb-4 font-mono tabular-nums">
                <div className="p-3 bg-slate-900/70 border border-slate-800">
                  <div className="text-[11px] font-sans text-slate-400">سایز بهینه Primary</div>
                  <div className="mt-1 text-xl font-bold text-emerald-400">
                    {plan.primarySizePct}%
                  </div>
                  <div className="text-[11px] text-slate-400">
                    ${((bankroll * plan.primarySizePct) / 100).toFixed(0)} از ${bankroll}
                  </div>
                </div>

                <div className="p-3 bg-slate-900/70 border border-slate-800">
                  <div className="text-[11px] font-sans text-slate-400">اجماع بیزی (کالیبره)</div>
                  <div className="mt-1 text-xl font-bold text-slate-100">
                    {plan.calibratedConsensusScore}%
                  </div>
                  <div className="text-[11px] font-sans text-slate-400">
                    خام: {rawConsensus}% ({numSources} منبع)
                  </div>
                </div>

                <div className="p-3 bg-slate-900/70 border border-slate-800">
                  <div className="text-[11px] font-sans text-slate-400">کِلی کامل / کسری</div>
                  <div className="mt-1 text-xl font-bold text-sky-400">
                    {plan.kellyAppliedPct}%
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Full Kelly: {plan.kellyFullPct}%
                  </div>
                </div>

                <div className="p-3 bg-slate-900/70 border border-slate-800">
                  <div className="text-[11px] font-sans text-slate-400">مجموع قیمت‌ها (Overround)</div>
                  <div
                    className={`mt-1 text-xl font-bold ${
                      plan.dutchBookArbitragePossible ? 'text-emerald-400' : 'text-slate-200'
                    }`}
                  >
                    {(plan.overroundSum * 100).toFixed(1)}%
                  </div>
                  <div className="text-[11px] font-sans text-slate-400">
                    {plan.dutchBookArbitragePossible ? 'آربیتراژ Dutch-Book فعال!' : 'بدون آربیتراژ خالص'}
                  </div>
                </div>
              </div>

              {plan.warning && (
                <div className="p-3.5 bg-amber-950/30 border border-amber-800/50 flex items-start gap-2.5 text-xs text-amber-300">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
                  <span>{plan.warning}</span>
                </div>
              )}

              {/* Scenario Payoff Matrix Table */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>جدول تخصیص بودجه و ماتریس بازده خالص هر سناریو (رفع باگ ۲)</span>
                </h3>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-right border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-2 px-3">نقش پایه</th>
                        <th className="py-2 px-3 text-left" dir="ltr">
                          Outcome
                        </th>
                        <th className="py-2 px-3">درصد بودجه</th>
                        <th className="py-2 px-3">مبلغ ($)</th>
                        <th className="py-2 px-3">قیمت بازار</th>
                        <th className="py-2 px-3">سهام خریداری‌شده</th>
                        <th className="py-2 px-3">دریافتی ناخالص اگر ببرد</th>
                        <th className="py-2 px-3">سود/زیان خالص کل سبد</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
                      {plan.allocations.map((leg, i) => (
                        <tr key={i} className="hover:bg-slate-800/30">
                          <td className="py-2.5 px-3 font-sans">
                            {leg.role === 'primary' ? (
                              <span className="text-emerald-400 font-bold">Primary</span>
                            ) : leg.role === 'secondary' ? (
                              <span className="text-sky-400">Secondary</span>
                            ) : (
                              <span className="text-amber-400">Hedge</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-left font-bold text-slate-100" dir="ltr">
                            {leg.outcome}
                          </td>
                          <td className="py-2.5 px-3 text-slate-100">{leg.sizePct}%</td>
                          <td className="py-2.5 px-3 text-slate-300">${leg.dollarAmount}</td>
                          <td className="py-2.5 px-3 text-slate-300">
                            {(leg.marketPrice * 100).toFixed(1)}¢
                          </td>
                          <td className="py-2.5 px-3 text-slate-300">{leg.sharesBought}</td>
                          <td className="py-2.5 px-3 text-slate-200">
                            ${((bankroll * leg.grossPayoutPct) / 100).toFixed(1)} ({leg.grossPayoutPct}%)
                          </td>
                          <td
                            className={`py-2.5 px-3 font-bold ${
                              leg.netRoiIfWinsPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {leg.netRoiIfWinsPct >= 0 ? '+' : ''}
                            {leg.netRoiIfWinsPct}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {plan.cashReservePct > 0 && (
                <div className="p-3 bg-slate-900 border border-slate-800 text-xs text-slate-300 flex items-center justify-between">
                  <span>ذخیره نقدی خارج از ریسک (Cash Reserve):</span>
                  <span className="font-mono font-bold text-emerald-400">
                    {plan.cashReservePct}% (${((bankroll * plan.cashReservePct) / 100).toFixed(0)})
                  </span>
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};
