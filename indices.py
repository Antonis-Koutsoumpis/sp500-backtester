"""Shared index configuration for the app and the daily data updater.

Each index lists one or more Yahoo Finance tickers in order of preference.
The updater uses the first ticker that returns data; the one actually used is
recorded in data/metadata.json and shown in the app.

Prices are *price return* (Yahoo "Close", not "Adj Close"), so dividends are
excluded, matching the original S&P 500 file.

Inflation adjustment uses the CPI of the index's own currency area:
  USD -> US CPI-U, EUR -> euro-area HICP, JPY -> Japan CPI, GBP -> UK CPI.
"""

INDICES = {
    "sp500": {
        "name": "S&P 500",
        "tickers": ["^GSPC"],
        "currency": "USD",
        "cpi": "US",
        "region": "United States",
        "short": "500 large US companies, weighted by market value.",
        "description": (
            "The S&P 500 tracks about 500 of the largest companies listed in the "
            "United States, weighted by market capitalisation, so the biggest "
            "companies (e.g. Apple, Microsoft, Nvidia) have the most influence. "
            "It covers roughly 80% of the US stock market's value and is the most "
            "widely used benchmark for US stocks. The index in its 500-stock form "
            "dates from 1957; earlier values come from its predecessor, the S&P 90."
        ),
    },
    "sp500_ew": {
        "name": "S&P 500 Equal Weight",
        "tickers": ["^SPXEW", "RSP"],
        "currency": "USD",
        "cpi": "US",
        "region": "United States",
        "short": "Same 500 companies as the S&P 500, each given the same weight.",
        "description": (
            "Holds the same companies as the S&P 500, but each one gets an equal "
            "share (about 0.2%) instead of being weighted by size. It is "
            "rebalanced every quarter. This gives smaller and mid-sized members "
            "more influence and makes it far less concentrated in the few largest "
            "tech companies, so it behaves differently from the regular S&P 500 "
            "when mega-caps lead or lag."
        ),
    },
    "nasdaq100": {
        "name": "Nasdaq 100",
        "tickers": ["^NDX"],
        "currency": "USD",
        "cpi": "US",
        "region": "United States",
        "short": "100 largest non-financial companies on the Nasdaq; tech-heavy.",
        "description": (
            "The Nasdaq 100 contains the 100 largest non-financial companies "
            "listed on the Nasdaq exchange, weighted (with caps) by market value. "
            "It is dominated by technology, communication and consumer companies, "
            "which has made it more volatile than the S&P 500 — it fell about 80% "
            "in the dot-com crash. Launched in 1985."
        ),
    },
    "dowjones": {
        "name": "Dow Jones Industrial Average",
        "tickers": ["^DJI"],
        "currency": "USD",
        "cpi": "US",
        "region": "United States",
        "short": "30 large US 'blue-chip' companies, weighted by share price.",
        "description": (
            "The Dow Jones Industrial Average follows 30 large, well-established "
            "US companies. Unusually, it is price-weighted: a stock with a higher "
            "share price counts for more, regardless of company size. It is the "
            "oldest major US index (1896), but the free data used here starts "
            "later — see the data range below."
        ),
    },
    "total_us": {
        "name": "Total U.S. Stock Market",
        "tickers": ["^W5000", "VTI"],
        "currency": "USD",
        "cpi": "US",
        "region": "United States",
        "short": "Practically every listed US company — large, mid and small.",
        "description": (
            "Covers essentially the entire US stock market — large, mid, small and "
            "micro-cap companies — weighted by market value. Uses the Wilshire 5000 "
            "index (or, if unavailable, the Vanguard Total Stock Market ETF, VTI). "
            "Because large companies dominate by value, it moves very similarly to "
            "the S&P 500, with a bit more small-company exposure."
        ),
    },
    "world": {
        "name": "MSCI World (ETF)",
        "tickers": ["URTH"],
        "currency": "USD",
        "cpi": "US",
        "region": "Global developed markets",
        "short": "~1,400 large and mid-size companies in 23 developed countries.",
        "description": (
            "The MSCI World index covers large and mid-size companies across 23 "
            "developed countries (US, Europe, Japan, Canada, Australia, …). The US "
            "makes up around 70% of it. Data comes from the iShares MSCI World ETF "
            "(URTH), priced in US dollars, which only exists since January 2012. "
            "Emerging markets such as China and India are not included."
        ),
    },
    "stoxx600": {
        "name": "STOXX Europe 600",
        "tickers": ["^STOXX"],
        "currency": "EUR",
        "cpi": "EA",
        "region": "Europe",
        "short": "600 large, mid and small companies from 17 European countries.",
        "description": (
            "The broadest common benchmark for European stocks: 600 companies "
            "from 17 countries, including the eurozone, the UK, Switzerland and "
            "the Nordics, weighted by market value. Quoted in euros; the "
            "inflation-adjusted version uses euro-area HICP inflation."
        ),
    },
    "eurostoxx50": {
        "name": "Euro Stoxx 50",
        "tickers": ["^STOXX50E"],
        "currency": "EUR",
        "cpi": "EA",
        "region": "Eurozone",
        "short": "50 largest blue-chip companies in the eurozone.",
        "description": (
            "The 50 largest companies of the eurozone (e.g. ASML, LVMH, SAP, "
            "TotalEnergies), weighted by market value. Unlike the STOXX Europe 600 "
            "it excludes non-euro countries such as the UK and Switzerland. "
            "Quoted in euros; the inflation-adjusted version uses euro-area HICP."
        ),
    },
    "ftse100": {
        "name": "FTSE 100",
        "tickers": ["^FTSE"],
        "currency": "GBP",
        "cpi": "UK",
        "region": "United Kingdom",
        "short": "100 largest companies on the London Stock Exchange.",
        "description": (
            "The 100 largest companies listed in London, weighted by market value. "
            "Heavy in energy, mining, banks and consumer staples, and most of its "
            "companies earn their revenue abroad. Quoted in British pounds; the "
            "inflation-adjusted version uses UK CPI. Launched in 1984."
        ),
    },
    "nikkei225": {
        "name": "Nikkei 225",
        "tickers": ["^N225"],
        "currency": "JPY",
        "cpi": "JP",
        "region": "Japan",
        "short": "225 large companies on the Tokyo Stock Exchange; price-weighted.",
        "description": (
            "Japan's best-known index: 225 large companies on the Tokyo Stock "
            "Exchange, price-weighted like the Dow. Famous for its 1989 bubble "
            "peak, which it did not surpass again until 2024 — a reminder that "
            "lump sums can stay underwater for decades. Quoted in yen; the "
            "inflation-adjusted version uses Japanese CPI."
        ),
    },
    "em": {
        "name": "MSCI Emerging Markets (ETF)",
        "tickers": ["EEM"],
        "currency": "USD",
        "cpi": "US",
        "region": "Emerging markets",
        "short": "~1,200 companies in about 24 emerging economies.",
        "description": (
            "Large and mid-size companies in about 24 emerging economies, led by "
            "China, India, Taiwan and South Korea. Data comes from the iShares MSCI "
            "Emerging Markets ETF (EEM), priced in US dollars, available since 2003. "
            "Returns therefore include currency movements against the dollar."
        ),
    },
}

CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}

CPI_NAMES = {
    "US": "US CPI-U (all items)",
    "EA": "Euro-area HICP (all items)",
    "UK": "UK CPI (all items)",
    "JP": "Japan CPI (all items)",
}
