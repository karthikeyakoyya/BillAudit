-- Vendor billed the other jurisdiction's rate than the one the circuit's two
-- ends call for, and the rate billed is higher than the contract rate.
SELECT line_id,
       'jurisdiction_misrate' AS rule,
       round(amount * (1 - contract_rate / rate_billed), 2) AS est_overcharge,
       'Billed ' || billed_jurisdiction || ' rate ' || CAST(rate_billed AS VARCHAR)
         || '; circuit is ' || true_jurisdiction || ' at ' || CAST(contract_rate AS VARCHAR) AS detail
FROM line_ref
WHERE in_inventory
  AND charge_type = 'MRC'
  AND contract_rate IS NOT NULL
  AND billed_jurisdiction <> true_jurisdiction
  AND rate_billed > contract_rate + 0.005;
