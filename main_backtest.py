from backtest.report_text import generate_text_report

report = generate_text_report(
    result=result,
    df_prices=df,                # le DataFrame OHLC chargé
    initial_capital=args.capital,
    symbol=args.symbol,
    timeframe=args.timeframe
)
print(report)

if __name__ == "__main__":
    main()