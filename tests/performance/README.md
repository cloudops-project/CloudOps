# Performance Testing

QA, platform, and AWS engineers use this area to establish representative scan, API, database, and durable-job baselines.

Workloads must document environment, asset counts, regions, rule set, concurrency, warm/cold state, throttling, cost, and measurement method. Results inform targets; CloudFix does not currently promise that scans finish within a fixed duration.

The repository includes [../../scripts/load/k6-v1-smoke.js](../../scripts/load/k6-v1-smoke.js) as a smoke-load definition. No retained production-scale baseline or live AWS performance result is present; those results require an authorized environment and external log retention.
