import time

from delta_client import DeltaClient


SYMBOL = "BTCUSD"
TEST_SIZE = 1


def show_position(
    client,
    product_id,
    label,
):
    position = client.get_position(
        product_id
    )

    print(
        f"\n{label}"
    )

    print(
        f"Size        : "
        f"{position.get('size')}"
    )

    print(
        f"Entry price : "
        f"{position.get('entry_price')}"
    )

    return position


def main():
    print(
        "\n⚠️ ONE-CONTRACT LIVE ORDER TEST"
    )

    print(
        "=" * 60
    )

    client = DeltaClient()

    if not client.allow_orders:
        raise RuntimeError(
            "DELTA_ALLOW_ORDERS is not true."
        )

    product = client.get_product(
        SYMBOL
    )

    product_id = int(
        product["id"]
    )

    contract_value = float(
        product["contract_value"]
    )

    print(
        f"\nSymbol         : "
        f"{SYMBOL}"
    )

    print(
        f"Product ID     : "
        f"{product_id}"
    )

    print(
        f"Contract value : "
        f"{contract_value} BTC"
    )

    # ==========================================
    # SAFETY CHECK 1
    # Must be flat before test.
    # ==========================================

    current = show_position(
        client,
        product_id,
        "CURRENT POSITION",
    )

    current_size = int(
        current.get(
            "size",
            0,
        )
        or 0
    )

    if current_size != 0:
        raise RuntimeError(
            "BTCUSD position is NOT flat. "
            "Test aborted."
        )

    # ==========================================
    # SAFETY CHECK 2
    # Explicit confirmation
    # ==========================================

    print(
        "\nThis test will:"
    )

    print(
        "1. BUY exactly 1 BTCUSD contract"
    )

    print(
        "2. Confirm the position"
    )

    print(
        "3. SELL exactly 1 contract "
        "with reduce_only=True"
    )

    print(
        "4. Verify the position is flat"
    )

    confirmation = input(
        "\nType EXACTLY: EXECUTE 1 CONTRACT\n> "
    )

    if confirmation != (
        "EXECUTE 1 CONTRACT"
    ):
        print(
            "\n❌ Test cancelled."
        )
        return

    # ==========================================
    # OPEN 1 CONTRACT
    # ==========================================

    open_client_id = (
        f"manual-open-"
        f"{int(time.time())}"
    )

    print(
        "\n🚀 Sending BUY "
        "1-contract market order..."
    )

    open_order = (
        client.place_market_order(
            product_id=product_id,

            size=TEST_SIZE,

            side="buy",

            client_order_id=(
                open_client_id
            ),

            reduce_only=False,
        )
    )

    print(
        "\n✅ OPEN ORDER RESPONSE"
    )

    print(
        open_order
    )

    time.sleep(
        2
    )

    opened = show_position(
        client,
        product_id,
        "POSITION AFTER OPEN",
    )

    opened_size = int(
        opened.get(
            "size",
            0,
        )
        or 0
    )

    if opened_size <= 0:
        raise RuntimeError(
            "Expected a LONG position "
            "after BUY, but position "
            "was not positive."
        )

    # ==========================================
    # CLOSE EXACTLY 1 CONTRACT
    # REDUCE ONLY
    # ==========================================

    close_client_id = (
        f"manual-close-"
        f"{int(time.time())}"
    )

    print(
        "\n🧯 Closing exactly "
        "1 contract..."
    )

    close_order = (
        client.place_market_order(
            product_id=product_id,

            size=TEST_SIZE,

            side="sell",

            client_order_id=(
                close_client_id
            ),

            reduce_only=True,
        )
    )

    print(
        "\n✅ CLOSE ORDER RESPONSE"
    )

    print(
        close_order
    )

    time.sleep(
        2
    )

    final_position = (
        show_position(
            client,
            product_id,
            "FINAL POSITION",
        )
    )

    final_size = int(
        final_position.get(
            "size",
            0,
        )
        or 0
    )

    print(
        "\n"
        + "=" * 60
    )

    if final_size == 0:
        print(
            "✅ SUCCESS"
        )

        print(
            "BTCUSD position returned "
            "to zero."
        )

    else:
        print(
            "⚠️ POSITION NOT FLAT"
        )

        print(
            f"Remaining size: "
            f"{final_size}"
        )

        print(
            "Do not start the algo."
        )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()