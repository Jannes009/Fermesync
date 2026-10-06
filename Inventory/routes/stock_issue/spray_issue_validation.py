from decimal import Decimal, InvalidOperation


def validate_spray_execution_quantities(cursor, execution_id, lines, quantity_key, adjustment_sign):
    cursor.execute("""
        SELECT REQ.StockId, MAX(STK.StockDescription), SUM(REQ.TotalQty)
        FROM [agr].[_uvSprayStockRequirements] REQ
        LEFT JOIN [cmn].[_uvStockItems] STK ON STK.StockLink = REQ.StockId
        WHERE REQ.SprayHExecutionId = ?
        GROUP BY REQ.StockId
    """, (execution_id,))
    recommendations = {
        int(row[0]): (row[1] or str(row[0]), Decimal(str(row[2] or 0)))
        for row in cursor.fetchall()
    }
    if not recommendations:
        raise ValueError("Cannot complete this issue because the spray execution has no recommended quantities.")

    cursor.execute("""
        SELECT LIN.IssLineStockLink,
               SUM(LIN.IssLineQtyIssued - ISNULL(LIN.IssLineQtyReceived, 0))
        FROM stk.IssueHeader HEA
        JOIN stk.IssueLines LIN ON LIN.IssLineIssueId = HEA.IdIssue
        WHERE HEA.IssSprayExecutionId = ? and HEA.IssCancelled = 0
        GROUP BY LIN.IssLineStockLink
    """, (execution_id,))
    previously_issued = {
        int(row[0]): Decimal(str(row[1] or 0))
        for row in cursor.fetchall()
    }

    adjustments = {}
    for line in lines or []:
        try:
            stock_id = int(line.get("product_link"))
            quantity = Decimal(str(line.get(quantity_key)))
        except (TypeError, ValueError, InvalidOperation):
            raise ValueError("Cannot complete this issue because a product quantity is invalid.")
        if not quantity.is_finite() or quantity < 0:
            raise ValueError("Cannot complete this issue because a product quantity is invalid.")
        if stock_id not in recommendations:
            raise ValueError(f"Cannot complete this issue because product {stock_id} has no spray recommendation.")
        adjustments[stock_id] = adjustments.get(stock_id, Decimal("0")) + quantity * adjustment_sign

    violations = []
    for stock_id, (description, recommended) in recommendations.items():
        total_issued = previously_issued.get(stock_id, Decimal("0")) + adjustments.get(stock_id, Decimal("0"))
        lower_limit = recommended * Decimal("0.90")
        upper_limit = recommended * Decimal("1.10")
        if total_issued < lower_limit or total_issued > upper_limit:
            violations.append(
                f"{description}: recommended {recommended:,.2f}, total issued {total_issued:,.2f}, "
                f"allowed {lower_limit:,.2f} - {upper_limit:,.2f}"
            )

    if violations:
        raise ValueError(
            "Cannot complete spray issue: total quantities must be within 10% of the recommendation. "
            + "; ".join(violations)
        )