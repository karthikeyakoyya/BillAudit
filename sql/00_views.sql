-- Reference views shared by every audit rule.
-- Tables expected: invoice_lines, circuits, orders, contracts, lerg_sim, neca_sim.

-- A circuit's true jurisdiction comes from the states of its two ends, looked
-- up in the LERG-style table. It does not come from what the vendor billed.
CREATE OR REPLACE VIEW circuit_ref AS
SELECT c.circuit_id,
       c.vendor_id,
       c.service,
       c.install_date,
       c.disconnect_date,
       a.state AS a_state,
       z.state AS z_state,
       CASE WHEN a.state = z.state THEN 'intrastate' ELSE 'interstate' END AS true_jurisdiction
FROM circuits c
LEFT JOIN lerg_sim a ON a.npanxx = c.a_npanxx
LEFT JOIN lerg_sim z ON z.npanxx = c.z_npanxx;

-- Every invoice line with the contract rate that applied in its period.
-- Amended rates are picked by effective date, so a mid-year rate change does
-- not look like an overcharge.
CREATE OR REPLACE VIEW line_ref AS
SELECT l.line_id,
       l.invoice_id,
       l.vendor_id,
       l.circuit_id,
       l.period,
       l.charge_type,
       l.rate_billed,
       l.amount,
       l.billed_jurisdiction,
       l.order_ref,
       cr.service,
       cr.disconnect_date,
       cr.true_jurisdiction,
       cr.a_state,
       (cr.circuit_id IS NOT NULL) AS in_inventory,
       k.rate AS contract_rate,
       n.surcharge_pct AS neca_pct
FROM invoice_lines l
LEFT JOIN circuit_ref cr ON cr.circuit_id = l.circuit_id
LEFT JOIN contracts k
       ON k.vendor_id = l.vendor_id
      AND k.service = cr.service
      AND k.jurisdiction = cr.true_jurisdiction
      AND l.period BETWEEN k.effective_from AND k.effective_to
-- Regulatory surcharge percentage from the NECA-style tariff table, by the
-- circuit's originating state and service, as of the invoice period.
LEFT JOIN neca_sim n
       ON n.state = cr.a_state
      AND n.service = cr.service
      AND l.period BETWEEN n.effective_from AND n.effective_to;
