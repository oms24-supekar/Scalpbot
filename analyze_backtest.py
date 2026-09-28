import pandas as pd


FILE = "backtests/btc_orderblock_trades.csv"

df = pd.read_csv(FILE)

wins = df[df["net_return_pct"] > 0]
losses = df[df["net_return_pct"] <= 0]


print("\n" + "=" * 55)
print("📊 TRADE QUALITY ANALYSIS")
print("=" * 55)

print(f"\nTotal trades : {len(df)}")

print("\n--- WINNERS ---")

print(
    f"Number       : {len(wins)}"
)

print(
    f"Average win  : "
    f"{wins['net_return_pct'].mean():.4f}%"
)

print(
    f"Best win     : "
    f"{wins['net_return_pct'].max():.4f}%"
)

print(
    f"Total wins   : "
    f"{wins['net_return_pct'].sum():.4f}%"
)


print("\n--- LOSERS ---")

print(
    f"Number       : {len(losses)}"
)

print(
    f"Average loss : "
    f"{losses['net_return_pct'].mean():.4f}%"
)

print(
    f"Worst loss   : "
    f"{losses['net_return_pct'].min():.4f}%"
)

print(
    f"Total losses : "
    f"{losses['net_return_pct'].sum():.4f}%"
)


print("\n--- PAYOFF ---")

avg_win = wins["net_return_pct"].mean()
avg_loss = abs(
    losses["net_return_pct"].mean()
)

if avg_loss > 0:
    payoff = avg_win / avg_loss

    print(
        f"Average win/loss ratio : "
        f"{payoff:.2f}"
    )


print("\n--- 5 WORST TRADES ---")

worst = df.sort_values(
    "net_return_pct"
).head(5)

print(
    worst[
        [
            "side",
            "entry_time",
            "exit_time",
            "entry",
            "exit",
            "net_return_pct"
        ]
    ].to_string(index=False)
)

print("\n--- 5 BEST TRADES ---")

best = df.sort_values(
    "net_return_pct",
    ascending=False
).head(5)

print(
    best[
        [
            "side",
            "entry_time",
            "exit_time",
            "entry",
            "exit",
            "net_return_pct"
        ]
    ].to_string(index=False)
)

print("\n" + "=" * 55)