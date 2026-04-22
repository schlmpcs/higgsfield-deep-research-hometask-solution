Grade whether every factual claim in the final answer is traceable to a URL the agent actually fetched.

Scoring guidance:
- 1.0: Every factual claim in the answer corresponds to a URL present in the fetched pages listed in the trace.
- 0.5: Most claims are grounded, but one or more minor claims lack a fetched source, or a cited URL appears in a search snippet but was never fetched.
- 0.0: One or more significant claims have no matching fetched source, a cited URL was never fetched, or the agent fabricated sources.

Pass only when all material factual claims can be traced to a page the agent actually fetched (via fetch_url) during this run. A URL appearing only in a web_search snippet does not count as fetched.
