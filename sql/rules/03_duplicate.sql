-- Same vendor, circuit, period, charge type and amount more than once.
-- The first line by id is kept as the original; later copies are the dispute.
SELECT line_id,
       'duplicate' AS rule,
       amount AS est_overcharge,
       'Repeats line ' || first_id || ' (same circuit, period and amount)' AS detail
FROM (
    SELECT line_id,
           amount,
           row_number() OVER w AS rn,
           first_value(line_id) OVER w AS first_id
    FROM line_ref
    WINDOW w AS (PARTITION BY vendor_id, circuit_id, period, charge_type, amount ORDER BY line_id)
)
WHERE rn > 1;
