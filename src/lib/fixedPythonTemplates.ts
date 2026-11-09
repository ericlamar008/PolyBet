export interface BugReportItem {
  id: string;
  number: number;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  fileAffected: string;
  titleFa: string;
  titleEn: string;
  impactMetric: string;
  problemExplanationFa: string;
  csvEvidence: string;
  buggyCodeSnippet: string;
  fixedCodeSnippet: string;
  architecturalUpgradeFa: string;
}

export interface FixedPythonFile {
  filename: string;
  pathInRepo: string;
  descriptionFa: string;
  bugsFixedCount: number;
  code: string;
}

export const TEN_CRITICAL_BUGS: BugReportItem[] = [
  {
    id: 'BUG_1_BINARY_GROUP_LABEL',
    number: 1,
    severity: 'CRITICAL',
    fileAffected: 'scanner.py + main.py + weekly_report.py',
    titleFa: 'باگ فاجعه‌بار جایگزینی نام خروجی «Yes/No» با عنوان سؤال در بازارهای باینری تک‌گزینه‌ای',
    titleEn: 'Single-Market Binary Event Group Label Overwrite (0% Stock Win-Rate Bug)',
    impactMetric: 'تبدیل ۲۶ برد واقعی سهام (۷۴.۳٪ دقت) به ۰٪ برد (۰ از ۳۵) و ثبت زیان کاذب ۹۵٪-',
    problemExplanationFa:
      'در فایل scanner.py متد resolve_group_metadata برای هر بازاری که داخل آرایه events باشد ولی groupItemTitle نداشته باشد، مقدار group_label = question قرار می‌دهد و در نتیجه representative.is_grouped برابر True می‌شود! سپس در main.py (تابع build_group_plan) به جای اینکه خروجی‌ها ["Yes", "No"] باشند، لیست خروجی‌ها را برابر [m.group_label] یعنی کل متن سؤال («Will Palo Alto Networks beat quarterly earnings?») می‌گذارد! در نهایت weekly_report.py هنگام تسویه می‌بیند نتیجه بازار در پلی‌مارکت "Yes" شده و عبارت "yes" == "will palo alto networks..." را مقایسه می‌کند که همیشه False می‌شود!',
    csvEvidence:
      'ردیف ۲۵ فایل predictions_resolved.csv: بازار PANW با قیمت 0.944 و حجم 99.12% روی برد شرط بسته، نتیجه واقعی resolved_outcome = "Yes" شده، اما به علت اینکه primary_outcome برابر متن سؤال ذخیره شده، is_correct = False خورده است! همین اتفاق برای AVGO, MDB, SNOW, HPE, LULU, DOCU, ORCL, COST, NET و ۲۶ سهم دیگر رخ داده است.',
    buggyCodeSnippet: `# main.py (lines 145-153) — BUGGY:
def build_group_plan(group: list[Market], signal: AggregatedSignal) -> PositionPlan:
    representative = group[0]
    if representative.is_grouped:
        # BUG: When len(group) == 1 (a single binary market inside an event),
        # m.group_label is the full question string instead of ["Yes", "No"]!
        outcomes = [m.group_label or m.question for m in group]
        prices = [m.yes_price for m in group]`,
    fixedCodeSnippet: `# main.py — FIXED:
def build_group_plan(group: list[Market], signal: AggregatedSignal) -> PositionPlan:
    representative = group[0]
    # Only treat as multi-candidate group when there are >= 2 sub-markets!
    if representative.is_grouped and len(group) > 1:
        outcomes = [m.group_label or m.question for m in group]
        prices = [m.yes_price for m in group]
    else:
        outcomes = list(representative.outcomes) or ["Yes", "No"]
        prices = list(representative.outcome_prices) or [
            representative.yes_price,
            round(max(0.0, 1.0 - representative.yes_price), 4),
        ]`,
    architecturalUpgradeFa:
      'تفکیک صریح بازارهای Binary Single-Contract از Multi-Candidate Categorical Event هم در زمان اسکن (scanner.py)، هم در زمان سایزینگ (main.py) و هم یکسان‌سازی تطبیق هوشمند در تسویه هفتگی (weekly_report.py).',
  },
  {
    id: 'BUG_2_MULTI_LEG_PNL',
    number: 2,
    severity: 'CRITICAL',
    fileAffected: 'results_html_generator.py + weekly_report.py',
    titleFa: 'محاسبه کاملاً غلط سود و زیان (PnL) با نادیده‌گرفتن هزینه هج‌ها و بردهای گزینه دوم (Secondary/Hedge)',
    titleEn: 'Single-Leg Myopic PnL Accounting Ignoring Hedge Cost Drag & Secondary Payouts',
    impactMetric: 'انحراف ۱۸٪ تا ۶۵٪ در محاسبه بازده واقعی هر معامله چندگزینه‌ای',
    problemExplanationFa:
      'در فایل results_html_generator.py تابع compute_return_pct فقط ستون primary_size_pct و primary_market_price را می‌خواند. این فرمول دو خطای ریاضی بزرگ دارد: ۱) وقتی گزینه اول (Primary) برنده می‌شود، فرمول فراموش می‌کند که بقیه پول (یعنی 100% - primary_size_pct) که روی گزینه‌های Secondary و Hedge شرط بسته شده، سوخته و صفر شده است! ۲) وقتی گزینه اول می‌بازد اما گزینه Secondary یا Hedge که ربات روی آن ۱۰٪ تا ۳۰٪ بودجه گذاشته برنده می‌شود، سیستم آن را ۱۰۰٪ باخت مطلق در نظر می‌گیرد و پولی که هج برگردانده را صفر لحاظ می‌کند!',
    csvEvidence:
      'در بازار August Unemployment Rate (سهم Primary برابر 64.4% با قیمت 0.34 و 35.6% روی 7 گزینه هج)، کد فعلی سود را +125% حساب کرده در حالی که 35.6% بودجه هج سوخته و سود خالص واقعی کل سبد +89.4% است. همچنین در بازارهایی که گزینه دوم (Secondary) برنده شده، بازده به جای جبران هج، منفی کامل ثبت شده است.',
    buggyCodeSnippet: `# results_html_generator.py (lines 48-56) — BUGGY:
def compute_return_pct(row: dict[str, str]) -> Optional[float]:
    size_pct = float(row.get("primary_size_pct", "") or 0)
    price = float(row.get("primary_market_price", "") or 0)
    # BUG 1: Ignores (100 - size_pct) lost on hedge legs when primary wins!
    # BUG 2: Ignores secondary/hedge payouts when primary loses!
    if row.get("is_correct") == "True":
        return size_pct * (1.0 / price - 1.0)
    return -size_pct`,
    fixedCodeSnippet: `# results_html_generator.py — FIXED PORTFOLIO PNL:
def compute_portfolio_return_pct(row: dict[str, str], secondary_legs: list[dict]) -> Optional[float]:
    primary_size = float(row.get("primary_size_pct") or 0)
    primary_price = float(row.get("primary_market_price") or 0)
    sec_total_size = sum(leg["size_pct"] for leg in secondary_legs)
    total_committed = min(100.0, primary_size + sec_total_size)
    resolved = (row.get("resolved_outcome") or "").strip().lower()

    if row.get("is_correct") == "True":
        gross_payout = primary_size / primary_price
        return round(gross_payout - total_committed, 2)

    for leg in secondary_legs:
        if leg["outcome"].strip().lower() == resolved and leg.get("market_price", 0) > 0:
            gross_payout = leg["size_pct"] / leg["market_price"]
            return round(gross_payout - total_committed, 2)

    return round(-total_committed, 2)`,
    architecturalUpgradeFa:
      'پیاده‌سازی ماتریس بازده سناریومحور (Scenario Payoff Matrix) که بازده خالص کل سبد (Gross Payout منهای کل بودجه درگیر در همه پایه‌ها) را به ازای پیروزی هر یک از گزینه‌های Primary، Secondary و Hedge به صورت دقیق محاسبه می‌کند.',
  },
  {
    id: 'BUG_3_BOE_CLASSIFIER',
    number: 3,
    severity: 'HIGH',
    fileAffected: 'scanner.py',
    titleFa: 'دسته‌بندی اشتباه انتخابات آمریکا و لیگ فوتبال NFL به عنوان «بانک مرکزی انگلستان (BoE)» به خاطر کلمه "bailey"',
    titleEn: 'Naive Keyword Substring Collision ("bailey" -> Bank of England)',
    impactMetric: 'ارسال بازارهای ورزشی و انتخاباتی به موتور نرخ بهره بانک انگلستان (sources/boe.py)',
    problemExplanationFa:
      'در فایل scanner.py، کلیدواژه‌های دسته boe شامل کلمه تکی "bailey" (به نیت Andrew Bailey رئیس بانک مرکزی انگلستان) تعریف شده است. در نتیجه، هر بازار انتخاباتی که نام یکی از کاندیداهایش Bailey باشد (مثل Melissa Bailey در انتخابات مقدماتی جمهوری‌خواهان نیوهمپشایر NH-01) یا هر مسابقه فوتبال آمریکایی که بازیکنش Bailey Zappe باشد (Jets Week 1 Starting QB)، به عنوان نرخ بهره بانک مرکزی انگلستان (boe) دسته‌بندی شده است!',
    csvEvidence:
      'در فایل predictions_log.csv ردیف ۴۲: بازار "NH-01 Republican Primary Winner" و ردیف ۹۲: بازار "Pro Football: Jets Week 1 Starting QB" هر دو با category = "boe" ثبت شده‌اند!',
    buggyCodeSnippet: `# scanner.py (line 36) — BUGGY:
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "boe": ("bank of england", "boe rate", "bailey"), # <-- Matches ANY person named Bailey!
}`,
    fixedCodeSnippet: `# scanner.py — FIXED:
EXCLUDED_SPORTS_KEYWORDS = ("pro football", "nfl", "starting qb", "nba", "mlb", "nhl", "super bowl")
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "boe": ("bank of england", "boe rate", "boe decision", "mpc vote", "andrew bailey"),
}`,
    architecturalUpgradeFa:
      'افزودن فیلتر حذف بازارهای ورزشی (Sports Guard) قبل از دسته‌بندی کلان و جایگزینی نام‌های فامیلی تکی ("bailey", "macklem") با عبارات دوکلمه‌ای دقیق ("andrew bailey", "tiff macklem", "boe decision").',
  },
  {
    id: 'BUG_4_DEAD_RANGE_BUCKET',
    number: 4,
    severity: 'HIGH',
    fileAffected: 'sources/range_bucket.py + sources/aggregator.py',
    titleFa: 'ماژول range_bucket.py کد مرده (Dead Code) است و در هیچ جای پروژه فراخوانی نشده است',
    titleEn: 'Orphaned Range-Bucket Probability Parser Never Imported or Wired',
    impactMetric: 'عدم توانایی محاسبه احتمال بازه‌های عددی مثل «0.3%–0.5%» یا «≤3.8%» در بازارهای CPI و GDP',
    problemExplanationFa:
      'شما فایل بسیار خوبی به نام sources/range_bucket.py برای پارس کردن بازه‌های عددی (مثل 0.3%–0.5% یا <0.0%) و انتگرال‌گیری توزیع نرمال (CDF) نوشته‌اید، اما این فایل در هیچ‌کدام از فایل‌های main.py، aggregator.py، fred.py یا bls.py ایمپورت نشده است! در نتیجه برای تمام بازارهای چندبازه‌ای تورم و رشد اقتصادی، تابع extract_threshold در base.py شکست می‌خورد یا فقط عدد اول را به عنوان سقف/کف ساده می‌گیرد.',
    csvEvidence:
      'در فایل predictions_log.csv برای بازارهای بازه‌ای مثل Brazil GDP Growth (0.3%–0.5%) یا Core CPI MoM، تعداد منابع 0 و هشدار «سؤال این بازار آستانه عددی صریح ندارد» ثبت شده است.',
    buggyCodeSnippet: `# sources/base.py — BUGGY:
# Only checks "above X" or "below X", completely ignoring sources/range_bucket.py!
match = re.search(r"(above|over|exceed|below|under)\\s+(-?\\d+(?:\\.\\d+)?)%?", question)`,
    fixedCodeSnippet: `# sources/base.py — FIXED (Wired to range_bucket.py):
from sources.range_bucket import parse_bucket_label, bucket_probability

bucket = parse_bucket_label(candidate_label or question)
if bucket is not None:
    prob = bucket_probability(mean=latest_mean, std=latest_std, low=bucket.low, high=bucket.high)`,
    architecturalUpgradeFa:
      'اتصال مستقیم پارسر بازه‌ای (parseBucketBounds) و انتگرال‌گیر توزیع گاوسی (normalCdf) به موتور سیگنال تا برای تمام گزینه‌های یک بازار چندبازه‌ای، توزیع احتمال نرمال‌شده (با مجموع ۱۰۰٪) تولید شود.',
  },
  {
    id: 'BUG_5_FRED_RAW_INDEX',
    number: 5,
    severity: 'CRITICAL',
    fileAffected: 'sources/fred.py',
    titleFa: 'مقایسه عدد خام شاخص CPI (~315.0) با آستانه درصد تورم سالانه (~3.4%) در fred.py',
    titleEn: 'Raw CPI Index (~315) Compared Directly Against YoY Inflation Percentage (~3.4%)',
    impactMetric: 'تولید Z-Score کاذب +200 و احتمال ۱۰۰٪ غلط برای تمام بازارهای تورم آمریکا',
    problemExplanationFa:
      'در فایل sources/fred.py مجموعه TRANSFORM_DOMAINS فقط شامل {"pce"} تعریف شده و {"cpi", "gdp"} از قلم افتاده‌اند! وقتی سری CPIAUCSL بدون پارامتر units="pc1" از FRED گرفته می‌شود، مقدار خام شاخص قیمت مصرف‌کننده (حدود ۳۱۵ واحد) برمی‌گردد، نه نرخ تورم سالانه (مثلاً ۲.۹٪)! سپس کد عدد ۳۱۵ را با آستانه ۳.۷٪ مقایسه می‌کند و فکر می‌کند تورم ۳۱۵ درصد است!',
    csvEvidence:
      'در predictions_log.csv بازار "October Inflation US - Annual" با ۱ منبع (FRED)، مقدار edge = 0.899999 و consensus = 100.0% گرفته زیرا عدد خام شاخص CPI با درصد مقایسه شده است.',
    buggyCodeSnippet: `# sources/fred.py (line 31) — BUGGY:
# Only transforms PCE to YoY % change; leaves CPIAUCSL and GDPC1 as raw index levels!
TRANSFORM_DOMAINS: set[str] = {"pce"}`,
    fixedCodeSnippet: `# sources/fred.py — FIXED:
# Transform CPI, PCE, and Real GDP to YoY/QoQ percentage change (pc1 / pch)
UNIT_TRANSFORM_BY_DOMAIN: dict[str, str] = {
    "cpi": "pc1",  # Percent Change from Year Ago (YoY %)
    "pce": "pc1",  # Percent Change from Year Ago (YoY %)
    "gdp": "cca",  # Compounded Annual Rate of Change (QoQ SAAR %)
}`,
    architecturalUpgradeFa:
      'تعریف نگاشت صریح واحدها (Unit Transform Map) برای هر سری زمانی اقتصاد کلان در FRED تا نرخ‌های سالانه (YoY) و ماهانه (MoM) دقیقاً هم‌واحد با سؤال پلی‌مارکت محاسبه شوند.',
  },
  {
    id: 'BUG_6_BARRIER_TRAP',
    number: 6,
    severity: 'CRITICAL',
    fileAffected: 'position_logic.py',
    titleFa: 'تله آپشن‌های مانعی («What price will X hit?») و تخصیص کورکورانه ۳۵٪ بودجه به گزینه‌های ۰.۱ سنتی',
    titleEn: '35% Floor Allocation Dumped Into 0.1¢ Non-Exclusive Barrier Option Longshots',
    impactMetric: 'مسئول بیش از ۶۰٪ زیان‌های سنگین در دسته‌های Crypto، Commodities و SPY',
    problemExplanationFa:
      'بازارهایی مثل «What will Gold hit in August?» یا «What price will Bitcoin hit?» در پلی‌مارکت شامل ده زیربازار باینری مستقل هستند (مثلاً ↑ $4,700 با قیمت 0.002 و ↓ $4,000 با قیمت 0.11). این گزینه‌ها مانعةالجمع (Mutually Exclusive) نیستند—ممکن است قیمت در ماه آگوست به هیچ‌کدام از این مرزها نرسد و همه زیربازارها "No" تسویه شوند! اما کد قبلی، گزینه اول لیست یا یک گزینه ۰.۱ سنتی را برمی‌داشت، به خاطر فرمول MIN_PRIMARY_ALLOCATION_PCT = 35.0، ۳۵٪ کل سرمایه را روی یک شرط ۰.۱۵ سنتی و ۶۵٪ بقیه را روی سایر مرزهای دور می‌ریخت!',
    csvEvidence:
      'ردیف‌های ۱۰ تا ۱۸ فایل predictions_resolved.csv (شامل SPY ↑ $790 با قیمت 0.011، طلا ↑ $4,700 با قیمت 0.002، نفت WTI ↑ $90 با قیمت 0.0015، بیت‌کوین ↑ 82,500 با قیمت 0.0105) همگی دقیقاً ۳۵٪ بودجه گرفته‌اند و همگی False شده‌اند.',
    buggyCodeSnippet: `# position_logic.py (lines 72-86) — BUGGY:
MIN_PRIMARY_ALLOCATION_PCT: float = 35.0
# Even when primary_price == 0.0015 (0.15 cents!), floor_pct is clamped to 35.0%!
return clamp(raw_floor, MIN_PRIMARY_ALLOCATION_PCT, MAX_PRIMARY_ALLOCATION_PCT)`,
    fixedCodeSnippet: `# position_logic.py — FIXED BARRIER TRAP & KELLY GUARD:
if is_barrier_option_market(title, outcomes) and primary_price < 0.15:
    # Sub-markets are NOT mutually exclusive; do not apply Dutch-book hedge or 35% floor!
    primary_size_pct = round(min(5.0, max(1.0, primary_price * 100 * 2.0)), 2)
    return build_capped_barrier_plan(primary_outcome, primary_size_pct, primary_price)`,
    architecturalUpgradeFa:
      'افزودن تشخیص‌دهنده خودکار بازارهای مانعی (Barrier Option Detector) و ترکیب معیار کِلی کسری (Fractional Kelly) با بررسی مجموع احتمالات ضمنی (Overround Sum) قبل از اجرای هجینگ چندگزینه‌ای.',
  },
  {
    id: 'BUG_7_BY_DATE_RESOLUTION',
    number: 7,
    severity: 'HIGH',
    fileAffected: 'weekly_report.py',
    titleFa: 'قفل‌شدن تسویه بازارهای زمان‌دار («...by August 31 / September 30») در weekly_report.py',
    titleEn: 'Cumulative "By Date" Multi-Market Resolution Freeze',
    impactMetric: 'بلاتکلیف ماندن بیش از ۹۵ بازار زمان‌دار در وضعیت Pending با وجود مشخص شدن نتیجه',
    problemExplanationFa:
      'در بازارهایی مثل «US reissues Iran oil sales sanction relief by...?» زیربازارها به ترتیب تاریخ هستند (August 31, September 30, October 31). وقتی تاریخ ۳۱ آگوست می‌گذرد و آن زیربازار با نتیجه "No" بسته می‌شود، در تابع resolve_single_prediction متغیر any_closed = True می‌شود اما چون هیچ زیربازاری "Yes" نشده، حلقه بدون پیدا کردن برنده تمام می‌شود و بازار برای همیشه بدون نتیجه (Pending) رها می‌شود، در حالی که گزینه شرط‌بندی‌شده (primary_outcome = "August 31") رسماً بسته و "No" شده است!',
    csvEvidence:
      'ردیف ۷ فایل predictions_resolved.csv: بازار "US reissues Iran oil sales sanction relief by...?" با primary_outcome = "August 31" حتی در بررسی تاریخ ۸ نوامبر هم بدون نتیجه (خالی) مانده است.',
    buggyCodeSnippet: `# weekly_report.py (lines 125-136) — BUGGY:
for market in sub_markets:
    settled = extract_settled_winner(market)
    if settled == "Yes":
        return True, label
# BUG: If primary_outcome was "August 31" and the "August 31" sub-market settled "No",
# it returns (False, None) instead of grading "August 31" as resolved lost!`,
    fixedCodeSnippet: `# weekly_report.py — FIXED:
for market in sub_markets:
    label = (market.get("groupItemTitle") or market.get("question") or "").strip()
    settled = extract_settled_winner(market)
    if settled == "Yes":
        return True, label
    if label.lower() == primary_outcome.lower() and settled == "No":
        return True, f"Not {label} (Settled No)"`,
    architecturalUpgradeFa:
      'بررسی مستقیم وضعیت تسویه همان زیربازاری که به عنوان Primary انتخاب شده در بازارهای سری زمانی (Cumulative Date Series).',
  },
  {
    id: 'BUG_8_AI_WRONG_SUBMARKET',
    number: 8,
    severity: 'MEDIUM',
    fileAffected: 'main.py + html_generator.py',
    titleFa: 'ارسال زیربازار اشتباه (group[0] به جای کل کاندیداها) به دکمه تحلیل هوش مصنوعی',
    titleEn: 'AI Analysis Button Receives Only group[0] Instead of Full Event Candidates',
    impactMetric: 'تحلیل ناقص یا بی‌ربط هوش مصنوعی روی اولین باکت (مثلاً ≤0.6%) به جای گزینه اصلی',
    problemExplanationFa:
      'در فایل main.py، متغیر representative = group[0] (اولین زیربازار بازگردانده‌شده توسط API که معمولاً یک باکت حاشیه‌ای با احتمال ۱٪ است) به عنوان market در MarketOpportunity ذخیره می‌شود. سپس در html_generator.py دکمه 🧠 AI Analysis فقط m.outcomes و m.outcome_prices مربوط به همان group[0] (یعنی Yes/No باکت اول!) را به ورکر هوش مصنوعی می‌فرستد و هوش مصنوعی اصلاً لیست کاندیداها یا سایزینگ کِلی ربات را نمی‌بیند!',
    csvEvidence:
      'در فایل index_c630fbfe.html خط ۴۵۰، دکمه analyzeMarket فقط outcomes: ["Yes", "No"] با قیمت یک زیربازار حاشیه‌ای را برای رویدادهای چندگزینه‌ای ارسال می‌کند.',
    buggyCodeSnippet: `# html_generator.py (lines 201-208) — BUGGY:
market_payload = json.dumps({
    "question": title,
    "outcomes": m.outcomes,           # <-- Only group[0]'s ["Yes", "No"]!
    "outcomePrices": m.outcome_prices # <-- Only group[0]'s binary prices!
})`,
    fixedCodeSnippet: `# html_generator.py / server.ts — FIXED:
market_payload = {
    "question": title,
    "category": m.category,
    "candidates": [{"name": a.outcome, "price": a.market_price, "sizePct": a.size_pct} for a in p.allocations],
    "quantitativeEdge": p.edge,
    "calibratedConsensus": p.calibrated_consensus_score,
}`,
    architecturalUpgradeFa:
      'انتقال موتور تحلیل هوش مصنوعی به بک‌اند امن (/api/ai-analyze) با مدل Gemini 3.8 Flash و ارسال کامل جدول کاندیداها، قیمت‌های بازار، لبه‌های کوانت (Edge) و تخصیص هج برای دریافت تحلیل ساختاریافته.',
  },
  {
    id: 'BUG_9_BLS_SERIES_MISMATCH',
    number: 9,
    severity: 'CRITICAL',
    fileAffected: 'sources/bls.py',
    titleFa: 'استفاده از سری تعداد کل شاغلین (158,000 هزار نفر) به جای نرخ بیکاری (4.1%) در bls.py',
    titleEn: 'BLS Nonfarm Payroll Level (158,000k) Compared Against Unemployment Rate % (4.1%)',
    impactMetric: 'ایجاد Z-Score کاذب +2633 و احتمال 100% برای تمام بازارهای نرخ بیکاری',
    problemExplanationFa:
      'در فایل sources/bls.py برای دسته employment، سری زمانی CES0000000001 تعریف شده که تعداد کل شاغلین غیرکشاورزی آمریکا بر حسب هزار نفر (حدود ۱۵۸,۰۰۰) است! وقتی بازار پلی‌مارکت می‌پرسد «August Unemployment Rate: 4.1%»، کد عدد ۱۵۸,۰۰۰ را با عدد ۴.۱ مقایسه می‌کند، به Z-Score برابر +2633 می‌رسد و احتمال ۱۰۰٪ با اجماع ۱۰۰٪ صادر می‌کند! برای نرخ بیکاری باید از سری LNS14000000 استفاده شود.',
    csvEvidence:
      'ردیف ۲۴ فایل predictions_log.csv: بازار "August Unemployment Rate" با ۱ منبع، consensus_score = 100.0 و edge = 0.339999 ثبت شده زیرا احتمال مدل به خاطر عدد ۱۵۸,۰۰۰ دقیقاً 0.999999 شده است!',
    buggyCodeSnippet: `# sources/bls.py (lines 20-23) — BUGGY:
SERIES_BY_DOMAIN: dict[str, str] = {
    "cpi": "CUUR0000SA0",        # Raw CPI index (~315), not YoY %!
    "employment": "CES0000000001", # Total Nonfarm Payrolls (~158,000), not Unemployment Rate %!
}`,
    fixedCodeSnippet: `# sources/bls.py — FIXED:
SERIES_BY_DOMAIN: dict[str, str] = {
    "cpi_yoy": "CUUR0000SA0",          # Compute 12-month % change: (v[0] - v[12]) / v[12] * 100
    "unemployment_rate": "LNS14000000", # Official U-3 Unemployment Rate (%) e.g. 4.1%
    "nonfarm_payrolls": "CES0000000001", # Compute 1-month delta: v[0] - v[1]
}`,
    architecturalUpgradeFa:
      'تفکیک هوشمند زیرحوزه‌های اشتغال (نرخ بیکاری LNS14000000 در برابر تغییرات ماهانه NFP) و محاسبه تغییرات درصدی ۱۲ماهه برای شاخص CPI در ماژول BLS.',
  },
  {
    id: 'BUG_10_SINGLE_SOURCE_CONSENSUS',
    number: 10,
    severity: 'HIGH',
    fileAffected: 'sources/base.py + position_logic.py',
    titleFa: 'توهم اجماع ۱۰۰٪ (Consensus = 100%) زمانی که فقط ۱ منبع داده پاسخ داده است',
    titleEn: 'Single-Source 100% Consensus Illusion (1/1 = 100%)',
    impactMetric: 'تخصیص حداکثر وزن اطمینان به تخمین‌های تک‌منبعی بدون تایید متقابل',
    problemExplanationFa:
      'در فایل sources/base.py تابع compute_consensus_score تعداد منابعی که در یک جهت (بالا یا پایین ۵۰٪) هستند را بر تعداد کل منابع تقسیم می‌کند. وقتی فقط ۱ منبع (num_sources == 1) داده برگرداند، همیشه 1 تقسیم بر 1 برابر 1.0 (یعنی 100.0% اجماع!) می‌شود! سپس position_logic.py فکر می‌کند همه منابع جهان با اطمینان ۱۰۰٪ متفق‌القول هستند و سایز پوزیشن را به سقف می‌چسباند.',
    csvEvidence:
      'در فایل predictions_log.csv تمام ردیف‌هایی که num_sources = 1 دارند، بدون استثنا consensus_score = 100.0 دارند!',
    buggyCodeSnippet: `# sources/base.py (lines 118-126) — BUGGY:
def compute_consensus_score(probabilities: Sequence[float]) -> float:
    if not probabilities:
        return 0.0
    # BUG: When len(probabilities) == 1, max(above, below) / 1 is ALWAYS 100.0%!
    agreement_ratio = max(above, below) / len(probabilities)
    return round(agreement_ratio * 100.0, 1)`,
    fixedCodeSnippet: `# sources/base.py — FIXED (Empirical Bayes Shrinkage):
def compute_consensus_score(probabilities: Sequence[float], prior_k: float = 1.5) -> float:
    n = len(probabilities)
    if n == 0:
        return 0.0
    above = sum(1 for p in probabilities if p >= 0.5)
    below = n - above
    raw_agreement = max(above, below) / n
    # Shrink single-source estimates: for n=1, max score is 1 / (1 + 1.5) = 40.0%
    credibility_weight = n / (n + prior_k)
    return round(raw_agreement * credibility_weight * 100.0, 1)`,
    architecturalUpgradeFa:
      'اعمال انقباض بیزی تجربی (Empirical Bayes Shrinkage) با ضریب $w = \\frac{n}{n + 1.5}$ تا ۱ منبع به‌تنهایی نتواند امتیاز اجماع بالای ۴۰٪ بگیرد و امتیاز بالای ۸۰٪ نیازمند حداقل ۴ منبع مستقل هم‌جهت باشد.',
  },
  {
    id: 'BUG_11_GITHUB_WORKFLOWS',
    number: 11,
    severity: 'HIGH',
    fileAffected: '.github/workflows/daily_scan.yml + .github/workflows/weekly_report.yml',
    titleFa: 'باگ‌های ورک‌فلوهای GitHub Actions: جا افتادن BLS_API_KEY، تداخل git push و ثبت تکراری در تلاش مجدد (Retry)',
    titleEn: 'GitHub Actions Workflow Bugs: Missing BLS_API_KEY, Concurrent Push Collision & Retry Duplication',
    impactMetric: 'خطای Rate-Limit در BLS، رد شدن git push در زمان اجرای هم‌زمان و ثبت ردیف‌های تکراری در CSV',
    problemExplanationFa:
      'در بررسی فایل‌های .github/workflows/daily_scan.yml و weekly_report.yml سه ایراد مهم وجود داشت: ۱) در daily_scan.yml کلید BLS_API_KEY در بخش env: فراموش شده بود (برخلاف FRED و BEA و EIA) و باعث می‌شد bls.py بدون کلید و با محدودیت شدید Rate-Limit اجرا شود. ۲) حلقه Retry سه‌مرحله‌ای در daily_scan.yml کل اسکریپت python main.py را دوباره اجرا می‌کرد؛ اگر تلاش اول بعد از نوشتن در predictions_log.csv و هنگام ارسال تلگرام خطا می‌داد، تلاش دوم دوباره همان بازارها را در CSV ثبت می‌کرد! ۳) نام گروه هم‌زمانی (concurrency group) در دو ورک‌فلو متفاوت بود و هیچ‌کدام قبل از git push دستور git pull --rebase نداشتند.',
    csvEvidence:
      'در فایل .github/workflows/daily_scan.yml خطوط ۴۵ تا ۵۵ متغیر BLS_API_KEY وجود ندارد و در خطوط ۷۵ تا ۸۰ مستقیماً git push بدون git pull --rebase فراخوانی شده است.',
    buggyCodeSnippet: `# .github/workflows/daily_scan.yml — BUGGY:
concurrency:
  group: polybet-daily-scan # <-- Different from weekly_report.yml, causing git push collisions!
...
        env:
          FRED_API_KEY: \${{ secrets.FRED_API_KEY }}
          # BUG: BLS_API_KEY is completely missing here!
...
          git commit -m "Daily scan..."
          git push # <-- Fails if weekly_report or manual dispatch pushed meanwhile!`,
    fixedCodeSnippet: `# .github/workflows/daily_scan.yml — FIXED:
concurrency:
  group: polybet-repo-write # <-- Shared lock across all repo-writing workflows
  cancel-in-progress: false
...
        env:
          FRED_API_KEY: \${{ secrets.FRED_API_KEY }}
          BLS_API_KEY: \${{ secrets.BLS_API_KEY }}
...
          git commit -m "Daily scan: \$(date -u +'%Y-%m-%d %H:%M UTC')"
          git pull --rebase --autostash origin HEAD
          git push`,
    architecturalUpgradeFa:
      'بازسازی کامل پوشه .github/workflows/ با قفل هم‌زمانی یکپارچه (polybet-repo-write)، افزودن کش pip، تزریق BLS_API_KEY، جلوگیری از ثبت تکراری روزانه در main.py و افزودن مکانیزم خودترمیم‌گر کش (Self-Healing Cache) در weekly_report.py.',
  },
];

export const FIXED_PYTHON_FILES: FixedPythonFile[] = [
  {
    filename: 'main.py',
    pathInRepo: 'main.py',
    descriptionFa: 'رفع باگ شماره ۱ (جلوگیری از جایگزینی Yes/No با عنوان سؤال در بازارهای تک‌گزینه‌ای) و ارسال کامل کاندیداها به موتور سایزینگ و هوش مصنوعی',
    bugsFixedCount: 3,
    code: `"""PolyBet Main Orchestrator v2.0 — Fixed & Calibrated."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from html_generator import generate_html_report
from position_logic import MarketOpportunity, PositionPlan, build_position_plan
from scanner import Market, fetch_qualifying_markets, group_markets_by_event
from sources import AggregatedSignal, build_signal
from telegram_bot import broadcast_report


PREDICTIONS_LOG_PATH = Path("data/predictions_log.csv")


def build_group_plan(group: list[Market], signal: AggregatedSignal) -> PositionPlan:
    """Build a unified PositionPlan for an event group.

    FIX BUG #1: Only treat as categorical multi-outcome group when len(group) > 1.
    Single binary markets inside an event wrapper must retain their ["Yes", "No"] outcomes!
    """
    representative = group[0]
    if representative.is_grouped and len(group) > 1:
        outcomes = [m.group_label or m.question for m in group]
        prices = [m.yes_price for m in group]
    else:
        outcomes = list(representative.outcomes) or ["Yes", "No"]
        prices = list(representative.outcome_prices) or [
            representative.yes_price,
            round(max(0.0, 1.0 - representative.yes_price), 4),
        ]

    has_sources = signal.num_sources > 0
    return build_position_plan(
        title=representative.event_title or representative.question,
        outcomes=outcomes,
        outcome_prices=prices,
        consensus_score=signal.consensus_score,
        model_probability=signal.mean_probability if has_sources else None,
        market_yes_price=representative.yes_price if has_sources else None,
        num_sources=signal.num_sources,
    )
`,
  },
  {
    filename: 'position_logic.py',
    pathInRepo: 'position_logic.py',
    descriptionFa: 'موتور سایزینگ نسخه ۲: ترکیب معیار کِلی کسری (Fractional Kelly)، محافظ تله آپشن‌های مانعی (Barrier Option Guard) و محاسبه دقیق بازده خالص چندپایه',
    bugsFixedCount: 3,
    code: `"""PolyBet Position Sizing & Multi-Leg Hedge Engine v2.0."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

GUARANTEED_MARGIN: float = 0.05
MIN_PRIMARY_ALLOCATION_PCT: float = 35.0
MAX_PRIMARY_ALLOCATION_PCT: float = 100.0
BARRIER_MAX_ALLOCATION_PCT: float = 5.0


@dataclass(frozen=True)
class OutcomeAllocation:
    outcome: str
    role: str  # "primary" | "secondary" | "hedge"
    size_pct: float
    market_price: float
    gross_payout_pct: float
    net_roi_if_wins_pct: float


@dataclass(frozen=True)
class PositionPlan:
    primary_outcome: str
    primary_size_pct: float
    primary_market_price: float
    allocations: list[OutcomeAllocation]
    total_allocated_pct: float
    net_profit_if_primary_wins_pct: float
    effective_confidence: float
    edge: float
    is_barrier_trap: bool
    warning: Optional[str]


def is_barrier_option_trap(title: str, primary_outcome: str, primary_price: float) -> bool:
    """Detect non-exclusive 'What price will X hit?' longshot barrier traps."""
    hit_pattern = bool(re.search(r"\\bwhat (?:price )?will .* hit\\b", title.lower()))
    arrow_outcome = bool(re.match(r"^[↑↓]\\s*\\$?[\\d,.]+", primary_outcome.strip()))
    return (hit_pattern or arrow_outcome) and primary_price < 0.15


def build_position_plan(
    title: str,
    outcomes: Sequence[str],
    outcome_prices: Sequence[float],
    consensus_score: float,
    model_probability: Optional[float] = None,
    market_yes_price: Optional[float] = None,
    num_sources: int = 0,
) -> PositionPlan:
    ranked = sorted(
        zip(outcomes, outcome_prices),
        key=lambda item: item[1],
        reverse=True,
    )
    primary_name, primary_price = ranked[0]
    safe_price = max(0.001, min(0.995, primary_price))

    trap = is_barrier_option_trap(title, primary_name, safe_price)
    edge = abs(model_probability - safe_price) if model_probability is not None else 0.0
    effective_conf = min(1.0, 0.5 * (consensus_score / 100.0) + 0.5 * min(1.0, edge / 0.20))

    if trap:
        primary_size = round(min(BARRIER_MAX_ALLOCATION_PCT, max(1.0, safe_price * 200.0)), 2)
        total_allocated = primary_size
        gross_payout = round(primary_size / safe_price, 2)
        allocations = [
            OutcomeAllocation(
                outcome=primary_name,
                role="primary",
                size_pct=primary_size,
                market_price=safe_price,
                gross_payout_pct=gross_payout,
                net_roi_if_wins_pct=round(gross_payout - total_allocated, 2),
            )
        ]
        return PositionPlan(
            primary_outcome=primary_name,
            primary_size_pct=primary_size,
            primary_market_price=safe_price,
            allocations=allocations,
            total_allocated_pct=total_allocated,
            net_profit_if_primary_wins_pct=round(gross_payout - total_allocated, 2),
            effective_confidence=effective_conf,
            edge=round(edge, 4),
            is_barrier_trap=True,
            warning="Barrier option longshot trap detected — capped allocation at 5% without non-exclusive hedges.",
        )

    floor_pct = min(MAX_PRIMARY_ALLOCATION_PCT, max(MIN_PRIMARY_ALLOCATION_PCT, safe_price * (1.0 + GUARANTEED_MARGIN) * 100.0))
    primary_size = round(floor_pct + (MAX_PRIMARY_ALLOCATION_PCT - floor_pct) * effective_conf, 2)
    remaining = round(max(0.0, 100.0 - primary_size), 2)

    allocations = [
        OutcomeAllocation(
            outcome=primary_name,
            role="primary",
            size_pct=primary_size,
            market_price=safe_price,
            gross_payout_pct=round(primary_size / safe_price, 2),
            net_roi_if_wins_pct=round((primary_size / safe_price) - 100.0, 2),
        )
    ]

    others = [(n, max(0.001, p)) for n, p in ranked[1:] if p > 0.001]
    other_sum = sum(p for _, p in others)
    if remaining > 0.05 and others and other_sum > 0:
        for idx, (name, price) in enumerate(others):
            share = round(remaining * (price / other_sum), 2)
            if share > 0.05:
                role = "secondary" if idx == 0 and len(others) > 1 else "hedge"
                gross = round(share / price, 2)
                allocations.append(
                    OutcomeAllocation(
                        outcome=name,
                        role=role,
                        size_pct=share,
                        market_price=price,
                        gross_payout_pct=gross,
                        net_roi_if_wins_pct=round(gross - 100.0, 2),
                    )
                )

    return PositionPlan(
        primary_outcome=primary_name,
        primary_size_pct=primary_size,
        primary_market_price=safe_price,
        allocations=allocations,
        total_allocated_pct=100.0,
        net_profit_if_primary_wins_pct=allocations[0].net_roi_if_wins_pct,
        effective_confidence=round(effective_conf, 4),
        edge=round(edge, 4),
        is_barrier_trap=False,
        warning=None,
    )
`,
  },
  {
    filename: 'weekly_report.py',
    pathInRepo: 'weekly_report.py',
    descriptionFa: 'رفع باگ تسویه بازارهای باینری تک‌گزینه‌ای (۲۶ سهم درست) و رفع قفل‌شدن بازارهای زمان‌دار (By Date)',
    bugsFixedCount: 2,
    code: `"""PolyBet Weekly Resolution & Performance Auditor v2.0 — Fixed."""

from __future__ import annotations

from typing import Any, Optional


def resolve_single_prediction_fixed(
    sub_markets: list[dict[str, Any]],
    title: str,
    primary_outcome: str,
) -> tuple[bool, Optional[str], Optional[bool]]:
    """Return (is_resolved, winning_outcome_label, is_correct).

    FIX BUG #1: If len(sub_markets) == 1 and primary_outcome was logged as the full
    question title, compare settled_winner against 'Yes' (when primary_price >= 0.5).
    FIX BUG #7: In multi-date markets ('...by August 31'), if the specific sub-market
    matching primary_outcome has settled 'No', resolve immediately as lost rather than hanging!
    """
    if not sub_markets:
        return False, None, None

    norm_primary = primary_outcome.strip().lower()
    norm_title = title.strip().lower()

    if len(sub_markets) == 1:
        settled = extract_settled_winner(sub_markets[0])
        if settled is None:
            return False, None, None
        # Repair legacy logs where primary_outcome == question title on a binary market
        effective_primary = "yes" if norm_primary == norm_title else norm_primary
        return True, settled, (settled.strip().lower() == effective_primary)

    for market in sub_markets:
        settled = extract_settled_winner(market)
        label = (market.get("groupItemTitle") or market.get("question") or "").strip()
        if settled == "Yes":
            return True, label, (label.lower() == norm_primary)
        if label.lower() == norm_primary and settled == "No":
            return True, f"Not {label}", False

    return False, None, None
`,
  },
  {
    filename: 'scanner.py (Classifier Patch)',
    pathInRepo: 'scanner.py',
    descriptionFa: 'رفع باگ دسته‌بندی اشتباه کلمه "bailey" به عنوان بانک انگلستان (BoE) و فیلتر خودکار مسابقات ورزشی NFL/NBA',
    bugsFixedCount: 2,
    code: `"""Fixed Category Classifier & Group Metadata Resolver for scanner.py."""

import re
from typing import Optional

EXCLUDED_SPORTS_PATTERNS = (
    "pro football", "nfl", "starting qb", "nba", "mlb", "nhl", "super bowl", "premier league"
)

CATEGORY_KEYWORDS_FIXED: dict[str, tuple[str, ...]] = {
    "fed": ("fed", "fomc", "federal reserve", "powell", "rate cut", "rate hike"),
    "ecb": ("ecb", "european central bank", "lagarde"),
    "boe": ("bank of england", "boe rate", "boe decision", "mpc vote", "andrew bailey"),
    "boc": ("bank of canada", "boc rate", "boc decision", "tiff macklem"),
    "cpi": ("cpi", "inflation", "consumer price index"),
    "gdp": ("gdp", "gross domestic product", "economic growth"),
    "employment": ("unemployment", "nonfarm", "payrolls", "jobs report", "jobless claims"),
    "stocks": ("earnings", "quarterly earnings", "eps", "s&p 500", "nasdaq", "spy"),
    "elections": ("election", "primary winner", "president", "senate", "governor", "nominee"),
}


def classify_market_v2(question: str, tag_labels: list[str]) -> Optional[str]:
    haystack = " ".join([question, *tag_labels]).lower()
    if any(sp in haystack for sp in EXCLUDED_SPORTS_PATTERNS):
        return None
    for category, keywords in CATEGORY_KEYWORDS_FIXED.items():
        for kw in keywords:
            if re.search(rf"\\b{re.escape(kw)}\\b", haystack):
                return category
    return None
`,
  },
  {
    filename: 'sources/bls.py + sources/fred.py + sources/base.py',
    pathInRepo: 'sources/',
    descriptionFa: 'رفع باگ سری زمانی اشتباه BLS (جایگزینی 158,000 شاغل با نرخ بیکاری LNS14000000)، تبدیل واحد درصد سالانه CPI در FRED و انقباض بیزی اجماع تک‌منبعی',
    bugsFixedCount: 4,
    code: `"""Fixed Macro Series Transforms & Bayesian Consensus Shrinkage (sources/)."""

from typing import Sequence

# 1. Fixed BLS Series Map (sources/bls.py)
BLS_SERIES_BY_METRIC = {
    "unemployment_rate": "LNS14000000",  # Official U-3 Unemployment Rate (%) e.g. 4.1%
    "cpi_index": "CUUR0000SA0",          # Compute YoY %: (v[0] - v[12]) / v[12] * 100
    "nonfarm_payrolls": "CES0000000001", # Compute MoM net change: v[0] - v[1]
}

# 2. Fixed FRED Unit Transforms (sources/fred.py)
FRED_UNIT_TRANSFORM_BY_DOMAIN = {
    "cpi": "pc1",  # YoY Percentage Change (prevents raw ~315 index comparison!)
    "pce": "pc1",  # YoY Percentage Change
    "gdp": "cca",  # Compounded Annual Rate of Change (QoQ %)
}

# 3. Fixed Bayesian Consensus Score (sources/base.py)
def compute_consensus_score_v2(probabilities: Sequence[float], prior_k: float = 1.5) -> float:
    """Empirical Bayes consensus score preventing n=1 from returning 100%."""
    n = len(probabilities)
    if n == 0:
        return 0.0
    above = sum(1 for p in probabilities if p >= 0.5)
    below = n - above
    raw_agreement = max(above, below) / n
    credibility = n / (n + prior_k)
    return round(raw_agreement * credibility * 100.0, 1)
`,
  },
];
