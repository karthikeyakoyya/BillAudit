-- Monthly charge for a period after the month of the disconnect order.
-- The disconnect month itself is billed legitimately and is not flagged.
SELECT line_id,
       'post_disconnect' AS rule,
       amount AS est_overcharge,
       'Billed for ' || strftime(period, '%Y-%m') || ' after disconnect effective '
         || strftime(disconnect_date, '%Y-%m-%d') AS detail
FROM line_ref
WHERE in_inventory
  AND charge_type = 'MRC'
  AND disconnect_date IS NOT NULL
  AND period > date_trunc('month', disconnect_date);
