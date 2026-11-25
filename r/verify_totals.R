# Independent check of the Python audit totals, using base R only.
# Usage: Rscript r/verify_totals.R [outputs_dir]
args <- commandArgs(trailingOnly = TRUE)
out <- if (length(args) >= 1) args[1] else "outputs"

findings <- read.csv(file.path(out, "findings.csv"), stringsAsFactors = FALSE)
claims   <- read.csv(file.path(out, "claims.csv"),   stringsAsFactors = FALSE)
totals   <- read.csv(file.path(out, "rule_totals.csv"), stringsAsFactors = FALSE)

tol <- 0.01
failures <- 0

# 1. Rule totals recomputed from the line-level findings
r_lines  <- aggregate(est_overcharge ~ rule, data = findings, FUN = sum)
r_counts <- aggregate(line_id ~ rule, data = findings, FUN = length)
chk <- merge(totals, r_lines, by = "rule", suffixes = c("_py", "_r"))
chk <- merge(chk, r_counts, by = "rule")
chk$diff <- round(chk$total_est_overcharge - chk$est_overcharge, 2)
chk$ok <- abs(chk$diff) <= tol & chk$n_lines == chk$line_id
cat("Rule totals: Python vs R (from findings.csv)\n")
print(data.frame(rule = chk$rule, lines_py = chk$n_lines, lines_r = chk$line_id,
                 total_py = chk$total_est_overcharge, total_r = round(chk$est_overcharge, 2),
                 diff = chk$diff, ok = chk$ok), row.names = FALSE)
failures <- failures + sum(!chk$ok)

# 2. Claim totals add back up to the rule totals
c_rule <- aggregate(total_overcharge ~ rule, data = claims, FUN = sum)
chk2 <- merge(totals, c_rule, by = "rule")
chk2$diff <- round(chk2$total_est_overcharge - chk2$total_overcharge, 2)
cat("\nClaims roll-up vs rule totals\n")
print(data.frame(rule = chk2$rule, claims_total = round(chk2$total_overcharge, 2), diff = chk2$diff,
                 ok = abs(chk2$diff) <= tol), row.names = FALSE)
failures <- failures + sum(abs(chk2$diff) > tol)

# 3. Claimable + time-barred = total, claim by claim
split_gap <- abs(claims$claimable_amount + claims$barred_amount - claims$total_overcharge)
cat(sprintf("\nClaimable + barred = total on every claim: %s (largest gap %.4f)\n",
            ifelse(all(split_gap <= tol), "yes", "NO"), max(split_gap)))
failures <- failures + sum(split_gap > tol)

# 4. Expected value = claimable x recovery rate
ev_gap <- abs(claims$expected_value - claims$claimable_amount * claims$recovery_rate)
cat(sprintf("Expected value = claimable x rule rate on every claim: %s (largest gap %.4f)\n",
            ifelse(all(ev_gap <= tol), "yes", "NO"), max(ev_gap)))
failures <- failures + sum(ev_gap > tol)

# 5. Claimable value recomputed from lines using the claim's cutoff
cl <- aggregate(est_overcharge ~ claim_id, data = findings[findings$claimable == "True" | findings$claimable == TRUE, ], FUN = sum)
m <- merge(claims[, c("claim_id", "claimable_amount")], cl, by = "claim_id", all.x = TRUE)
m$est_overcharge[is.na(m$est_overcharge)] <- 0
gap <- abs(m$claimable_amount - m$est_overcharge)
cat(sprintf("Claimable amount matches the claimable lines: %s (largest gap %.4f)\n",
            ifelse(all(gap <= tol), "yes", "NO"), max(gap)))
failures <- failures + sum(gap > tol)

if (failures == 0) {
  cat("\nPASS: R totals match Python\n")
} else {
  cat(sprintf("\nFAIL: %d check(s) differ\n", failures))
  quit(status = 1)
}
