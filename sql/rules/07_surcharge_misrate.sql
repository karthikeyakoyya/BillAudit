-- Regulatory surcharge billed above the tariff percentage for the circuit's
-- originating state and service in that period. Services the tariff exempts
-- carry 0 percent, so any surcharge on them is flagged in full. Surcharges
-- billed at the new rate after a tariff change are not flagged.
SELECT line_id,
       'surcharge_misrate' AS rule,
       round(amount - contract_rate * coalesce(neca_pct, 0) / 100.0, 2) AS est_overcharge,
       'Surcharge billed at ' || CAST(round(100.0 * amount / contract_rate, 2) AS VARCHAR)
         || ' percent; tariff for ' || a_state || ' ' || service || ' is '
         || CAST(coalesce(neca_pct, 0) AS VARCHAR) || ' percent' AS detail
FROM line_ref
WHERE in_inventory
  AND charge_type = 'SUR'
  AND contract_rate IS NOT NULL
  AND amount > contract_rate * coalesce(neca_pct, 0) / 100.0 + 0.01;
