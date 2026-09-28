from delta_client import DeltaClient


client = DeltaClient()


# ==========================================
# PRODUCT
# ==========================================

product = client.get_product(
    "BTCUSD"
)

print("\n✅ PRODUCT")

print(
    "ID:",
    product["id"]
)

print(
    "Symbol:",
    product["symbol"]
)

print(
    "Contract value:",
    product["contract_value"]
)

print(
    "Tick size:",
    product["tick_size"]
)


# ==========================================
# POSITION
# ==========================================

position = client.get_position(
    product["id"]
)

print(
    "\n✅ BTCUSD POSITION"
)

print(
    position
)


# ==========================================
# WALLET
# ==========================================

wallet = client.get_wallet_balances()

print(
    "\n✅ WALLET"
)

print(
    "Net equity:",
    wallet.get(
        "meta",
        {}
    ).get(
        "net_equity"
    )
)

for asset in wallet.get(
    "result",
    []
):
    balance = float(
        asset.get(
            "balance",
            0
        )
        or 0
    )

    available = float(
        asset.get(
            "available_balance",
            0
        )
        or 0
    )

    if (
        balance != 0
        or available != 0
    ):
        print(
            f"\nAsset     : "
            f"{asset.get('asset_symbol')}"
        )

        print(
            f"Balance   : "
            f"{balance}"
        )

        print(
            f"Available : "
            f"{available}"
        )

        print(
            f"Blocked   : "
            f"{asset.get('blocked_margin')}"
        )