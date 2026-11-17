# Truddy: AI review of the TopG trading strategy

This repo contains an AI assistant's work in understanding and backtesting the TopG price-action strategy (structure marking, TJL1/TJL2, CHOCH, Dual CHOCH, ISS). It is published so the AI's interpretation of the rules and its results can be reviewed.

## Where to start

1. **[topg-practice/TopG_strategy_notes.md](topg-practice/TopG_strategy_notes.md)** shows how the AI understood each concept's rules. Check this first: if the understanding is wrong, the backtests that follow are wrong too.
2. **[topg-practice/concepts/README.md](topg-practice/concepts/README.md)** has the results summary, key findings and caveats across all concepts and timeframes.
3. The per-concept folders hold the rules practised, the results tables and example charts with entry, SL, TP and outcome:
   - [01 Structure marking](topg-practice/concepts/01_structure_marking/README.md)
   - [02 TJL1 / TJL2 A+](topg-practice/concepts/02_TJL1_TJL2/README.md)
   - [03 CHOCH](topg-practice/concepts/03_CHOCH/README.md)
   - [04 Dual CHOCH](topg-practice/concepts/04_Dual_CHOCH/README.md)
   - [05 ISS](topg-practice/concepts/05_ISS/README.md)
4. **[topg-practice/concepts/EVALUATION_SHEET.csv](topg-practice/concepts/EVALUATION_SHEET.csv)** is for marking each example chart as correct or incorrect, with notes.

## Code and data

- `topg-practice/topg_structure_engine.py` does the swing and structure detection.
- `topg-practice/concepts/practice.py` runs each concept across pairs and timeframes and generates the charts, trades.csv and READMEs.
- `topg-practice/concepts/data/` has the OHLC price data (bid) for AUDUSD, USDCAD, NZDUSD, EURJPY, USDCHF and GBPJPY.
- Each concept folder's `trades.csv` lists every individual trade, so any setup can be spot-checked on TradingView. Times are IST.
- `topg-practice/transcripts/` has transcripts of the public YouTube explainers the AI used.

The original course PDFs and class recordings are not included.
