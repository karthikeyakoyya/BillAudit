-- Right jurisdiction, but the rate billed is above the contract rate in force
-- for that period. Under-billing is not flagged.
SELECT line_id,
       'rate_mismatch' AS rule,
       round(amount * (1 - contract_rate / rate_billed), 2) AS est_overcharge,
       'Billed rate ' || CAST(rate_billed AS VARCHAR) || ' vs contract rate '
         || CAST(contract_rate AS VARCHAR) AS detail
FROM line_ref
WHERE in_inventory
  AND charge_type = 'MRC'
  AND contract_rate IS NOT NULL
  AND billed_jurisdiction = true_jurisdiction
  AND rate_billed > contract_rate + 0.005;
