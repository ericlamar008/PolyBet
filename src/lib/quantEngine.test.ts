import test from 'node:test';
import assert from 'node:assert/strict';
import {
  classifyMarketFixed,
  computeBayesianConsensus,
  computeBucketProbabilities,
  buildOptimalPositionPlan,
  parseSecondarySummary,
  auditResolvedDataset,
  RawResolvedRow,
  RawLogRow,
} from './quantEngine';

test('Bug #3 Fix: classifyMarketFixed prevents "bailey" from misclassifying US primaries or NFL as Bank of England (boe)', () => {
  const nhPrimary = classifyMarketFixed(
    'NH-01 Republican Primary Winner',
    'Melissa Bailey, Hollie Noveletsky',
    'boe'
  );
  assert.equal(nhPrimary.category, 'elections');
  assert.equal(nhPrimary.wasFixed, true);

  const nflJets = classifyMarketFixed(
    'Pro Football: Jets Week 1 Starting QB',
    'Bailey Zappe, Tyrod Taylor',
    'boe'
  );
  assert.equal(nflJets.category, 'excluded_sports');
  assert.equal(nflJets.wasFixed, true);

  const realBoe = classifyMarketFixed(
    'Bank of England Decision in September?',
    'MPC interest rate vote Andrew Bailey',
    'boe'
  );
  assert.equal(realBoe.category, 'boe');
  assert.equal(realBoe.wasFixed, false);
});

test('Bug #10 Fix: computeBayesianConsensus shrinks single-source 100% consensus to realistic credibility', () => {
  assert.equal(computeBayesianConsensus(100, 0), 0);
  const singleSource = computeBayesianConsensus(100, 1);
  // 1 / (1 + 1.5) * 100 = 40.0%
  assert.equal(singleSource, 40.0);

  const fourSources = computeBayesianConsensus(100, 4);
  // 4 / (4 + 1.5) * 100 = 72.7%
  assert.ok(fourSources > 70 && fourSources < 80);
});

test('Bug #4 Fix: computeBucketProbabilities integrates Gaussian CDF across range buckets and normalizes to 1.0', () => {
  const buckets = ['<0.0%', '0.0%–0.2%', '0.3%–0.5%', '0.6%–0.8%', '≥0.9%'];
  const dist = computeBucketProbabilities(buckets, 0.4, 0.15);
  const totalProb = Object.values(dist).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(totalProb - 1.0) < 0.01);
  // 0.3%–0.5% contains the mean 0.4%, so it must have the highest probability
  assert.ok(dist['0.3%–0.5%'] > dist['<0.0%']);
  assert.ok(dist['0.3%–0.5%'] > dist['0.6%–0.8%']);
});

test('Bug #6 Fix: buildOptimalPositionPlan guards against longshot barrier option traps and computes exact multi-leg net ROI', () => {
  // Barrier trap test (e.g. Gold ↑ $4,700 at 0.2 cents)
  const trapPlan = buildOptimalPositionPlan({
    title: 'What will Gold (XAUUSD) hit in August 2026?',
    candidates: [
      { name: '↑ $4,700', marketPrice: 0.002 },
      { name: '↓ $4,000', marketPrice: 0.11 },
    ],
    bankrollDollars: 1000,
  });
  assert.equal(trapPlan.isLongshotBarrierTrap, true);
  assert.ok(trapPlan.primarySizePct <= 5.0, 'Should cap barrier trap size instead of 35% floor');

  // Normal multi-candidate market test
  const normalPlan = buildOptimalPositionPlan({
    title: 'Brazil GDP Growth in Q2 2026 (QoQ)?',
    candidates: [
      { name: '0.3%–0.5%', marketPrice: 0.76, modelProb: 0.84 },
      { name: '0.6%–0.8%', marketPrice: 0.14, modelProb: 0.10 },
      { name: '0.0%–0.2%', marketPrice: 0.08, modelProb: 0.05 },
    ],
    bankrollDollars: 1000,
    numSources: 3,
    rawConsensusScore: 92,
  });
  assert.equal(normalPlan.isLongshotBarrierTrap, false);
  assert.equal(normalPlan.primaryOutcome, '0.3%–0.5%');
  assert.ok(normalPlan.primarySizePct >= 79.8);
  assert.ok(normalPlan.netProfitIfPrimaryWinsPct > 0);
});

test('Bug #1 & #2 Fix: auditResolvedDataset repairs binary stock earnings false-negatives and secondary leg saves', () => {
  const resolvedRows: RawResolvedRow[] = [
    {
      group_key: 'https://polymarket.com/event/panw-earnings',
      title: 'Will Palo Alto Networks (PANW) beat quarterly earnings?',
      category: 'stocks',
      logged_at_utc: '2026-09-01T17:23:53Z',
      market_url: 'https://polymarket.com/event/panw-earnings',
      primary_outcome: 'Will Palo Alto Networks (PANW) beat quarterly earnings?',
      primary_size_pct: 99.12,
      primary_market_price: 0.944,
      resolved_outcome: 'Yes',
      is_correct: 'False', // Falsely marked False by legacy weekly_report.py!
      checked_at_utc: '2026-09-02T18:52:56Z',
    },
    {
      group_key: 'https://polymarket.com/event/nh-01-dem',
      title: 'NH-01 Democratic Primary Winner',
      category: 'elections',
      logged_at_utc: '2026-09-05T10:00:00Z',
      market_url: 'https://polymarket.com/event/nh-01-dem',
      primary_outcome: 'Candidate A',
      primary_size_pct: 55.0,
      primary_market_price: 0.52,
      resolved_outcome: 'Candidate B',
      is_correct: 'False',
      checked_at_utc: '2026-09-09T10:00:00Z',
    },
  ];

  const logMap = new Map<string, RawLogRow>();
  logMap.set('https://polymarket.com/event/nh-01-dem', {
    logged_at_utc: '2026-09-05T10:00:00Z',
    group_key: 'https://polymarket.com/event/nh-01-dem',
    title: 'NH-01 Democratic Primary Winner',
    category: 'elections',
    days_to_resolve_at_scan: 3.0,
    consensus_score: 0,
    edge: 0,
    num_sources: 0,
    primary_outcome: 'Candidate A',
    primary_size_pct: 55.0,
    primary_market_price: 0.52,
    hedge_or_secondary_summary: 'secondary:Candidate B=30.0%; hedge:Candidate C=15.0%',
    warning: '',
    market_url: 'https://polymarket.com/event/nh-01-dem',
  });

  const parsedLegs = parseSecondarySummary('secondary:Candidate B=30.0%; hedge:Candidate C=15.0%');
  assert.equal(parsedLegs.length, 2);
  assert.equal(parsedLegs[0].outcome, 'Candidate B');
  assert.equal(parsedLegs[0].sizePct, 30.0);

  const audit = auditResolvedDataset(resolvedRows, logMap);
  assert.equal(audit.summary.legacyWinCount, 0);
  assert.equal(audit.summary.repairedWinCount, 1);
  assert.equal(audit.summary.bug1BinaryFalseNegativesFixed, 1);
  assert.equal(audit.summary.repairedSecondarySaveCount, 1);
  assert.equal(audit.trades[0].repairedPrimaryOutcome, 'Yes');
  assert.equal(audit.trades[0].repairedIsCorrect, true);
  assert.equal(audit.trades[1].wonViaLeg, 'secondary');
});
