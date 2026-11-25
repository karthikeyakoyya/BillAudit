-- Amount well above the circuit's own history while the rate on the line did
-- not change. One-time install charges (NRC) are excluded by design.
WITH mrc AS (
    SELECT line_id, circuit_id, period, amount
    FROM line_ref
    WHERE charge_type = 'MRC' AND in_inventory
),
hist AS (
    SELECT a.line_id,
           a.amount,
           median(b.amount) AS med,
           count(*) AS n_hist
    FROM mrc a
    JOIN mrc b ON b.circuit_id = a.circuit_id AND b.period < a.period
    GROUP BY a.line_id, a.amount
)
SELECT line_id,
       'spike' AS rule,
       round(amount - med, 2) AS est_overcharge,
       'Billed ' || CAST(amount AS VARCHAR) || ' vs circuit median ' || CAST(round(med, 2) AS VARCHAR)
         || ' over ' || CAST(n_hist AS VARCHAR) || ' prior months' AS detail
FROM hist
WHERE n_hist >= $spike_min_history
  AND amount > $spike_multiplier * med
  AND amount - med >= $spike_min_abs;
