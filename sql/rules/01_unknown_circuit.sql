-- Billed circuit that is not in the service inventory. Whole charge is disputable.
SELECT line_id,
       'unknown_circuit' AS rule,
       amount AS est_overcharge,
       'Circuit ' || circuit_id || ' is billed but not in the service inventory' AS detail
FROM line_ref
WHERE NOT in_inventory;
